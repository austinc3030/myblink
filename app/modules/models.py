"""
Data models for MyBlink application.

Contains all dataclasses and enums used throughout the application for
configuration, credentials, and health monitoring.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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
    voipms: Optional[VoipMsCredentials] = None
    
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
            
            # VoIP.ms credentials are optional (for interactive 2FA mode)
            voipms_creds = None
            if "voipms" in creds_dict:
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
        result = {
            "blink": {
                "username": self.blink.username,
                "password": self.blink.password,
                "cached_credentials": self.blink.cached_credentials
            }
        }
        
        # Only include voipms if it exists
        if self.voipms:
            result["voipms"] = {
                "username": self.voipms.username,
                "password": self.voipms.password,
                "did": self.voipms.did
            }
        
        return result


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
    web_time_format: str = "12h"  # Time format: '12h' or '24h'
    
    # Authentication settings
    auth_enabled: bool = False
    auth_method: str = "basic"  # "basic" or "oidc"
    auth_session_timeout: int = 480  # Session timeout in minutes (8 hours)
    auth_basic_username: str = "admin"
    auth_basic_password_hash: str = ""  # bcrypt hash
    auth_oidc_client_id: str = ""
    auth_oidc_client_secret: str = ""
    auth_oidc_server_metadata_url: str = ""
    auth_oidc_redirect_uri: str = ""
    auth_oidc_allowed_emails: List[str] = field(default_factory=list)
    auth_oidc_allowed_domains: List[str] = field(default_factory=list)
    
    # Credentials (stored in config for easy web UI editing)
    blink_username: str = ""
    blink_password: str = ""
    
    # Media download settings (configurable via web UI)
    media_download_enabled: bool = False
    media_download_clips: bool = True
    media_download_thumbnails: bool = True
    media_download_base_path: str = "/app/media"
    media_retention_type: str = "count"  # "count", "days", or "size"
    media_retention_count: int = 100
    media_retention_days: int = 30
    media_retention_size_gb: float = 10.0
    media_use_nas: bool = False
    media_nas_type: str = "smb"  # "smb" or "nfs"
    media_nas_host: str = ""
    media_nas_share: str = ""
    media_nas_username: str = ""
    media_nas_password: str = ""
    media_nas_mount_point: str = "/mnt/nas"
    media_check_interval_minutes: int = 5
    blink_cached_credentials: Optional[str] = None
    voipms_username: str = ""
    voipms_password: str = ""
    voipms_did: str = ""
    
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
        from .exceptions import ConfigurationError
        
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
            web_time_format=config_dict.get("web_time_format", "12h"),
            auth_enabled=config_dict.get("auth_enabled", False),
            auth_method=config_dict.get("auth_method", "basic"),
            auth_session_timeout=config_dict.get("auth_session_timeout", 480),
            auth_basic_username=config_dict.get("auth_basic_username", "admin"),
            auth_basic_password_hash=config_dict.get("auth_basic_password_hash", ""),
            auth_oidc_client_id=config_dict.get("auth_oidc_client_id", ""),
            auth_oidc_client_secret=config_dict.get("auth_oidc_client_secret", ""),
            auth_oidc_server_metadata_url=config_dict.get("auth_oidc_server_metadata_url", ""),
            auth_oidc_redirect_uri=config_dict.get("auth_oidc_redirect_uri", ""),
            auth_oidc_allowed_emails=config_dict.get("auth_oidc_allowed_emails", []),
            auth_oidc_allowed_domains=config_dict.get("auth_oidc_allowed_domains", []),
            blink_username=config_dict.get("blink_username", ""),
            blink_password=config_dict.get("blink_password", ""),
            blink_cached_credentials=config_dict.get("blink_cached_credentials"),
            voipms_username=config_dict.get("voipms_username", ""),
            voipms_password=config_dict.get("voipms_password", ""),
            voipms_did=config_dict.get("voipms_did", ""),
            media_download_enabled=config_dict.get("media_download_enabled", False),
            media_download_clips=config_dict.get("media_download_clips", True),
            media_download_thumbnails=config_dict.get("media_download_thumbnails", True),
            media_download_base_path=config_dict.get("media_download_base_path", "/app/media"),
            media_retention_type=config_dict.get("media_retention_type", "count"),
            media_retention_count=config_dict.get("media_retention_count", 100),
            media_retention_days=config_dict.get("media_retention_days", 30),
            media_retention_size_gb=config_dict.get("media_retention_size_gb", 10.0),
            media_use_nas=config_dict.get("media_use_nas", False),
            media_nas_type=config_dict.get("media_nas_type", "smb"),
            media_nas_host=config_dict.get("media_nas_host", ""),
            media_nas_share=config_dict.get("media_nas_share", ""),
            media_nas_username=config_dict.get("media_nas_username", ""),
            media_nas_password=config_dict.get("media_nas_password", ""),
            media_nas_mount_point=config_dict.get("media_nas_mount_point", "/mnt/nas"),
            media_check_interval_minutes=config_dict.get("media_check_interval_minutes", 15),
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
        from .exceptions import ConfigurationError
        
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
    
    def get_auth_config(self) -> Dict[str, Any]:
        """
        Convert authentication settings to AuthConfig dictionary.
        
        Returns:
            Dictionary that can be passed to AuthConfig.from_dict()
        """
        if not self.auth_enabled:
            return {"enabled": False}
        
        auth_dict = {
            "enabled": True,
            "method": self.auth_method,
            "session_timeout_minutes": self.auth_session_timeout
        }
        
        if self.auth_method == "basic":
            auth_dict["basic"] = {
                "username": self.auth_basic_username,
                "password": self.auth_basic_password_hash  # Already hashed
            }
        elif self.auth_method == "oidc":
            auth_dict["oidc"] = {
                "client_id": self.auth_oidc_client_id,
                "client_secret": self.auth_oidc_client_secret,
                "server_metadata_url": self.auth_oidc_server_metadata_url,
                "redirect_uri": self.auth_oidc_redirect_uri or None,
                "allowed_emails": self.auth_oidc_allowed_emails,
                "allowed_domains": self.auth_oidc_allowed_domains
            }
        
        return auth_dict
    
    def get_media_config(self) -> Dict[str, Any]:
        """
        Convert media download settings to dictionary.
        
        Returns:
            Dictionary for MediaDownloadConfig
        """
        return {
            "enabled": self.media_download_enabled,
            "download_clips": self.media_download_clips,
            "download_thumbnails": self.media_download_thumbnails,
            "base_path": self.media_download_base_path,
            "retention_type": self.media_retention_type,
            "retention_count": self.media_retention_count,
            "retention_days": self.media_retention_days,
            "retention_size_gb": self.media_retention_size_gb,
            "use_nas": self.media_use_nas,
            "nas_type": self.media_nas_type,
            "nas_host": self.media_nas_host,
            "nas_share": self.media_nas_share,
            "nas_username": self.media_nas_username,
            "nas_password": self.media_nas_password,
            "nas_mount_point": self.media_nas_mount_point,
            "check_interval_minutes": self.media_check_interval_minutes,
        }
