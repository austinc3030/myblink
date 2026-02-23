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
        history_manager: Any = None,  # HistoryManager (avoiding circular import)
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
            history_manager: History manager for recording metrics
            logger: Logger instance (creates new one if not provided)
        """
        self.credentials = credentials
        self.config = config
        self.voipms_handler = voipms_handler
        self.health_monitor = health_monitor
        self.config_manager = config_manager
        self.history_manager = history_manager
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
            TwoFactorAuthenticationError: If 2FA process fails or in interactive mode
        """
        if not self.blink:
            raise AuthenticationError("Blink instance not initialized")
        
        # Check if we're in interactive mode (no VoIP.ms handler)
        if not self.voipms_handler:
            self.logger.info("2FA required in interactive mode - waiting for user input")
            raise TwoFactorAuthenticationError("2FA code required - please provide code interactively")
        
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
            # Log more details about why it's not available
            sync_count = len(self.blink.sync) if self.blink.sync else 0
            camera_count = len(self.blink.cameras) if self.blink.cameras else 0
            self.logger.error(
                f"Blink not available - sync: {sync_count}, cameras: {camera_count}"
            )
            # Don't fail if available flag is False but we actually have successful auth
            # Some accounts may have networks with no cameras
            self.logger.warning("Continuing despite available=False (authentication succeeded)")
        
        # Verification passes if authentication succeeded, even with no devices
        # Some users have networks/sync modules without cameras
        self.logger.info("Blink connection verified - authentication successful")
    
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
            TwoFactorAuthenticationError: If 2FA is required and in interactive mode
        """
        self.logger.info("Initializing Blink API connection")
        
        # Clean up old SMS messages first (only if VoIP.ms handler available)
        if self.voipms_handler:
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
        Note: We don't close the old session explicitly to avoid 'Session is closed'
        errors if operations are still in progress. The old session will be garbage
        collected once all references are released.
        """
        self.logger.warning("Reinitializing Blink connection")
        
        # Clear existing Blink instance
        self.blink = None
        
        # Mark session for replacement (don't close it - let it be cleaned up naturally)
        # This ensures initialize() creates a fresh session
        old_session = self._session
        self._session = None
        
        # Reinitialize with fresh session
        await self.initialize()
        
        # Close old session after new one is established
        if old_session and not old_session.closed:
            try:
                await old_session.close()
                self.logger.debug("Closed old session after reinitialize")
            except Exception as e:
                self.logger.debug(f"Failed to close old session (already closed or in use): {e}")
    
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
        in sequence. Also records camera metrics (battery, status) if history manager is available.
        Designed to be called on a schedule.
        """
        self.logger.info("Running scheduled jobs")
        
        jobs = [
            ("update_thumbnails", self.update_thumbnails),
            ("rearm_cameras", self.rearm_cameras),
            ("snooze_cameras", self.snooze_cameras),
            ("record_camera_metrics", self.record_camera_metrics),
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
    
    async def record_camera_metrics(self) -> None:
        """
        Record battery and status metrics for all cameras.
        
        Captures current battery voltage and online/offline status for each camera
        and stores in history database. Called as part of scheduled jobs.
        """
        if not self.history_manager:
            self.logger.debug("History manager not available, skipping metrics recording")
            return
        
        if not self.blink or not self.blink.sync:
            self.logger.debug("Blink not initialized, skipping metrics recording")
            return
        
        try:
            self.logger.debug("Recording camera metrics")
            
            for sync_name, sync_module in self.blink.sync.items():
                # Record sync module status
                try:
                    # Sync is online if it has available attribute set to True
                    is_sync_online = getattr(sync_module, 'available', False)
                    
                    from .db_models import CameraStatus
                    sync_status = CameraStatus.ONLINE if is_sync_online else CameraStatus.OFFLINE
                    
                    self.history_manager.record_status(
                        camera_name=sync_name,  # Use sync name as camera_name (status_history table accepts any device name)
                        status=sync_status
                    )
                    self.logger.debug(f"Recorded status for sync '{sync_name}': {sync_status.value}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to record metrics for sync {sync_name}: {e}")
                
                # Record camera metrics
                if not hasattr(sync_module, 'cameras'):
                    continue
                
                for camera_name, camera in sync_module.cameras.items():
                    try:
                        # Record battery level if available
                        if hasattr(camera, 'battery_voltage') and camera.battery_voltage is not None:
                            # Get battery level (percentage) if available
                            battery_level = getattr(camera, 'battery_level', None) or 50  # Default to 50% if not available
                            
                            self.history_manager.record_battery_level(
                                camera_name=camera_name,
                                battery_level=battery_level,
                                voltage=camera.battery_voltage
                            )
                            self.logger.debug(f"Recorded battery for {camera_name}: {battery_level}% / {camera.battery_voltage/100:.2f}V")
                        
                        # Record online/offline status
                        # Camera is online if it has wifi_strength (better indicator than motion_enabled)
                        is_online = False
                        if hasattr(camera, 'wifi_strength') and camera.wifi_strength is not None:
                            is_online = True
                        elif hasattr(camera, 'battery_level') and camera.battery_level is not None:
                            # Fallback: if we have battery level, camera is probably online
                            is_online = True
                        
                        from .db_models import CameraStatus
                        status = CameraStatus.ONLINE if is_online else CameraStatus.OFFLINE
                        
                        self.history_manager.record_status(
                            camera_name=camera_name,
                            status=status
                        )
                        self.logger.debug(f"Recorded status for {camera_name}: {status.value}")
                        
                    except Exception as e:
                        self.logger.error(f"Failed to record metrics for camera {camera_name}: {e}")
                        # Continue with next camera
            
            self.logger.debug("Completed recording camera and sync metrics")
            
        except Exception as e:
            self.logger.error(f"Failed to record camera metrics: {e}", exc_info=True)
    
    # ========== Helper methods for schedule executor ==========
    
    def _find_camera_in_blink(self, camera_name: str):
        """Find camera object in Blink instance by name."""
        if not self.blink or not self.blink.sync:
            return None
        
        for sync_name, sync_module in self.blink.sync.items():
            if hasattr(sync_module, 'cameras') and camera_name in sync_module.cameras:
                return sync_module.cameras[camera_name]
        
        return None
    
    def _find_sync_in_blink(self, sync_name: str):
        """Find sync module object in Blink instance by name."""
        if not self.blink or not self.blink.sync:
            return None
        
        return self.blink.sync.get(sync_name)
    
    async def set_camera_motion_detect(self, camera_name: str, enable: bool) -> bool:
        """
        Enable or disable motion detection for a camera.
        
        Args:
            camera_name: Name of camera
            enable: True to enable, False to disable
            
        Returns:
            True if successful
        """
        camera = self._find_camera_in_blink(camera_name)
        
        if not camera:
            self.logger.error(f"Camera '{camera_name}' not found")
            return False
        
        try:
            if enable:
                response = await camera.async_arm(True)
                self.logger.info(f"Enabled motion detection for '{camera_name}'")
            else:
                response = await camera.async_arm(False)
                self.logger.info(f"Disabled motion detection for '{camera_name}'")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to set motion detection for '{camera_name}': {e}")
            return False
    
    async def capture_thumbnail(self, camera_name: str) -> bool:
        """
        Capture a new thumbnail for a camera.
        
        Args:
            camera_name: Name of camera
            
        Returns:
            True if successful
        """
        camera = self._find_camera_in_blink(camera_name)
        
        if not camera:
            self.logger.error(f"Camera '{camera_name}' not found")
            return False
        
        try:
            await camera.snap_picture()
            self.logger.info(f"Captured thumbnail for '{camera_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to capture thumbnail for '{camera_name}': {e}")
            return False
    
    async def set_sync_arm(self, sync_name: str, enable: bool) -> bool:
        """
        Enable or disable arm for entire sync module.
        
        Args:
            sync_name: Name of sync module
            enable: True to enable (arm), False to disable (snooze)
            
        Returns:
            True if successful
        """
        sync = self._find_sync_in_blink(sync_name)
        
        if not sync:
            self.logger.error(f"Sync module '{sync_name}' not found")
            return False
        
        try:
            if enable:
                await sync.async_arm(True)
                # Update local state
                if sync.network_info and 'network' in sync.network_info:
                    sync.network_info['network']['armed'] = True
                self.logger.info(f"Armed sync module '{sync_name}'")
            else:
                await sync.async_arm(False)
                # Update local state
                if sync.network_info and 'network' in sync.network_info:
                    sync.network_info['network']['armed'] = False
                self.logger.info(f"Disarmed (snoozed) sync module '{sync_name}'")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to set arm for sync '{sync_name}': {e}")
            return False    
    async def unsnooze_camera(self, camera_name: str) -> bool:
        """
        Un-snooze a camera by disarming and re-arming its sync module.
        
        Args:
            camera_name: Name of camera to un-snooze
            
        Returns:
            True if successful
        """
        camera = self._find_camera_in_blink(camera_name)
        
        if not camera:
            self.logger.error(f"Camera '{camera_name}' not found")
            return False
        
        # Find the sync module for this camera
        sync = None
        for s in self.blink.sync.values():
            if camera_name in [c.name for c in s.cameras]:
                sync = s
                break
        
        if not sync:
            self.logger.error(f"Sync module for camera '{camera_name}' not found")
            return False
        
        try:
            # Disarm and re-arm the sync to un-snooze the camera
            await sync.async_arm(False)
            # Update local state
            if sync.network_info and 'network' in sync.network_info:
                sync.network_info['network']['armed'] = False
            await asyncio.sleep(2)
            await sync.async_arm(True)
            # Update local state
            if sync.network_info and 'network' in sync.network_info:
                sync.network_info['network']['armed'] = True
            
            self.logger.info(f"Un-snoozed camera '{camera_name}' by cycling its sync module")
            return True
        except Exception as e:
            self.logger.error(f"Failed to un-snooze camera '{camera_name}': {e}")
            return False
    
    async def unsnooze_sync(self, sync_name: str) -> bool:
        """
        Un-snooze a sync module by disarming and re-arming it.
        
        Args:
            sync_name: Name of sync module to un-snooze
            
        Returns:
            True if successful
        """
        sync = self._find_sync_in_blink(sync_name)
        
        if not sync:
            self.logger.error(f"Sync module '{sync_name}' not found")
            return False
        
        try:
            # Disarm and re-arm to un-snooze
            await sync.async_arm(False)
            # Update local state
            if sync.network_info and 'network' in sync.network_info:
                sync.network_info['network']['armed'] = False
            await asyncio.sleep(2)
            await sync.async_arm(True)
            # Update local state
            if sync.network_info and 'network' in sync.network_info:
                sync.network_info['network']['armed'] = True
            
            self.logger.info(f"Un-snoozed sync module '{sync_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to un-snooze sync '{sync_name}': {e}")
            return False