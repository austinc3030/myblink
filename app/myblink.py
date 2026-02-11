"""
Blink Camera Automation with VoIP.ms 2FA Integration.

This module provides automated management of Blink security cameras with
2FA authentication via VoIP.ms SMS integration. It handles camera thumbnails,
arming/disarming, and snoozing on a scheduled basis.

Author: Your Name
Version: 2.0.0
License: MIT
"""

import asyncio
import json
import logging
import os
import re
import signal
import sys
import time
import yaml
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, TypeVar, cast

from aiohttp import ClientSession
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink
from blinkpy.camera import BlinkCamera
from blinkpy.sync_module import BlinkSyncModule
from voipms import VoipMs

# Import web server (optional dependency)
try:
    from web_server import WebServer
    WEB_SERVER_AVAILABLE = True
except ImportError:
    WebServer = None
    WEB_SERVER_AVAILABLE = False

# Type aliases
T = TypeVar('T')
AsyncFunc = Callable[..., Awaitable[T]]


class HealthStatus(Enum):
    """Health status enumeration for monitoring."""
    
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthData:
    """Health check data structure."""
    
    status: HealthStatus
    timestamp: float
    message: str
    consecutive_errors: int = 0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert health data to dictionary."""
        return {
            "healthy": self.status == HealthStatus.HEALTHY,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "message": self.message,
            "consecutive_errors": self.consecutive_errors,
            "error": self.error
        }


@dataclass
class BlinkCredentials:
    """Blink authentication credentials."""
    
    username: str
    password: str
    cached_credentials: Optional[str] = None


@dataclass
class VoipMsCredentials:
    """VoIP.ms API credentials."""
    
    username: str
    password: str
    did: str


@dataclass
class Credentials:
    """Application credentials."""
    
    blink: BlinkCredentials
    voipms: VoipMsCredentials
    
    @classmethod
    def from_dict(cls, creds_dict: Dict[str, Any]) -> 'Credentials':
        """
        Create Credentials from dictionary with validation.
        
        Args:
            creds_dict: Credentials dictionary from YAML file
            
        Returns:
            Validated Credentials instance
            
        Raises:
            ValueError: If required credential keys are missing
        """
        try:
            blink_creds = BlinkCredentials(
                username=creds_dict["blink"]["username"],
                password=creds_dict["blink"]["password"],
                cached_credentials=creds_dict["blink"].get("cached_credentials")
            )
            
            voipms_creds = VoipMsCredentials(
                username=creds_dict["voipms"]["username"],
                password=creds_dict["voipms"]["password"],
                did=creds_dict["voipms"]["did"]
            )
            
            return cls(blink=blink_creds, voipms=voipms_creds)
        except KeyError as e:
            raise ValueError(f"Missing required credential key: {e}") from e
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Credentials to dictionary format."""
        return {
            "blink": {
                "username": self.blink.username,
                "password": self.blink.password,
                "cached_credentials": self.blink.cached_credentials
            },
            "voipms": {
                "username": self.voipms.username,
                "password": self.voipms.password,
                "did": self.voipms.did
            }
        }


