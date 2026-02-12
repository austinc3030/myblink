"""
Configuration and credential management for MyBlink application.

Handles loading, saving, and validation of both application configuration
and credentials from environment variables and YAML files.
"""

import logging
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .models import AppConfig, Credentials
from .exceptions import ConfigurationError


# Environment variable names
CONFIG_FILE_ENV = "MYBLINK_CONFIG"
BLINK_USERNAME_ENV = "BLINK_USERNAME"
BLINK_PASSWORD_ENV = "BLINK_PASSWORD"
VOIPMS_USERNAME_ENV = "VOIPMS_USERNAME"
VOIPMS_PASSWORD_ENV = "VOIPMS_PASSWORD"
VOIPMS_DID_ENV = "VOIPMS_DID"

# Default file path
DEFAULT_CONFIG_FILE = Path("/app/config.yaml")


def mask_email(email: Optional[str]) -> str:
    """
    Mask email address for secure logging.
    
    Args:
        email: Email address to mask
        
    Returns:
        Masked email address (e.g., "us***@g***")
        
    Examples:
        >>> mask_email("user@example.com")
        'us***@e***'
        >>> mask_email("a@b.com")
        '***@b***'
    """
    if not email or '@' not in email:
        return email or "***"
    
    local, domain = email.split('@', 1)
    masked_local = local[:2] + '***' if len(local) > 2 else '***'
    masked_domain = domain[0] + '***' if domain else '***'
    return f"{masked_local}@{masked_domain}"


