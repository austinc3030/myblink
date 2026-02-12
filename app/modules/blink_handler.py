"""
Blink camera integration handler for MyBlink application.

Handles authentication, camera operations, sync module management,
and device discovery for Blink security cameras.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, Optional, TypeVar, cast

from aiohttp import ClientSession
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink
from blinkpy.camera import BlinkCamera
from blinkpy.sync_module import BlinkSyncModule

from .models import Credentials, AppConfig, HealthStatus
from .exceptions import AuthenticationError, TwoFactorAuthenticationError, ConfigurationError
from .config_manager import mask_email

# Type aliases
T = TypeVar('T')
AsyncFunc = Callable[..., Awaitable[T]]

# Debug mode (for verbose logging)
DEBUG_MODE = False


class BlinkHandler:
    """
    Handles Blink camera operations and authentication.
    
    Manages Blink API connection, authentication (including 2FA), camera operations,
    sync module management, and scheduled maintenance jobs.
    """
    
    def __init__(
        self,
        credentials: Credentials,
        config: AppConfig,
        voipms_handler: Any,  # VoipMsHandler (avoiding circular import)
        health_monitor: Any,  # HealthMonitor (avoiding circular import)
        config_manager: Any,  # ConfigManager (avoiding circular import)
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize Blink handler.
        
        Args:
            credentials: Application credentials
            config: Application configuration
            voipms_handler: VoIP.ms handler for 2FA
            health_monitor: Health monitoring instance
            config_manager: Configuration manager for saving config
            logger: Logger instance (creates new one if not provided)
        """
        self.credentials = credentials
        self.config = config
        self.voipms_handler = voipms_handler
        self.health_monitor = health_monitor
        self.config_manager = config_manager
        self.logger = logger or logging.getLogger(__name__)
        
        self.blink: Optional[Blink] = None
        self._session: Optional[ClientSession] = None
    
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
    
    async def cleanup_session(self) -> None:
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
        if not self.credentials.blink.cached_credentials:
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
        self.logger.info("Performing fresh authentication")
        
        # Clear failed cached credentials
        if self.credentials.blink.cached_credentials:
            self.credentials.blink.cached_credentials = None
            self.config.blink_cached_credentials = None
            self.config_manager.save_config()
        
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
        if not self.blink:
            raise AuthenticationError("Blink instance not initialized")
        
        self.logger.info("2FA required, retrieving code from SMS")
        
        # Wait for SMS delivery
        await asyncio.sleep(self.config.voipms_sms_wait)
        
        # Get 2FA code from VoIP.ms
        code = self.voipms_handler.get_blink_2fa_code()
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
        """Save current Blink authentication credentials to config file."""
        if not self.blink:
            return
        
        if hasattr(self.blink.auth, 'login_attributes') and self.blink.available:
            self.credentials.blink.cached_credentials = json.dumps(
                self.blink.auth.login_attributes,
                indent=4
            )
            self.config.blink_cached_credentials = self.credentials.blink.cached_credentials
            self.config_manager.save_config()
            self.logger.info("Blink credentials cached")
    
    async def initialize(self) -> None:
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
        self.voipms_handler.delete_blink_sms_messages()
        
        async with self._get_session() as session:
            # Try cached credentials first
            if await self._authenticate_with_cached_credentials(session):
                self.health_monitor.update_status(
                    HealthStatus.HEALTHY,
                    "Blink initialized with cached credentials"
                )
                return
            
            # Fall back to fresh authentication
            await self._authenticate_with_credentials(session)
            self.health_monitor.update_status(
                HealthStatus.HEALTHY,
                "Blink initialized successfully"
            )
        
        self.logger.info("Blink initialization complete")
    
    async def reinitialize(self) -> None:
        """
        Reinitialize Blink connection after an error.
        
        This completely resets the Blink connection and re-authenticates.
        """
        self.logger.warning("Reinitializing Blink connection")
        
        # Cleanup existing resources
        await self.cleanup_session()
        self.blink = None
        
        # Reinitialize
        await self.initialize()
    
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
            max_retries: Maximum retry attempts (defaults to config.blink_retry_limit)
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: If all retry attempts fail
        """
        if max_retries is None:
            max_retries = self.config.blink_retry_limit
        
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
                    exc_info=DEBUG_MODE
                )
            
            # Reinitialize if not last attempt
            if attempt < max_retries:
                self.logger.info(f"Reinitializing Blink before retry {attempt + 1}")
                try:
                    await self.reinitialize()
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
        if not self.blink:
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
                
                if self.config.thumbnail_cams:
                    # If positive list exists and is not empty, only update cameras in it
                    should_update = name in self.config.thumbnail_cams
                elif self.config.no_thumbnail_cams:
                    # If only negative list exists, update all except those in it
                    should_update = name not in self.config.no_thumbnail_cams
                else:
                    # If both lists are empty, update all cameras
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
            self.health_monitor.update_status(
                HealthStatus.HEALTHY,
                f"Updated {count} thumbnail(s)"
            )
        except Exception as e:
            self.logger.error(f"Failed to update thumbnails: {e}")
            self.health_monitor.update_status(
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
                
                if self.config.arm_syncs:
                    # If positive list exists and is not empty, only rearm syncs in it
                    should_rearm = sync_name in self.config.arm_syncs
                elif self.config.no_arm_syncs:
                    # If only negative list exists, rearm all except those in it
                    should_rearm = sync_name not in self.config.no_arm_syncs
                else:
                    # If both lists are empty, rearm all syncs
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
            self.health_monitor.update_status(
                HealthStatus.HEALTHY,
                f"Rearmed {count} sync module(s)"
            )
        except Exception as e:
            self.logger.error(f"Failed to rearm cameras: {e}")
            self.health_monitor.update_status(
                HealthStatus.UNHEALTHY,
                "Failed to rearm cameras",
                e
            )
            raise
    
    async def snooze_cameras(self) -> None:
        """
        Snooze cameras to temporarily disable motion notifications.
        
        Applies to cameras specified in config lists.
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
                
                if self.config.snooze_syncs:
                    # If positive list exists and is not empty, only process syncs in it
                    should_process_sync = sync_name in self.config.snooze_syncs
                elif self.config.no_snooze_syncs:
                    # If only negative list exists, process all except those in it
                    should_process_sync = sync_name not in self.config.no_snooze_syncs
                else:
                    # If both lists are empty, process all syncs
                    should_process_sync = True
                
                if not should_process_sync:
                    self.logger.debug(f"Skipping sync (excluded): {sync_name}")
                    continue
                
                sync_obj = cast(BlinkSyncModule, sync)
                for camera_name, camera in sync_obj.cameras.items():
                    # Determine if this camera should be snoozed
                    should_snooze = False
                    
                    if self.config.snooze_cams:
                        # If positive list exists and is not empty, only snooze cameras in it
                        should_snooze = camera_name in self.config.snooze_cams
                    elif self.config.no_snooze_cams:
                        # If only negative list exists, snooze all except those in it
                        should_snooze = camera_name not in self.config.no_snooze_cams
                    else:
                        # If both lists are empty, snooze all cameras
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
            self.health_monitor.update_status(
                HealthStatus.HEALTHY,
                f"Snoozed {count} camera(s)"
            )
        except Exception as e:
            self.logger.error(f"Failed to snooze cameras: {e}")
            self.health_monitor.update_status(
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