@dataclass
class AppConfig:
    """Application configuration settings."""
    
    # Logging
    debug_mode: bool = False
    
    # File paths
    health_file: str = "/tmp/myblink_health.json"
    
    # Health monitoring
    health_check_interval: int = 30
    max_consecutive_errors: int = 3
    
    # Blink settings (configurable via web UI)
    blink_retry_limit: int = 3
    
    # Camera/Sync operation settings (managed via web UI)
    # These default to empty lists - web UI manages all camera/sync operations
    snooze_syncs: List[str] = field(default_factory=list)
    no_snooze_syncs: List[str] = field(default_factory=list)
    snooze_cams: List[str] = field(default_factory=list)
    no_snooze_cams: List[str] = field(default_factory=list)
    
    arm_syncs: List[str] = field(default_factory=list)
    no_arm_syncs: List[str] = field(default_factory=list)
    arm_cams: List[str] = field(default_factory=list)
    no_arm_cams: List[str] = field(default_factory=list)
    
    thumbnail_cams: List[str] = field(default_factory=list)
    no_thumbnail_cams: List[str] = field(default_factory=list)
    
    # VoIP.ms settings
    voipms_message_keyword: str = "Blink"  # Not configurable via web UI
    voipms_retry_limit: int = 10  # Not configurable via web UI
    voipms_retry_delay: int = 3  # Not configurable via web UI
    voipms_sms_wait: int = 30  # Configurable via web UI
    
    # Schedule settings (configurable via web UI)
    schedule_interval_hours: int = 1
    status_log_interval: int = 60
    main_loop_sleep: int = 1
    error_recovery_sleep: int = 5
    
    # Web interface settings
    web_enabled: bool = False
    web_port: int = 8080
    web_host: str = "0.0.0.0"
    web_theme: str = "dark"  # UI theme: 'light' or 'dark'
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'AppConfig':
        """
        Create AppConfig from dictionary with defaults and validation.
        
        Args:
            config_dict: Configuration dictionary from YAML file
            
        Returns:
            AppConfig instance with values from dict or defaults
            
        Raises:
            ConfigurationError: If configuration validation fails
        """
        config = cls(
            debug_mode=config_dict.get("debug_mode", False),
            health_file=config_dict.get("health_file", "/tmp/myblink_health.json"),
            health_check_interval=config_dict.get("health_check_interval", 30),
            max_consecutive_errors=config_dict.get("max_consecutive_errors", 3),
            blink_retry_limit=config_dict.get("blink_retry_limit", 3),
            snooze_syncs=config_dict.get("snooze_syncs", []),
            no_snooze_syncs=config_dict.get("no_snooze_syncs", []),
            snooze_cams=config_dict.get("snooze_cams", []),
            no_snooze_cams=config_dict.get("no_snooze_cams", []),
            arm_syncs=config_dict.get("arm_syncs", []),
            no_arm_syncs=config_dict.get("no_arm_syncs", []),
            arm_cams=config_dict.get("arm_cams", []),
            no_arm_cams=config_dict.get("no_arm_cams", []),
            thumbnail_cams=config_dict.get("thumbnail_cams", []),
            no_thumbnail_cams=config_dict.get("no_thumbnail_cams", []),
            voipms_message_keyword=config_dict.get("voipms_message_keyword", "Blink"),
            voipms_retry_limit=config_dict.get("voipms_retry_limit", 10),
            voipms_retry_delay=config_dict.get("voipms_retry_delay", 3),
            voipms_sms_wait=config_dict.get("voipms_sms_wait", 30),
            schedule_interval_hours=config_dict.get("schedule_interval_hours", 1),
            status_log_interval=config_dict.get("status_log_interval", 60),
            main_loop_sleep=config_dict.get("main_loop_sleep", 1),
            error_recovery_sleep=config_dict.get("error_recovery_sleep", 5),
            web_enabled=config_dict.get("web_enabled", False),
            web_port=config_dict.get("web_port", 8080),
            web_host=config_dict.get("web_host", "0.0.0.0"),
            web_theme=config_dict.get("web_theme", "dark"),
        )
        
        # Validate exclusive pairs
        config._validate_exclusive_pairs()
        
        return config
    
    def _validate_exclusive_pairs(self) -> None:
        """
        Validate that items don't appear in both lists of exclusive pairs.
        
        Raises:
            ConfigurationError: If validation fails
        """
        pairs = [
            ("snooze_syncs", self.snooze_syncs, "no_snooze_syncs", self.no_snooze_syncs),
            ("snooze_cams", self.snooze_cams, "no_snooze_cams", self.no_snooze_cams),
            ("arm_syncs", self.arm_syncs, "no_arm_syncs", self.no_arm_syncs),
            ("arm_cams", self.arm_cams, "no_arm_cams", self.no_arm_cams),
            ("thumbnail_cams", self.thumbnail_cams, "no_thumbnail_cams", self.no_thumbnail_cams),
        ]
        
        for list1_name, list1, list2_name, list2 in pairs:
            conflicts = set(list1) & set(list2)
            if conflicts:
                raise ConfigurationError(
                    f"Configuration error: Items cannot appear in both {list1_name} and {list2_name}. "
                    f"Conflicting items: {', '.join(sorted(conflicts))}"
                )


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class TwoFactorAuthenticationError(AuthenticationError):
    """Raised when 2FA is required but fails."""
    pass


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


