"""
MyBlink application modules.

This package contains modular components for the MyBlink application:
- models: Data models and configuration
- exceptions: Custom exception classes
- config_manager: Configuration and credential management
- health_monitor: Health status monitoring
- voipms_handler: VoIP.ms 2FA integration
- blink_handler: Blink camera operations
- auth: Authentication and authorization
- db_models: Database models for historical data
- history_manager: Database operations for time-series data
"""

from .models import (
    HealthStatus,
    HealthData,
    BlinkCredentials,
    VoipMsCredentials,
    Credentials,
    AppConfig,
)
from .exceptions import (
    ConfigurationError,
    AuthenticationError,
    TwoFactorAuthenticationError,
)
from .config_manager import ConfigManager
from .health_monitor import HealthMonitor
from .voipms_handler import VoipMsHandler
from .blink_handler import BlinkHandler
from .auth import (
    AuthConfig,
    BasicAuthConfig,
    OIDCConfig,
    AuthManager,
    User,
)
from .db_models import (
    ScheduleAction,
    ScheduleTarget,
    CameraStatus,
    ScheduledRule,
    BatteryRecord,
    StatusRecord,
    MediaDownloadRecord,
)
from .history_manager import HistoryManager
from .schedule_executor import ScheduleExecutor

__all__ = [
    # Models
    "HealthStatus",
    "HealthData",
    "BlinkCredentials",
    "VoipMsCredentials",
    "Credentials",
    "AppConfig",
    # Exceptions
    "ConfigurationError",
    "AuthenticationError",
    "TwoFactorAuthenticationError",
    # Managers
    "ConfigManager",
    "HealthMonitor",
    "VoipMsHandler",
    "BlinkHandler",
    # Authentication
    "AuthConfig",
    "BasicAuthConfig",
    "OIDCConfig",
    "AuthManager",
    "User",
    # Database models
    "ScheduleAction",
    "ScheduleTarget",
    "CameraStatus",
    "ScheduledRule",
    "BatteryRecord",
    "StatusRecord",
    "MediaDownloadRecord",
    "HistoryManager",
    "ScheduleExecutor",
]
