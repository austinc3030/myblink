"""
VoIP.ms 2FA integration handler for MyBlink application.

Handles retrieving 2FA codes via SMS from VoIP.ms and managing SMS messages.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional

from voipms import VoipMs

from .models import Credentials, AppConfig
from .exceptions import ConfigurationError


class VoipMsHandler:
    """
    Handles VoIP.ms SMS integration for 2FA code retrieval.
    
    Manages VoIP.ms client, retrieves SMS messages, extracts 2FA codes,
    and cleans up old messages.
    """
    
    # Regex pattern for 2FA code extraction
    CODE_PATTERN = re.compile(r"\d{6}")
    
    def __init__(
        self,
        credentials: Credentials,
        config: AppConfig,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize VoIP.ms handler.
        
        Args:
            credentials: Application credentials
            config: Application configuration
            logger: Logger instance (creates new one if not provided)
            
        Raises:
            ConfigurationError: If VoIP.ms initialization fails
        """
        self.credentials = credentials
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.voipms: Optional[VoipMs] = None
        
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """
        Initialize VoIP.ms API client.
        
        Raises:
            ConfigurationError: If VoIP.ms initialization fails
        """
        try:
            self.voipms = VoipMs(
                self.credentials.voipms.username,
                self.credentials.voipms.password,
            )
            self.logger.info("VoIP.ms client initialized")
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize VoIP.ms client: {e}") from e
    
    def _get_sms_messages(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieve SMS messages from VoIP.ms.
        
        Returns:
            List of SMS message dictionaries, or None if retrieval fails
        """
        try:
            if not self.voipms:
                self.logger.error("VoIP.ms client not initialized")
                return None
            
            response = self.voipms.dids.get.sms()
            
            if isinstance(response, dict) and "sms" in response:
                return response["sms"]
            else:
                self.logger.warning(f"Unexpected VoIP.ms response format: {type(response)}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to retrieve SMS messages: {e}", exc_info=True)
            return None
    
    def _extract_2fa_code(self, message: str) -> Optional[str]:
        """
        Extract 6-digit 2FA code from SMS message.
        
        Args:
            message: SMS message content
            
        Returns:
            6-digit code if found, None otherwise
        """
        match = self.CODE_PATTERN.search(message)
        return match.group() if match else None
    
    def get_blink_2fa_code(self) -> Optional[str]:
        """
        Retrieve Blink 2FA code from VoIP.ms SMS with retry logic.
        
        This method polls VoIP.ms for SMS messages containing the Blink 2FA code,
        retrying up to the configured limit with delays between attempts.
        
        Returns:
            6-digit 2FA code if successfully retrieved, None otherwise
        """
        self.logger.debug(
            f"Retrieving 2FA code (up to {self.config.voipms_retry_limit} retries, "
            f"{self.config.voipms_retry_delay}s delay)"
        )
        
        for attempt in range(1, self.config.voipms_retry_limit + 1):
            self.logger.debug(f"Attempt {attempt}/{self.config.voipms_retry_limit}")
            
            sms_messages = self._get_sms_messages()
            
            if not sms_messages:
                self.logger.debug(f"No SMS messages found on attempt {attempt}")
                if attempt < self.config.voipms_retry_limit:
                    time.sleep(self.config.voipms_retry_delay)
                continue
            
            self.logger.debug(f"Retrieved {len(sms_messages)} SMS message(s)")
            
            # Filter for Blink messages
            blink_messages = [
                msg for msg in sms_messages
                if (
                    msg.get("type") == "1" and  # Received message
                    msg.get("did") == self.credentials.voipms.did and
                    self.config.voipms_message_keyword in msg.get("message", "")
                )
            ]
            
            if len(blink_messages) == 1:
                message_text = blink_messages[0]["message"]
                self.logger.debug(f"Found Blink message: {message_text}")
                
                code = self._extract_2fa_code(message_text)
                if code:
                    self.logger.info(f"Successfully retrieved 2FA code: {code}")
                    return code
                else:
                    self.logger.warning(f"Blink message found but no code extracted: {message_text}")
                    
            elif len(blink_messages) > 1:
                self.logger.warning(
                    f"Found {len(blink_messages)} Blink messages (expected 1). "
                    "Consider cleaning up old SMS messages."
                )
            
            if attempt < self.config.voipms_retry_limit:
                time.sleep(self.config.voipms_retry_delay)
        
        self.logger.error(
            f"Failed to retrieve 2FA code after {self.config.voipms_retry_limit} attempts"
        )
        return None
    
    def delete_blink_sms_messages(self) -> None:
        """
        Delete Blink-related SMS messages from VoIP.ms.
        
        Cleans up old 2FA messages to prevent confusion in future retrievals.
        Only deletes messages from 5-digit short codes containing the Blink keyword.
        """
        if not self.voipms:
            return
        
        sms_messages = self._get_sms_messages()
        if not sms_messages:
            return
        
        # Filter for Blink messages from short codes
        blink_messages = [
            msg for msg in sms_messages
            if (
                msg.get("type") == "1" and
                msg.get("did") == self.credentials.voipms.did and
                len(msg.get("contact", "")) == 5 and  # Short code
                self.config.voipms_message_keyword in msg.get("message", "")
            )
        ]
        
        deleted_count = 0
        for msg in blink_messages:
            try:
                msg_id = int(msg["id"])
                self.voipms.dids.delete.sms(msg_id)
                deleted_count += 1
                self.logger.debug(f"Deleted SMS message ID: {msg_id}")
            except Exception as e:
                self.logger.warning(f"Failed to delete SMS {msg.get('id')}: {e}")
        
        if deleted_count > 0:
            self.logger.info(f"Deleted {deleted_count} old Blink SMS message(s)")