class ConfigManager:
    """
    Manages application configuration and credentials.
    
    Handles loading from environment variables and YAML files, validation,
    and persistence of configuration settings.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize configuration manager.
        
        Args:
            logger: Logger instance (creates new one if not provided)
        """
        self.logger = logger or logging.getLogger(__name__)
        self._config_file = Path(os.getenv(CONFIG_FILE_ENV, DEFAULT_CONFIG_FILE))
        self.config: Optional[AppConfig] = None
        self.credentials: Optional[Credentials] = None
        self._configured = False
    
    def load_config(self) -> AppConfig:
        """
        Load configuration from YAML file.
        
        Loads configuration from the file specified by MYBLINK_CONFIG environment
        variable, or uses defaults if not specified.
        
        Returns:
            AppConfig instance
            
        Raises:
            ConfigurationError: If config file is invalid or cannot be read
        """
        try:
            # Check if path is a directory (Docker volume mount issue)
            if self._config_file.exists() and self._config_file.is_dir():
                self.logger.warning(
                    f"Config path is a directory (Docker volume issue): {self._config_file}, using defaults"
                )
                self.config = AppConfig()
                return self.config
            
            if not self._config_file.exists():
                self.logger.warning(
                    f"Config file not found: {self._config_file}, using defaults"
                )
                self.config = AppConfig()
                return self.config
            
            with open(self._config_file, 'r') as f:
                config_dict = yaml.safe_load(f) or {}
            
            self.config = AppConfig.from_dict(config_dict)
            
            self.logger.info(f"Configuration loaded from: {self._config_file}")
            return self.config
            
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in config file: {e}") from e
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}") from e
    
    def load_credentials(self) -> Tuple[Optional[Credentials], bool]:
        """
        Load credentials from environment variables or config file.
        
        Priority order:
        1. Environment variables (BLINK_USERNAME, BLINK_PASSWORD, etc.) - if found, saved to config
        2. Config file credentials (blink_username, voipms_username, etc.)
        3. Unconfigured mode - use web interface
        
        Returns:
            Tuple of (Credentials object or None, configured flag)
        """
        try:
            source = None
            save_to_config = False
            
            # Priority 1: Check environment variables
            blink_user = os.getenv(BLINK_USERNAME_ENV)
            blink_pass = os.getenv(BLINK_PASSWORD_ENV)
            voipms_user = os.getenv(VOIPMS_USERNAME_ENV)
            voipms_pass = os.getenv(VOIPMS_PASSWORD_ENV)
            voipms_did = os.getenv(VOIPMS_DID_ENV)
            
            if all([blink_user, blink_pass, voipms_user, voipms_pass, voipms_did]):
                # Found in environment variables - save to config for web UI editing
                if self.config:
                    self.config.blink_username = blink_user
                    self.config.blink_password = blink_pass
                    self.config.voipms_username = voipms_user
                    self.config.voipms_password = voipms_pass
                    self.config.voipms_did = voipms_did
                    save_to_config = True
                
                creds_dict = {
                    "blink": {
                        "username": blink_user,
                        "password": blink_pass
                    },
                    "voipms": {
                        "username": voipms_user,
                        "password": voipms_pass,
                        "did": voipms_did
                    }
                }
                source = "environment variables"
                self.logger.info("Credentials loaded from environment variables (will save to config)")
            
            # Priority 2: Check config file
            elif self.config and self.config.blink_username and self.config.voipms_username:
                creds_dict = {
                    "blink": {
                        "username": self.config.blink_username,
                        "password": self.config.blink_password,
                        "cached_credentials": self.config.blink_cached_credentials
                    },
                    "voipms": {
                        "username": self.config.voipms_username,
                        "password": self.config.voipms_password,
                        "did": self.config.voipms_did
                    }
                }
                source = f"config file: {self._config_file}"
                self.logger.info(f"Credentials loaded from config file: {self._config_file}")
            
            # Priority 3: Unconfigured - use web UI
            else:
                self.logger.info(
                    "No credentials found (checked environment variables and config file). "
                    "Starting in setup mode - configure via web interface."
                )
                return None, False
            
            # Validate and create credentials object
            self.credentials = Credentials.from_dict(creds_dict)
            
            # Validate required fields are not empty
            if not self.credentials.blink.username or not self.credentials.blink.password:
                self.logger.warning(f"Blink credentials incomplete (from {source})")
                return None, False
            
            if not self.credentials.voipms.username or not self.credentials.voipms.password:
                self.logger.warning(f"VoIP.ms credentials incomplete (from {source})")
                return None, False
            
            if not self.credentials.voipms.did:
                self.logger.warning(f"VoIP.ms DID missing (from {source})")
                return None, False
            
            # Save env vars to config file for web UI editing
            if save_to_config:
                self.save_config()
            
            self._configured = True
            self.logger.info(
                f"Credentials validated for user: {mask_email(self.credentials.blink.username)} (from {source})"
            )
            
            return self.credentials, True
            
        except Exception as e:
            self.logger.error(f"Failed to load credentials: {e}")
            return None, False
    
    def save_config(self) -> None:
        """
        Save configuration to YAML file.
        
        Persists all settings including credentials to config file.
        Logs error but does not raise exception to avoid disrupting operations.
        """
        if not self.config:
            self.logger.warning("Cannot save config: no config loaded")
            return
        
        try:
            # Ensure directory exists
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert config to dict
            config_dict = {
                "debug_mode": self.config.debug_mode,
                "health_file": self.config.health_file,
                "health_check_interval": self.config.health_check_interval,
                "max_consecutive_errors": self.config.max_consecutive_errors,
                "blink_retry_limit": self.config.blink_retry_limit,
                "snooze_syncs": self.config.snooze_syncs,
                "no_snooze_syncs": self.config.no_snooze_syncs,
                "snooze_cams": self.config.snooze_cams,
                "no_snooze_cams": self.config.no_snooze_cams,
                "arm_syncs": self.config.arm_syncs,
                "no_arm_syncs": self.config.no_arm_syncs,
                "arm_cams": self.config.arm_cams,
                "no_arm_cams": self.config.no_arm_cams,
                "thumbnail_cams": self.config.thumbnail_cams,
                "no_thumbnail_cams": self.config.no_thumbnail_cams,
                "voipms_message_keyword": self.config.voipms_message_keyword,
                "voipms_retry_limit": self.config.voipms_retry_limit,
                "voipms_retry_delay": self.config.voipms_retry_delay,
                "voipms_sms_wait": self.config.voipms_sms_wait,
                "schedule_interval_hours": self.config.schedule_interval_hours,
                "status_log_interval": self.config.status_log_interval,
                "main_loop_sleep": self.config.main_loop_sleep,
                "error_recovery_sleep": self.config.error_recovery_sleep,
                "web_enabled": self.config.web_enabled,
                "web_port": self.config.web_port,
                "web_host": self.config.web_host,
                "web_theme": self.config.web_theme,
                # Authentication settings
                "auth_enabled": self.config.auth_enabled,
                "auth_method": self.config.auth_method,
                "auth_session_timeout": self.config.auth_session_timeout,
                "auth_basic_username": self.config.auth_basic_username,
                "auth_basic_password_hash": self.config.auth_basic_password_hash,
                "auth_oidc_client_id": self.config.auth_oidc_client_id,
                "auth_oidc_client_secret": self.config.auth_oidc_client_secret,
                "auth_oidc_server_metadata_url": self.config.auth_oidc_server_metadata_url,
                "auth_oidc_redirect_uri": self.config.auth_oidc_redirect_uri,
                "auth_oidc_allowed_emails": self.config.auth_oidc_allowed_emails,
                "auth_oidc_allowed_domains": self.config.auth_oidc_allowed_domains,
                # Credentials
                "blink_username": self.config.blink_username,
                "blink_password": self.config.blink_password,
                "voipms_username": self.config.voipms_username,
                "voipms_password": self.config.voipms_password,
                "voipms_did": self.config.voipms_did,
            }
            
            # Add cached credentials if present
            if self.config.blink_cached_credentials:
                config_dict["blink_cached_credentials"] = self.config.blink_cached_credentials
            
            with open(self._config_file, 'w') as f:
                yaml.safe_dump(config_dict, f, default_flow_style=False, sort_keys=False)
            
            self.logger.debug(f"Configuration saved to: {self._config_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
    
    def set_credentials(self, creds_dict: Dict[str, Any]) -> Credentials:
        """
        Set credentials from dictionary.
        
        This is called by the web UI when user enters credentials.
        
        Args:
            creds_dict: Dictionary containing blink and voipms credentials
            
        Returns:
            Validated Credentials object
            
        Raises:
            ConfigurationError: If credentials are invalid
        """
        # Validate and create credentials object
        credentials = Credentials.from_dict(creds_dict)
        
        # Validate required fields
        if not credentials.blink.username or not credentials.blink.password:
            raise ConfigurationError("Blink username and password are required")
        
        if not credentials.voipms.username or not credentials.voipms.password:
            raise ConfigurationError("VoIP.ms username and password are required")
        
        if not credentials.voipms.did:
            raise ConfigurationError("VoIP.ms DID is required")
        
        # Update config with credentials
        if self.config:
            self.config.blink_username = credentials.blink.username
            self.config.blink_password = credentials.blink.password
            self.config.voipms_username = credentials.voipms.username
            self.config.voipms_password = credentials.voipms.password
            self.config.voipms_did = credentials.voipms.did
        
        # Save credentials to config file
        self.save_config()
        
        self.credentials = credentials
        self._configured = True
        
        return credentials
    
    def is_configured(self) -> bool:
        """Check if application is properly configured with credentials."""
        return self._configured
    
    def get_config_file(self) -> Path:
        """Get the configuration file path."""
        return self._config_file
