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
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Import web server (optional dependency)
try:
    from web_server import WebServer
    WEB_SERVER_AVAILABLE = True
except ImportError:
    WebServer = None
    WEB_SERVER_AVAILABLE = False

# Import our modular components
from modules import (
    AppConfig,
    Credentials,
    HealthStatus,
    ConfigurationError,
    AuthenticationError,
    ConfigManager,
    HealthMonitor,
    VoipMsHandler,
    BlinkHandler,
)


class MyBlink:
    """
    Main application class for Blink camera automation with VoIP.ms 2FA.
    
    This class orchestrates all application components including:
    - Configuration and credential management
    - Health monitoring
    - VoIP.ms 2FA integration
    - Blink camera operations
    - Web interface (if available)
    - Scheduled maintenance jobs
    
    Configuration is loaded from YAML files specified by environment variables:
    - MYBLINK_CONFIG: Path to configuration file
    
    Credentials can be provided via:
    - Environment variables (highest priority)
    - Config file
    - Web interface
    """
    
    # Environment variable names
    WEB_PORT_ENV = "WEB_PORT"
    WEB_HOST_ENV = "WEB_HOST"
    
    # Defaults
    DEFAULT_WEB_PORT = 8080
    DEFAULT_WEB_HOST = "0.0.0.0"
    
    def __init__(self) -> None:
        """Initialize MyBlink application."""
        self.logger = logging.getLogger(__name__)
        self._shutdown = False
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._web_server: Optional[Any] = None
        self._web_port = int(os.getenv(self.WEB_PORT_ENV, self.DEFAULT_WEB_PORT))
        self._web_host = os.getenv(self.WEB_HOST_ENV, self.DEFAULT_WEB_HOST)
        
        # Initialize configuration manager
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        
        # Setup logging
        self._setup_logger()
        
        # Load credentials (non-fatal if missing)
        self.credentials, self._configured = self.config_manager.load_credentials()
        
        # Initialize components (only if configured)
        self.health_monitor: Optional[HealthMonitor] = None
        self.voipms_handler: Optional[VoipMsHandler] = None
        self.blink_handler: Optional[BlinkHandler] = None
        self.media_manager: Optional[Any] = None
        
        if self._configured:
            self._initialize_handlers()
        
        # Always initialize web server
        self._initialize_web_server()
    
    def _setup_logger(self) -> None:
        """
        Configure logging system for console output.
        
        Sets up stdout logging with appropriate formatting for Docker environments.
        Log level is controlled by the debug_mode configuration setting.
        """
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
        mode = "DEBUG" if self.config.debug_mode else "INFO"
        self.logger.info(f"Logging initialized at {mode} level")
    
    def _initialize_handlers(self) -> None:
        """Initialize application handlers (requires credentials)."""
        if not self.credentials:
            return
        
        # Initialize health monitor
        self.health_monitor = HealthMonitor(self.config, self.logger)
        
        # Initialize VoIP.ms handler only if credentials provided (for automated 2FA)
        self.voipms_handler = None
        if self.credentials.voipms:
            self.voipms_handler = VoipMsHandler(
                self.credentials,
                self.config,
                self.logger
            )
            self.logger.info("VoIP.ms handler initialized for automated 2FA")
        else:
            self.logger.info("VoIP.ms handler not initialized (interactive 2FA mode)")
        
        # Initialize Blink handler
        self.blink_handler = BlinkHandler(
            self.credentials,
            self.config,
            self.voipms_handler,
            self.health_monitor,
            self.config_manager,
            self.logger
        )
        
        # Initialize media manager
        self.media_manager = self._initialize_media_manager()
        
        self.logger.info("Application handlers initialized")
    
    def _initialize_media_manager(self) -> Optional[Any]:
        """
        Initialize media download manager.
        
        Returns:
            MediaManager instance or None if initialization fails
        """
        try:
            from modules.media_manager import MediaManager, MediaDownloadConfig
            
            # Get media config from app config
            media_config_dict = self.config.get_media_config()
            media_config = MediaDownloadConfig.from_dict(media_config_dict)
            
            # Create media manager
            manager = MediaManager(
                self.blink_handler,
                media_config,
                self.logger
            )
            
            if media_config.enabled:
                self.logger.info("Media manager initialized and enabled")
            else:
                self.logger.info("Media manager initialized but disabled")
            
            return manager
            
        except Exception as e:
            self.logger.error(f"Failed to initialize media manager: {e}", exc_info=True)
            return None
    
    def _initialize_web_server(self) -> None:
        """
        Initialize web server.
        
        The web server provides a PWA interface for managing cameras and setup.
        Always starts if Flask is available.
        """
        if not WEB_SERVER_AVAILABLE:
            self.logger.error(
                "Web server not available - Flask not installed. "
                "Install Flask to enable web interface."
            )
            return
        
        try:
            # Create web server instance
            self._web_server = WebServer(
                myblink_app=self,
                host=self._web_host,
                port=self._web_port
            )
            self.logger.info(
                f"Web server initialized on {self._web_host}:{self._web_port}"
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize web server: {e}")
            self._web_server = None
    
    def set_credentials(self, creds_dict: dict) -> None:
        """
        Set credentials from dictionary and initialize services.
        
        This is called by the web UI when user enters credentials.
        
        Args:
            creds_dict: Dictionary containing blink and voipms credentials
            
        Raises:
            ConfigurationError: If credentials are invalid or initialization fails
        """
        # Set credentials via config manager
        self.credentials = self.config_manager.set_credentials(creds_dict)
        self._configured = True
        
        # Initialize handlers now that we have credentials
        self._initialize_handlers()
        
        self.logger.info("Credentials configured successfully")
    
    def is_configured(self) -> bool:
        """Check if application is properly configured with credentials."""
        return self._configured
    
    def get_config(self) -> AppConfig:
        """Get application configuration."""
        return self.config
    
    def get_blink_handler(self) -> Optional[BlinkHandler]:
        """Get Blink handler instance."""
        return self.blink_handler
    
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
            if self.health_monitor:
                self.health_monitor.update_status(
                    HealthStatus.DEGRADED,
                    "Waiting for configuration via web interface"
                )
        
        # Initialize Blink on startup (if configured)
        if self._configured and self.blink_handler:
            try:
                await self.blink_handler.initialize()
                # Run jobs immediately on startup
                await self.blink_handler.run_scheduled_jobs()
            except Exception as e:
                # Import exception types
                from modules.exceptions import TwoFactorAuthenticationError
                
                # For interactive 2FA mode, this is expected - user needs to provide code via web UI
                if isinstance(e, TwoFactorAuthenticationError):
                    self.logger.info("Interactive 2FA required - waiting for user to complete authentication via web interface")
                    if self.health_monitor:
                        self.health_monitor.update_status(
                            HealthStatus.DEGRADED,
                            "Waiting for 2FA authentication via web interface"
                        )
                else:
                    # Other errors are actual problems
                    self.logger.error(f"Startup initialization failed: {e}", exc_info=True)
                    if self.health_monitor:
                        self.health_monitor.update_status(
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
                        if self.health_monitor:
                            self.health_monitor.update_status(
                                HealthStatus.DEGRADED,
                                "Waiting for configuration via web interface"
                            )
                    await asyncio.sleep(5)
                    continue
                
                # Run scheduled jobs if it's time
                if current_time >= next_run and self.blink_handler:
                    await self.blink_handler.run_scheduled_jobs()
                    
                    # Calculate next run time
                    next_run += 3600
                    self.logger.info(
                        f"Next scheduled run: {datetime.fromtimestamp(next_run).strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                
                # Log status periodically
                time_until_next = next_run - current_time
                if current_time - last_status_log >= self.config.status_log_interval:
                    self.logger.debug(
                        f"Status: Running normally. Next job in {time_until_next:.0f}s"
                    )
                    last_status_log = current_time
                
                # Update health status periodically
                health_check_counter += 1
                if self.health_monitor and health_check_counter >= self.config.health_check_interval:
                    if not self.health_monitor.is_healthy():
                        self.health_monitor.update_status(
                            HealthStatus.UNHEALTHY,
                            f"Too many consecutive errors: {self.health_monitor.get_consecutive_errors()}"
                        )
                    elif not self.blink_handler or not self.blink_handler.blink:
                        self.health_monitor.update_status(
                            HealthStatus.DEGRADED,
                            "Blink not initialized"
                        )
                    else:
                        self.health_monitor.update_status(
                            HealthStatus.HEALTHY,
                            "Running normally"
                        )
                    health_check_counter = 0
                
                # Sleep
                await asyncio.sleep(self.config.main_loop_sleep)
                
            except asyncio.CancelledError:
                self.logger.info("Main loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                if self.health_monitor:
                    self.health_monitor.update_status(
                        HealthStatus.UNHEALTHY,
                        "Main loop error",
                        e
                    )
                await asyncio.sleep(self.config.error_recovery_sleep)
    
    async def shutdown(self) -> None:
        """
        Gracefully shutdown the application.
        
        Cleans up resources and saves state.
        """
        self.logger.info("Initiating graceful shutdown")
        self._shutdown = True
        
        # Stop media manager
        if hasattr(self, 'media_manager') and self.media_manager:
            try:
                self.media_manager.stop()
            except Exception as e:
                self.logger.error(f"Error stopping media manager: {e}")
        
        # Stop web server
        if self._web_server:
            try:
                self._web_server.stop()
            except Exception as e:
                self.logger.error(f"Error stopping web server: {e}")
        
        # Cleanup Blink session
        if self.blink_handler:
            try:
                await self.blink_handler.cleanup_session()
            except Exception as e:
                self.logger.error(f"Error cleaning up Blink session: {e}")
        
        # Update health status
        if self.health_monitor:
            self.health_monitor.update_status(
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
        # Create new event loop
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
        
        # Start media manager if enabled and configured
        if hasattr(self, 'media_manager') and self.media_manager and self.media_manager.config.enabled:
            try:
                self.media_manager.start(loop)
            except Exception as e:
                self.logger.error(f"Failed to start media manager: {e}")
        
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