class MyBlink:
    """
    Main application class for Blink camera automation with VoIP.ms 2FA.
    
    This class manages the lifecycle of Blink camera operations including:
    - Authentication with 2FA via VoIP.ms SMS
    - Scheduled camera thumbnail updates
    - Automatic camera re-arming
    - Camera motion detection snoozing
    - Health status monitoring
    
    Configuration is loaded from YAML files specified by environment variables:
    - MYBLINK_CONFIG: Path to configuration file (settings)
    - MYBLINK_CREDS: Path to credentials file (sensitive auth data)
    
    Attributes:
        config: Application configuration settings
        credentials: Application credentials
        blink: Blink API instance
        voipms: VoIP.ms API client
        logger: Application logger
    """
    
    # Environment variable names
    CONFIG_FILE_ENV: str = "MYBLINK_CONFIG"
    CREDS_FILE_ENV: str = "MYBLINK_CREDS"
    WEB_PORT_ENV: str = "WEB_PORT"
    WEB_HOST_ENV: str = "WEB_HOST"
    
    # Default file paths (if env vars not set)
    DEFAULT_CONFIG_FILE: Path = Path("/app/config.yaml")
    DEFAULT_CREDS_FILE: Path = Path("/app/credentials.json")
    
    # Regex pattern for 2FA code extraction
    CODE_PATTERN: re.Pattern = re.compile(r"\d{6}")
    
    def __init__(self) -> None:
        """Initialize MyBlink application."""
        self.config: Optional[AppConfig] = None
        self.credentials: Optional[Credentials] = None
        self.blink: Optional[Blink] = None
        self.voipms: Optional[VoipMs] = None
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.consecutive_errors: int = 0
        self._session: Optional[ClientSession] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutdown: bool = False
        self._config_file: Path = Path(os.getenv(self.CONFIG_FILE_ENV, self.DEFAULT_CONFIG_FILE))
        self._creds_file: Path = Path(os.getenv(self.CREDS_FILE_ENV, self.DEFAULT_CREDS_FILE))
        self._web_server: Optional[Any] = None
        self._configured: bool = False
        self._web_port: int = int(os.getenv(self.WEB_PORT_ENV, "8080"))
        self._web_host: str = os.getenv(self.WEB_HOST_ENV, "0.0.0.0")
        
        # Initialize components
        self._load_config()
        self._setup_logger()
        self._load_credentials()  # Non-fatal if missing
        if self._configured:
            self._initialize_voipms()
        self._initialize_web_server()  # Always start web server
        
    def _setup_logger(self) -> None:
        """
        Configure logging system for console output.
        
        Sets up stdout logging with appropriate formatting for Docker environments.
        Log level is controlled by the debug_mode configuration setting.
        """
        if not self.config:
            # Config not loaded yet, use default
            log_level = logging.INFO
        else:
            log_level = logging.DEBUG if self.config.debug_mode else logging.INFO
        
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # Create console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.addHandler(handler)
        
        # Suppress verbose logging from third-party libraries
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        
        # Log initialization
        mode = "DEBUG" if (self.config and self.config.debug_mode) else "INFO"
        self.logger.info(f"Logging initialized at {mode} level")
        
    def _load_config(self) -> None:
        """
        Load configuration from YAML file.
        
        Loads configuration from the file specified by MYBLINK_CONFIG environment
        variable, or uses defaults if not specified.
        
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
                return
            
            if not self._config_file.exists():
                self.logger.warning(
                    f"Config file not found: {self._config_file}, using defaults"
                )
                self.config = AppConfig()
                return
            
            with open(self._config_file, 'r') as f:
                config_dict = yaml.safe_load(f) or {}
            
            self.config = AppConfig.from_dict(config_dict)
            
            self.logger.info(f"Configuration loaded from: {self._config_file}")
            
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in config file: {e}") from e
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}") from e
    
    def _load_credentials(self) -> None:
        """
        Load credentials from JSON file.
        
        Loads credentials from the file specified by MYBLINK_CREDS environment
        variable. If file doesn't exist, app starts in unconfigured mode.
        """
        try:
            # Check if path is a directory (Docker volume mount issue)
            if self._creds_file.exists() and self._creds_file.is_dir():
                self.logger.info(
                    f"Credentials path is a directory (Docker volume issue): {self._creds_file}. "
                    "Starting in setup mode - configure via web interface."
                )
                self._configured = False
                return
            
            if not self._creds_file.exists():
                self.logger.info(
                    f"Credentials file not found: {self._creds_file}. "
                    "Starting in setup mode - configure via web interface."
                )
                self._configured = False
                return
            
            with open(self._creds_file, 'r') as f:
                creds_dict = json.load(f)
            
            if not creds_dict:
                self.logger.warning("Credentials file is empty")
                self._configured = False
                return
            
            self.credentials = Credentials.from_dict(creds_dict)
            
            # Validate required fields are not empty
            if not self.credentials.blink.username or not self.credentials.blink.password:
                self.logger.warning("Blink credentials incomplete")
                self._configured = False
                return
            
            if not self.credentials.voipms.username or not self.credentials.voipms.password:
                self.logger.warning("VoIP.ms credentials incomplete")
                self._configured = False
                return
            
            if not self.credentials.voipms.did:
                self.logger.warning("VoIP.ms DID missing")
                self._configured = False
                return
            
            self._configured = True
            self.logger.info(
                f"Credentials loaded for user: {mask_email(self.credentials.blink.username)}"
            )
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in credentials file: {e}")
            self._configured = False
        except Exception as e:
            self.logger.error(f"Failed to load credentials: {e}")
            self._configured = False
    
    def _save_credentials(self) -> None:
        """
        Save credentials to JSON file.
        
        Used to persist updated Blink cached credentials.
        Logs error but does not raise exception to avoid disrupting operations.
        """
        if not self.credentials:
            self.logger.warning("Cannot save credentials: no credentials loaded")
            return
        
        try:
            # Ensure directory exists
            self._creds_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self._creds_file, 'w') as f:
                json.dump(self.credentials.to_dict(), f, indent=2)
            
            self.logger.debug("Credentials saved successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to save credentials: {e}")
    
    def set_credentials(self, creds_dict: Dict[str, Any]) -> None:
        """
        Set credentials from dictionary and initialize services.
        
        This is called by the web UI when user enters credentials.
        
        Args:
            creds_dict: Dictionary containing blink and voipms credentials
            
        Raises:
            ConfigurationError: If credentials are invalid or initialization fails
        """
        # Validate and create credentials object
        self.credentials = Credentials.from_dict(creds_dict)
        
        # Validate required fields
        if not self.credentials.blink.username or not self.credentials.blink.password:
            raise ConfigurationError("Blink username and password are required")
        
        if not self.credentials.voipms.username or not self.credentials.voipms.password:
            raise ConfigurationError("VoIP.ms username and password are required")
        
        if not self.credentials.voipms.did:
            raise ConfigurationError("VoIP.ms DID is required")
        
        # Initialize VoIP.ms client
        self._initialize_voipms()
        
        # Save credentials to file
        self._save_credentials()
        
        # Mark as configured
        self._configured = True
        
        self.logger.info(
            f"Credentials configured for user: {mask_email(self.credentials.blink.username)}"
        )
    
    def is_configured(self) -> bool:
        """Check if application is configured with credentials."""
        return self._configured
    
    def _initialize_voipms(self) -> None:
        """
        Initialize VoIP.ms API client.
        
        Raises:
            ConfigurationError: If VoIP.ms initialization fails
        """
        if not self.credentials:
            raise ConfigurationError("Credentials not loaded")
        
        try:
            self.voipms = VoipMs(
                self.credentials.voipms.username,
                self.credentials.voipms.password,
            )
            self.logger.info("VoIP.ms client initialized")
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize VoIP.ms client: {e}") from e
    
    def _initialize_web_server(self) -> None:
        """
        Initialize web server.
        
        The web server provides a PWA interface for managing cameras and setup.
        Always starts if Flask is available.
        """
        if not WEB_SERVER_AVAILABLE:
            self.logger.error(
                "Flask not available. Web interface required for configuration. "
                "Install Flask: pip install flask"
            )
            return
        
        try:
            self._web_server = WebServer(
                myblink_app=self,
                host=self._web_host,
                port=self._web_port
            )
            self.logger.info(
                f"Web server initialized (will start on {self._web_host}:{self._web_port})"
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize web server: {e}")
            self._web_server = None
    
    def update_health_status(
        self,
        status: HealthStatus,
        message: str,
        error: Optional[Exception] = None
    ) -> None:
        """
        Update health status file for external monitoring.
        
        Args:
            status: Current health status
            message: Human-readable status message
            error: Optional exception that caused status change
        """
        if not self.config:
            return
        
        try:
            # Update consecutive error counter
            if status == HealthStatus.HEALTHY:
                self.consecutive_errors = 0
            elif status == HealthStatus.UNHEALTHY:
                self.consecutive_errors += 1
            
            health_data = HealthData(
                status=status,
                timestamp=time.time(),
                message=message,
                consecutive_errors=self.consecutive_errors,
                error=str(error) if error else None
            )
            
            # Ensure directory exists
            health_file = Path(self.config.health_file)
            health_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(health_file, 'w') as f:
                json.dump(health_data.to_dict(), f, indent=2)
            
            self.logger.debug(f"Health status updated: {status.value} - {message}")
            
        except Exception as e:
            self.logger.error(f"Failed to update health status: {e}")
    
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
        if not self.credentials or not self.config:
            self.logger.error("Configuration or credentials not loaded")
            return None
        
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
    
    def _delete_blink_sms_messages(self) -> None:
        """
        Delete Blink-related SMS messages from VoIP.ms.
        
        Cleans up old 2FA messages to prevent confusion in future retrievals.
        Only deletes messages from 5-digit short codes containing the Blink keyword.
        """
        if not self.credentials or not self.voipms or not self.config:
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
    
    @asynccontextmanager
    async def _get_session(self):
        """
        Async context manager for aiohttp session lifecycle.
        
        Ensures proper cleanup of HTTP sessions and reuses session when possible.
        
        Yields:
            ClientSession: Active aiohttp session
        """
        # Reuse existing session if available and not closed
        if self._session and not self._session.closed:
            yield self._session
            return
        
        # Create new session
        self._session = ClientSession()
        try:
            yield self._session
        finally:
            # Note: We don't close here to allow reuse across operations
            # Session will be closed on shutdown
            pass
    
    async def _cleanup_session(self) -> None:
        """Close aiohttp session if open."""
        if self._session and not self._session.closed:
            await self._session.close()
            self.logger.debug("Closed aiohttp session")
            self._session = None
    
    async def _authenticate_with_cached_credentials(self, session: ClientSession) -> bool:
        """
        Attempt authentication using cached credentials.
        
        Args:
            session: Active aiohttp session
            
        Returns:
            True if authentication successful, False otherwise
        """
        if not self.credentials or not self.credentials.blink.cached_credentials:
            return False
        
        self.logger.debug("Attempting authentication with cached credentials")
        
        try:
            cached_auth = json.loads(self.credentials.blink.cached_credentials)
            self.blink = Blink(session=session)
            self.blink.auth = Auth(cached_auth, no_prompt=True, session=session)
            
            result = await self.blink.start()
            
            if self.blink.available:
                self.logger.info("Successfully authenticated with cached credentials")
                await self._verify_blink_connection()
                return True
            else:
                self.logger.debug(
                    f"Cached credentials authentication result: {result}, "
                    f"available: {self.blink.available}"
                )
                return False
                
        except BlinkTwoFARequiredError:
            self.logger.debug("Cached credentials require 2FA")
            return False
        except json.JSONDecodeError as e:
            self.logger.warning(f"Invalid cached credentials format: {e}")
            return False
        except Exception as e:
            self.logger.debug(f"Cached credentials failed: {e}")
            return False
    
    async def _authenticate_with_credentials(self, session: ClientSession) -> None:
        """
        Perform fresh authentication with username and password.
        
        Args:
            session: Active aiohttp session
            
        Raises:
            AuthenticationError: If authentication fails
        """
        if not self.credentials:
            raise ConfigurationError("Credentials not loaded")
        
        self.logger.info("Performing fresh authentication")
        
        # Clear failed cached credentials
        if self.credentials.blink.cached_credentials:
            self.credentials.blink.cached_credentials = None
            self._save_credentials()
        
        # Create Blink instance with credentials
        self.blink = Blink(session=session)
        auth_info = {
            "username": self.credentials.blink.username,
            "password": self.credentials.blink.password,
        }
        
        self.logger.debug(f"Authenticating user: {mask_email(auth_info['username'])}")
        self.blink.auth = Auth(auth_info, no_prompt=True, session=session)
        
        # Attempt authentication
        try:
            result = await self.blink.start()
            self.logger.debug(f"Authentication result: {result}, available: {self.blink.available}")
        except BlinkTwoFARequiredError:
            self.logger.debug("2FA required during initial authentication")
            # Will be handled by caller
        
        # Handle 2FA if needed
        if not self.blink.available:
            await self._handle_2fa()
        
        # Verify and save
        await self._verify_blink_connection()
        self._save_blink_credentials()
    
    async def _handle_2fa(self) -> None:
        """
        Handle 2FA authentication flow.
        
        Raises:
            TwoFactorAuthenticationError: If 2FA process fails
        """
        if not self.blink or not self.config:
            raise AuthenticationError("Blink instance or config not initialized")
        
        self.logger.info("2FA required, retrieving code from SMS")
        
        # Wait for SMS delivery
        await asyncio.sleep(self.config.voipms_sms_wait)
        
        # Get 2FA code from VoIP.ms
        code = self.get_blink_2fa_code()
        if not code:
            raise TwoFactorAuthenticationError("Failed to retrieve 2FA code from VoIP.ms")
        
        self.logger.debug(f"Retrieved 2FA code: {code}")
        
        # Complete OAuth v2 login with 2FA code
        self.logger.debug("Completing OAuth v2 login with 2FA code")
        success = await self.blink.auth.complete_2fa_login(code)
        
        if not success:
            raise TwoFactorAuthenticationError("2FA login completion failed")
        
        # Complete setup
        self.logger.debug("2FA verified, completing Blink setup")
        self.blink.setup_urls()
        await self.blink.get_homescreen()
        await self.blink.setup_post_verify()
        
        self.logger.info(f"2FA authentication complete, available: {self.blink.available}")
    
    async def _verify_blink_connection(self) -> None:
        """
        Verify Blink connection is working and devices are available.
        
        Raises:
            AuthenticationError: If connection verification fails
        """
        if not self.blink:
            raise AuthenticationError("Blink instance not initialized")
        
        if not self.blink.available:
            raise AuthenticationError("Blink service not available after authentication")
        
        if not self.blink.sync and not self.blink.cameras:
            raise AuthenticationError("No Blink devices found")
        
        device_count = len(self.blink.sync) + len(self.blink.cameras)
        self.logger.info(f"Blink connection verified: {device_count} device(s) found")
    
    def _save_blink_credentials(self) -> None:
        """Save current Blink authentication credentials to credentials file."""
        if not self.blink or not self.credentials:
            return
        
        if hasattr(self.blink.auth, 'login_attributes') and self.blink.available:
            self.credentials.blink.cached_credentials = json.dumps(
                self.blink.auth.login_attributes,
                indent=4
            )
            self._save_credentials()
            self.logger.info("Blink credentials cached")
    
    async def initialize_blink(self) -> None:
        """
        Initialize Blink API connection with 2FA support.
        
        This method attempts authentication in the following order:
        1. Try cached credentials
        2. Fall back to username/password with 2FA if needed
        
        Raises:
            AuthenticationError: If all authentication attempts fail
        """
        self.logger.info("Initializing Blink API connection")
        
        # Clean up old SMS messages first
        self._delete_blink_sms_messages()
        
        async with self._get_session() as session:
            # Try cached credentials first
            if await self._authenticate_with_cached_credentials(session):
                self.update_health_status(
                    HealthStatus.HEALTHY,
                    "Blink initialized with cached credentials"
                )
                return
            
            # Fall back to fresh authentication
            await self._authenticate_with_credentials(session)
            self.update_health_status(
                HealthStatus.HEALTHY,
                "Blink initialized successfully"
            )
        
        self.logger.info("Blink initialization complete")
    
    async def reinitialize_blink(self) -> None:
        """
        Reinitialize Blink connection after an error.
        
        This completely resets the Blink connection and re-authenticates.
        """
        self.logger.warning("Reinitializing Blink connection")
        
        # Cleanup existing resources
        await self._cleanup_session()
        self.blink = None
        
        # Reinitialize
        await self.initialize_blink()
    
    async def _execute_with_retry(
        self,
        operation: AsyncFunc[T],
        operation_name: str,
        max_retries: Optional[int] = None
    ) -> T:
        """
        Execute an async operation with automatic retry and reinitialization.
        
        Args:
            operation: Async function to execute
            operation_name: Human-readable name for logging
            max_retries: Maximum retry attempts (defaults to BLINK_RETRY_LIMIT)
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: If all retry attempts fail
        """
        if max_retries is None:
            max_retries = self.config.blink_retry_limit if self.config else 3
        
        last_exception: Optional[Exception] = None
        
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.debug(f"{operation_name}: attempt {attempt}/{max_retries}")
                result = await operation()
                return result
                
            except BlinkTwoFARequiredError as e:
                last_exception = e
                self.logger.warning(
                    f"{operation_name} failed (attempt {attempt}/{max_retries}): 2FA required"
                )
                
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"{operation_name} failed (attempt {attempt}/{max_retries}): {e}",
                    exc_info=self.DEBUG_MODE
                )
            
            # Reinitialize if not last attempt
            if attempt < max_retries:
                self.logger.info(f"Reinitializing Blink before retry {attempt + 1}")
                try:
                    await self.reinitialize_blink()
                except Exception as e:
                    self.logger.error(f"Reinitialization failed: {e}")
                    # Continue to next attempt anyway
        
        # All retries exhausted
        error_msg = f"{operation_name} failed after {max_retries} attempts"
        self.logger.error(error_msg)
        raise Exception(error_msg) from last_exception
    
    def _handle_new_devices(self) -> None:
        """
        Check for new cameras/syncs and automatically add them to no_* lists.
        
        This ensures new devices are not automatically operated on until the
        user explicitly moves them to the active list.
        """
        if not self.blink or not self.config:
            return
        
        # Get current syncs and cameras
        current_syncs = set(self.blink.sync.keys())
        current_cameras = set(self.blink.cameras.keys())
        
        # Get all known syncs from config
        known_syncs = set(self.config.snooze_syncs + self.config.no_snooze_syncs +
                         self.config.arm_syncs + self.config.no_arm_syncs)
        
        # Get all known cameras from config
        known_cameras = set(self.config.snooze_cams + self.config.no_snooze_cams +
                           self.config.arm_cams + self.config.no_arm_cams +
                           self.config.thumbnail_cams + self.config.no_thumbnail_cams)
        
        # Find new syncs and cameras
        new_syncs = current_syncs - known_syncs
        new_cameras = current_cameras - known_cameras
        
        # Add new syncs to no_* lists
        for sync_name in new_syncs:
            self.logger.info(f"New sync module detected: {sync_name} - adding to exclusion lists")
            if sync_name not in self.config.no_snooze_syncs:
                self.config.no_snooze_syncs.append(sync_name)
            if sync_name not in self.config.no_arm_syncs:
                self.config.no_arm_syncs.append(sync_name)
        
        # Add new cameras to no_* lists
        for cam_name in new_cameras:
            self.logger.info(f"New camera detected: {cam_name} - adding to exclusion lists")
            if cam_name not in self.config.no_snooze_cams:
                self.config.no_snooze_cams.append(cam_name)
            if cam_name not in self.config.no_arm_cams:
                self.config.no_arm_cams.append(cam_name)
            if cam_name not in self.config.no_thumbnail_cams:
                self.config.no_thumbnail_cams.append(cam_name)
    
    async def update_thumbnails(self) -> None:
        """
        Update camera thumbnails for all cameras.
        
        This operation captures new thumbnail images from all cameras,
        which can be used for notifications or viewing in the app.
        """
        async def _update() -> int:
            """Inner function to perform the actual update."""
            if not self.blink:
                raise AuthenticationError("Blink not initialized")
            
            # Refresh camera list to account for any added/removed cameras
            self.logger.debug("Refreshing camera list before update")
            await self.blink.refresh(force=True)
            
            # Handle newly discovered devices
            self._handle_new_devices()
            
            count = 0
            for name, camera in self.blink.cameras.items():
                # Determine if this camera should be updated
                should_update = False
                
                if self.config:
                    if self.config.thumbnail_cams:
                        # If positive list exists and is not empty, only update cameras in it
                        should_update = name in self.config.thumbnail_cams
                    elif self.config.no_thumbnail_cams:
                        # If only negative list exists, update all except those in it
                        should_update = name not in self.config.no_thumbnail_cams
                    else:
                        # If both lists are empty, update all cameras
                        should_update = True
                else:
                    # No config, update all
                    should_update = True
                
                if not should_update:
                    self.logger.debug(f"Skipping thumbnail update for camera (excluded): {name}")
                    continue
                
                camera_obj = cast(BlinkCamera, camera)
                self.logger.debug(f"Updating thumbnail for camera: {name}")
                await camera_obj.snap_picture()
                self.logger.info(f"Updated thumbnail: {name}")
                count += 1
            
            return count
        
        try:
            count = await self._execute_with_retry(_update, "update_thumbnails")
            self.logger.info(f"Successfully updated {count} thumbnail(s)")
            self.update_health_status(
                HealthStatus.HEALTHY,
                f"Updated {count} thumbnail(s)"
            )
        except Exception as e:
            self.logger.error(f"Failed to update thumbnails: {e}")
            self.update_health_status(
                HealthStatus.UNHEALTHY,
                "Failed to update thumbnails",
                e
            )
            raise
    
    async def rearm_cameras(self) -> None:
        """
        Rearm all camera sync modules.
        
        This ensures cameras are armed and will detect motion events.
        """
        async def _rearm() -> int:
            """Inner function to perform the actual rearm."""
            if not self.blink:
                raise AuthenticationError("Blink not initialized")
            
            # Refresh camera list to account for any added/removed cameras
            self.logger.debug("Refreshing camera list before rearm")
            await self.blink.refresh(force=True)
            
            # Handle newly discovered devices
            self._handle_new_devices()
            
            count = 0
            for sync_name, sync in self.blink.sync.items():
                # Determine if this sync should be rearmed
                should_rearm = False
                
                if self.config:
                    if self.config.arm_syncs:
                        # If positive list exists and is not empty, only rearm syncs in it
                        should_rearm = sync_name in self.config.arm_syncs
                    elif self.config.no_arm_syncs:
                        # If only negative list exists, rearm all except those in it
                        should_rearm = sync_name not in self.config.no_arm_syncs
                    else:
                        # If both lists are empty, rearm all syncs
                        should_rearm = True
                else:
                    # No config, rearm all
                    should_rearm = True
                
                if not should_rearm:
                    self.logger.debug(f"Skipping rearm for sync (excluded): {sync_name}")
                    continue
                
                sync_obj = cast(BlinkSyncModule, sync)
                self.logger.debug(f"Rearming sync module: {sync_name}")
                await sync_obj.async_arm(True)
                self.logger.info(f"Rearmed: {sync_name}")
                count += 1
            
            return count
        
        try:
            count = await self._execute_with_retry(_rearm, "rearm_cameras")
            self.logger.info(f"Successfully rearmed {count} sync module(s)")
            self.update_health_status(
                HealthStatus.HEALTHY,
                f"Rearmed {count} sync module(s)"
            )
        except Exception as e:
            self.logger.error(f"Failed to rearm cameras: {e}")
            self.update_health_status(
                HealthStatus.UNHEALTHY,
                "Failed to rearm cameras",
                e
            )
            raise
    
    async def snooze_cameras(self) -> None:
        """
        Snooze cameras to temporarily disable motion notifications.
        
        Excludes cameras/syncs specified in NO_SNOOZE_SYNCS and NO_SNOOZE_CAMS.
        """
        async def _snooze() -> int:
            """Inner function to perform the actual snooze."""
            if not self.blink:
                raise AuthenticationError("Blink not initialized")
            
            # Refresh camera list to account for any added/removed cameras
            self.logger.debug("Refreshing camera list before snooze")
            await self.blink.refresh(force=True)
            
            # Handle newly discovered devices
            self._handle_new_devices()
            
            count = 0
            for sync_name, sync in self.blink.sync.items():
                # Determine if this sync should be processed
                should_process_sync = False
                
                if self.config:
                    if self.config.snooze_syncs:
                        # If positive list exists and is not empty, only process syncs in it
                        should_process_sync = sync_name in self.config.snooze_syncs
                    elif self.config.no_snooze_syncs:
                        # If only negative list exists, process all except those in it
                        should_process_sync = sync_name not in self.config.no_snooze_syncs
                    else:
                        # If both lists are empty, process all syncs
                        should_process_sync = True
                else:
                    # No config, process all
                    should_process_sync = True
                
                if not should_process_sync:
                    self.logger.debug(f"Skipping sync (excluded): {sync_name}")
                    continue
                
                sync_obj = cast(BlinkSyncModule, sync)
                for camera_name, camera in sync_obj.cameras.items():
                    # Determine if this camera should be snoozed
                    should_snooze = False
                    
                    if self.config:
                        if self.config.snooze_cams:
                            # If positive list exists and is not empty, only snooze cameras in it
                            should_snooze = camera_name in self.config.snooze_cams
                        elif self.config.no_snooze_cams:
                            # If only negative list exists, snooze all except those in it
                            should_snooze = camera_name not in self.config.no_snooze_cams
                        else:
                            # If both lists are empty, snooze all cameras
                            should_snooze = True
                    else:
                        # No config, snooze all
                        should_snooze = True
                    
                    if not should_snooze:
                        self.logger.debug(f"Skipping camera (excluded): {camera_name}")
                        continue
                    
                    camera_obj = cast(BlinkCamera, camera)
                    self.logger.debug(f"Snoozing camera: {camera_name} in {sync_name}")
                    await camera_obj.async_snooze()
                    self.logger.info(f"Snoozed: {camera_name}")
                    count += 1
            
            return count
        
        try:
            count = await self._execute_with_retry(_snooze, "snooze_cameras")
            self.logger.info(f"Successfully snoozed {count} camera(s)")
            self.update_health_status(
                HealthStatus.HEALTHY,
                f"Snoozed {count} camera(s)"
            )
        except Exception as e:
            self.logger.error(f"Failed to snooze cameras: {e}")
            self.update_health_status(
                HealthStatus.UNHEALTHY,
                "Failed to snooze cameras",
                e
            )
            raise
    
    async def run_scheduled_jobs(self) -> None:
        """
        Run all scheduled maintenance jobs.
        
        Executes thumbnail updates, camera rearming, and camera snoozing
        in sequence. Designed to be called on a schedule.
        """
        self.logger.info("Running scheduled jobs")
        
        jobs = [
            ("update_thumbnails", self.update_thumbnails),
            ("rearm_cameras", self.rearm_cameras),
            ("snooze_cameras", self.snooze_cameras),
        ]
        
        for job_name, job_func in jobs:
            try:
                self.logger.debug(f"Starting job: {job_name}")
                await job_func()
                self.logger.debug(f"Completed job: {job_name}")
            except Exception as e:
                self.logger.error(f"Job {job_name} failed: {e}", exc_info=True)
                # Continue with next job even if one fails
        
        self.logger.info("Completed all scheduled jobs")
    
    async def _main_loop(self) -> None:
        """
        Main application event loop.
        
        Runs scheduled jobs at specified intervals and monitors health status.
        If not configured, waits for credentials to be entered via web UI.
        """
        self.logger.info("Starting main application loop")
        
        # Wait for configuration if not configured
        if not self._configured:
            self.logger.info("Application not configured. Waiting for credentials via web interface...")
            self.update_health_status(
                HealthStatus.DEGRADED,
                "Waiting for configuration via web interface"
            )
        
        # Initialize Blink on startup (if configured)
        if self._configured:
            try:
                await self.initialize_blink()
                # Run jobs immediately on startup
                await self.run_scheduled_jobs()
            except Exception as e:
                self.logger.error(f"Startup initialization failed: {e}", exc_info=True)
                self.update_health_status(
                    HealthStatus.UNHEALTHY,
                    "Startup initialization failed",
                    e
                )
        
        # Calculate next run time (every hour on the hour)
        now = time.time()
        seconds_past_hour = now % 3600
        next_run = now + (3600 - seconds_past_hour)
        
        if self._configured:
            self.logger.info(
                f"Next scheduled run: {datetime.fromtimestamp(next_run).strftime('%Y-%m-%d %H:%M:%S')}"
            )
        
        last_status_log = time.time()
        health_check_counter = 0
        
        while not self._shutdown:
            try:
                current_time = time.time()
                
                # If not configured, just wait
                if not self._configured:
                    if current_time - last_status_log >= 60:  # Log every minute
                        self.logger.debug("Waiting for configuration via web interface")
                        last_status_log = current_time
                        self.update_health_status(
                            HealthStatus.DEGRADED,
                            "Waiting for configuration via web interface"
                        )
                    await asyncio.sleep(5)
                    continue
                
                # Run scheduled jobs if it's time
                if current_time >= next_run:
                    await self.run_scheduled_jobs()
                    
                    # Calculate next run time
                    next_run += 3600
                    self.logger.info(
                        f"Next scheduled run: {datetime.fromtimestamp(next_run).strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                
                # Log status periodically
                time_until_next = next_run - current_time
                if self.config and current_time - last_status_log >= self.config.status_log_interval:
                    self.logger.debug(
                        f"Status: Running normally. Next job in {time_until_next:.0f}s"
                    )
                    last_status_log = current_time
                
                # Update health status periodically
                health_check_counter += 1
                if self.config and health_check_counter >= self.config.health_check_interval:
                    if self.consecutive_errors >= self.config.max_consecutive_errors:
                        self.update_health_status(
                            HealthStatus.UNHEALTHY,
                            f"Too many consecutive errors: {self.consecutive_errors}"
                        )
                    elif not self.blink:
                        self.update_health_status(
                            HealthStatus.DEGRADED,
                            "Blink not initialized"
                        )
                    else:
                        self.update_health_status(
                            HealthStatus.HEALTHY,
                            "Running normally"
                        )
                    health_check_counter = 0
                
                # Sleep
                await asyncio.sleep(self.config.main_loop_sleep if self.config else 1)
                
            except asyncio.CancelledError:
                self.logger.info("Main loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                self.update_health_status(
                    HealthStatus.UNHEALTHY,
                    "Main loop error",
                    e
                )
                await asyncio.sleep(self.config.error_recovery_sleep if self.config else 5)
    
    async def shutdown(self) -> None:
        """
        Gracefully shutdown the application.
        
        Cleans up resources and saves state.
        """
        self.logger.info("Initiating graceful shutdown")
        self._shutdown = True
        
        # Stop web server
        if self._web_server:
            try:
                self._web_server.stop()
            except Exception as e:
                self.logger.error(f"Error stopping web server: {e}")
        
        # Cleanup session
        await self._cleanup_session()
        
        # Update health status
        self.update_health_status(
            HealthStatus.UNHEALTHY,
            "Application shutting down"
        )
        
        self.logger.info("Shutdown complete")
    
    def run(self) -> None:
        """
        Run the application.
        
        This is the main entry point that sets up the event loop and runs
        the application until interrupted.
        """
        # Create and set event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        self._event_loop = loop
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            """Handle shutdown signals."""
            sig_name = signal.Signals(signum).name
            self.logger.info(f"Received signal {sig_name}, initiating shutdown")
            self._shutdown = True
            
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # Start web server if enabled
        if self._web_server:
            try:
                self._web_server.start()
            except Exception as e:
                self.logger.error(f"Failed to start web server: {e}")
                self._web_server = None
        
        try:
            # Run main loop
            loop.run_until_complete(self._main_loop())
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
        finally:
            # Shutdown gracefully
            loop.run_until_complete(self.shutdown())
            
            # Close loop
            try:
                # Cancel any remaining tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                
                # Wait for cancellation
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")
            finally:
                loop.close()
                self.logger.info("Application terminated")


def main() -> None:
    """Application entry point."""
    app = MyBlink()
    app.run()


if __name__ == "__main__":
    main()
