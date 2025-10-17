"""Blink camera automation with VoIP.ms 2FA integration."""

import asyncio
import functools
import json
import logging
import os
import re
import schedule
import sys
import time
from datetime import datetime
from functools import wraps
from logging.handlers import RotatingFileHandler

from aiohttp import ClientSession
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink
from voipms import VoipMs


def mask_email(email):
    """Mask email address for logging purposes."""
    if not email or '@' not in email:
        return email
    local, domain = email.split('@', 1)
    # Show first 2 chars of local part and first char of domain
    masked_local = local[:2] + '***' if len(local) > 2 else '***'
    masked_domain = domain[0] + '***' if domain else '***'
    return f"{masked_local}@{masked_domain}"


def catch_exceptions(cancel_on_failure=False):
    """Decorator to catch and log exceptions in scheduled jobs."""
    def decorator(job_func):
        @functools.wraps(job_func)
        def wrapper(*args, **kwargs):
            try:
                result = job_func(*args, **kwargs)
                if hasattr(args[0], 'update_health_status'):
                    args[0].update_health_status(
                        healthy=True,
                        message=f"{job_func.__name__} executed successfully"
                    )
                return result
            except Exception as e:
                logging.exception(f"Exception in {job_func.__name__}")
                if hasattr(args[0], 'update_health_status'):
                    args[0].update_health_status(
                        healthy=False,
                        message=f"Exception in {job_func.__name__}",
                        error=e
                    )
                if cancel_on_failure:
                    sys.exit(1)
        return wrapper
    return decorator


def blink_retry(retry_limit_attr):
    """Decorator to retry Blink operations with reinitialization."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            retry_limit = getattr(self, retry_limit_attr)
            for attempt in range(retry_limit):
                try:
                    return func(self, *args, **kwargs)
                except BlinkTwoFARequiredError as e:
                    if attempt >= retry_limit - 1:
                        raise Exception(f"Failed after {retry_limit} attempts: 2FA required") from e
                    self.logger.info(f"2FA required during {func.__name__}, reinitializing Blink (attempt {attempt + 1}/{retry_limit})...")
                    self.reinit_blink()
                except Exception as e:
                    if attempt >= retry_limit - 1:
                        raise Exception(f"Failed after {retry_limit} attempts") from e
                    self.logger.warning(f"Attempt {attempt + 1}/{retry_limit} failed for {func.__name__}, reinitializing Blink...")
                    self.reinit_blink()
        return wrapper
    return decorator


def async_to_sync(func):
    """Decorator to run async functions in sync context."""
    @catch_exceptions(cancel_on_failure=False)
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check if we're already in a running event loop
        try:
            asyncio.get_running_loop()
            # We're already in an event loop - shouldn't happen in our case
            raise RuntimeError("Cannot call async_to_sync from within a running loop")
        except RuntimeError as e:
            # Check if it's the "no running event loop" error (which is expected)
            if "no running event loop" not in str(e).lower():
                # Different RuntimeError, re-raise it
                raise
        
        # No event loop running, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create a coroutine and wrap it in ensure_future to create a task
        coro = func(*args, **kwargs)
        task = asyncio.ensure_future(coro, loop=loop)
        return loop.run_until_complete(task)
    return wrapper


class MyBlink:
    """Main class for Blink camera automation with VoIP.ms 2FA."""

    # Logging configuration
    LOG_LEVEL = logging.DEBUG
    LOG_FILE = "stdout"
    LOG_SIZE = 10 * 1024 * 1024  # 10MB
    LOG_COUNT = 5

    # File paths
    CONFIG_FILE = "/app/config.json"
    HEALTH_FILE = "/tmp/myblink_health.json"

    # Health check settings
    HEALTH_TIMEOUT = 300  # 5 minutes
    MAX_CONSECUTIVE_ERRORS = 3
    HEALTH_UPDATE_INTERVAL = 30  # seconds

    # Blink settings
    BLINK_RETRY_LIMIT = 3
    NO_SNOOZE_SYNCS = ["Hobo Cams"]
    NO_SNOOZE_CAMS = ["Front Door"]

    # VoIP.ms settings
    VOIPMS_MSG_STR = "Blink"
    VOIPMS_RETRY_LIMIT = 10
    VOIPMS_RETRY_DELAY = 3  # seconds
    VOIPMS_SMS_WAIT = 30  # seconds to wait for SMS delivery

    # Schedule settings
    MIN_TO_NEXT_STATUS = 1  # minutes
    RUN_ON_START = os.environ.get("RUN_ON_START", "false").lower() == "true"

    class CustomRotatingFileHandler(RotatingFileHandler):
        """Custom file handler with timestamp-based rotation."""
        
        def doRollover(self):
            if self.stream:
                self.stream.close()
                self.stream = None
            if self.backupCount > 0:
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                # Rotate existing backups
                for i in range(self.backupCount - 1, 0, -1):
                    sfn = self.rotation_filename(f"{self.baseFilename}.{i}")
                    dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}")
                    if os.path.exists(sfn):
                        if os.path.exists(dfn):
                            os.remove(dfn)
                        os.rename(sfn, dfn)
                # Create new backup with timestamp
                dfn = self.rotation_filename(f"{self.baseFilename}.{timestamp}")
                if os.path.exists(dfn):
                    os.remove(dfn)
                self.rotate(self.baseFilename, dfn)
            if not self.delay:
                self.stream = self._open()

    def __init__(self):
        """Initialize MyBlink application."""
        self.config = {}
        self.blink = None
        self.voipms = None
        self.logger = None
        self.blink_initialized = False
        self.consecutive_errors = 0

        self._init_logger()
        self._load_config()
        self._init_voipms()
        self._init_blink_safe()
        self._init_schedule()

    def __del__(self):
        """Cleanup aiohttp sessions on destruction."""
        self._close_session()

    def _init_logger(self):
        """Initialize logging configuration."""
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        handler = (
            logging.StreamHandler(sys.stdout)
            if self.LOG_FILE == "stdout"
            else self.CustomRotatingFileHandler(
                self.LOG_FILE,
                maxBytes=self.LOG_SIZE,
                backupCount=self.LOG_COUNT,
            )
        )
        handler.setLevel(self.LOG_LEVEL)
        handler.setFormatter(formatter)

        self.logger = logging.getLogger()
        self.logger.setLevel(self.LOG_LEVEL)
        self.logger.addHandler(handler)
        
        # Prevent urllib3 from logging credentials in URLs
        # Set urllib3 to WARNING level to avoid DEBUG logs with sensitive data
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    def _load_config(self):
        """Load configuration from JSON file."""
        try:
            with open(self.CONFIG_FILE, "r") as f:
                self.config = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            raise

    def _save_config(self):
        """Save configuration to JSON file."""
        try:
            with open(self.CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")

    def update_health_status(self, healthy=True, message="", error=None):
        """Update health status file for monitoring."""
        try:
            health_data = {
                "healthy": healthy,
                "timestamp": time.time(),
                "message": message,
                "consecutive_errors": self.consecutive_errors,
                "error": str(error) if error else None
            }
            with open(self.HEALTH_FILE, "w") as f:
                json.dump(health_data, f, indent=2)

            self.consecutive_errors = 0 if healthy else self.consecutive_errors + 1
        except Exception as e:
            self.logger.error(f"Failed to update health status: {e}")

    def _init_voipms(self):
        """Initialize VoIP.ms client."""
        try:
            self.voipms = VoipMs(
                self.config["voipms"]["username"],
                self.config["voipms"]["password"],
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize VoIP.ms: {e}")
            raise

    def _get_sms_messages(self):
        """Retrieve SMS messages from VoIP.ms."""
        try:
            return self.voipms.dids.get.sms()["sms"]
        except Exception as e:
            self.logger.exception(f"Failed to retrieve SMS messages: {e}")
            return None

    def get_blink_code(self):
        """Retrieve 2FA code from VoIP.ms SMS messages."""
        self.logger.info(f"Attempting to retrieve 2FA code (up to {self.VOIPMS_RETRY_LIMIT} retries)")
        
        for attempt in range(self.VOIPMS_RETRY_LIMIT):
            sms_messages = self._get_sms_messages()
            
            if not sms_messages:
                self.logger.debug(f"Retry {attempt + 1}: No SMS messages")
                if attempt < self.VOIPMS_RETRY_LIMIT - 1:
                    time.sleep(self.VOIPMS_RETRY_DELAY)
                continue

            self.logger.debug(f"Retry {attempt + 1}: Found {len(sms_messages)} SMS messages")
            
            # Find Blink messages
            blink_msgs = [
                msg for msg in sms_messages
                if (
                    msg["type"] == "1"
                    and msg["did"] == self.config["voipms"]["did"]
                    and len(msg["contact"]) == 5
                    and self.VOIPMS_MSG_STR in msg["message"]
                )
            ]

            if len(blink_msgs) == 1:
                self.logger.debug(f"Found Blink message: {blink_msgs[0]['message']}")
                match = re.search(r"\d{6}", blink_msgs[0]["message"])
                if match:
                    code = match.group()
                    self.logger.info(f"Successfully extracted 2FA code: {code}")
                    return code
            elif len(blink_msgs) > 1:
                self.logger.warning(f"Found {len(blink_msgs)} Blink messages, expected 1")

            if attempt < self.VOIPMS_RETRY_LIMIT - 1:
                self.logger.debug(f"Code not found, waiting {self.VOIPMS_RETRY_DELAY}s before retry")
                time.sleep(self.VOIPMS_RETRY_DELAY)

        self.logger.error("Failed to retrieve 2FA code after all retries")
        return None

    def _delete_blink_messages(self):
        """Delete Blink-related SMS messages from VoIP.ms."""
        sms_messages = self._get_sms_messages()
        if not sms_messages:
            return

        blink_msgs = [
            msg for msg in sms_messages
            if (
                msg["type"] == "1"
                and msg["did"] == self.config["voipms"]["did"]
                and len(msg["contact"]) == 5
                and self.VOIPMS_MSG_STR in msg["message"]
            )
        ]

        for msg in blink_msgs:
            try:
                self.voipms.dids.delete.sms(int(msg["id"]))
            except Exception as e:
                self.logger.warning(f"Failed to delete SMS {msg['id']}: {e}")

    async def _verify_and_save_blink(self):
        """Verify Blink authentication and save credentials."""
        if not self.blink.available:
            raise Exception("Blink service not available after authentication")

        if not self.blink.sync and not self.blink.cameras:
            raise Exception("No Blink devices found")

        # Save credentials
        if hasattr(self.blink.auth, 'login_attributes') and self.blink.available:
            self.config["blink"]["blinkpy_conf"] = json.dumps(
                self.blink.auth.login_attributes, indent=4
            )
            self._save_config()
            self.logger.info("Blink credentials saved")

    async def _handle_2fa_authentication(self, session):
        """Handle 2FA authentication flow."""
        self.logger.info("2FA required, waiting for SMS code")
        await asyncio.sleep(self.VOIPMS_SMS_WAIT)

        blink_code = self.get_blink_code()
        if not blink_code:
            raise Exception("2FA code not received from VoIP.ms")

        self.logger.info(f"Retrieved 2FA code: {blink_code}")
        self.blink.auth.data["2fa_code"] = blink_code

        # Retry login with 2FA code
        self.logger.info("Retrying login with 2FA code")
        login_response = await self.blink.auth.login()
        
        if not login_response:
            raise Exception("Login with 2FA failed")

        # Save and extract login information
        self.blink.auth.login_response = login_response
        self.logger.debug(f"Login response keys: {list(login_response.keys())}")
        
        self.blink.auth.extract_login_info()
        self.blink.auth.tier_info = await self.blink.auth.get_tier_info()
        self.blink.auth.extract_tier_info()
        
        # Complete setup
        self.blink.setup_urls()
        await self.blink.get_homescreen()
        await self.blink.setup_post_verify()
        
        self.logger.info(f"2FA authentication complete, available: {self.blink.available}")

    @async_to_sync
    async def init_blink(self):
        """Initialize Blink API connection with 2FA support."""
        try:
            self._delete_blink_messages()

            # Create session and Blink instance
            session = ClientSession()
            self.blink = Blink(session=session)

            # Try cached credentials first
            if self.config["blink"]["blinkpy_conf"]:
                self.logger.info("Attempting login with cached credentials")
                try:
                    cached_auth = json.loads(self.config["blink"]["blinkpy_conf"])
                    self.blink.auth = Auth(cached_auth, no_prompt=True, session=session)
                    
                    result = await self.blink.start()
                    self.logger.info(f"Cached credentials result: {result}, available: {self.blink.available}")
                    
                    if self.blink.available:
                        self.logger.info("Successfully authenticated with cached credentials")
                        await self._verify_and_save_blink()
                        self.update_health_status(healthy=True, message="Blink initialized with cached credentials")
                        self.logger.info("Blink initialization complete")
                        return
                    else:
                        self.logger.warning("Cached credentials failed or expired, falling back to fresh login")
                except BlinkTwoFARequiredError:
                    self.logger.info("Cached credentials require 2FA, falling back to fresh login")
                except Exception as e:
                    self.logger.warning(f"Error using cached credentials: {e}, falling back to fresh login")

            # Fall back to fresh login with username/password
            self.logger.info("Performing fresh login")
            
            # Clear failed cached credentials
            if self.config["blink"]["blinkpy_conf"]:
                self.config["blink"]["blinkpy_conf"] = ""
                self._save_config()

            # Create auth with username/password
            auth_info = {
                "username": self.config["blink"]["username"],
                "password": self.config["blink"]["password"],
            }
            
            self.logger.info(f"Creating Auth for user: {mask_email(auth_info['username'])}")
            self.blink.auth = Auth(auth_info, no_prompt=True, session=session)

            # Attempt initial login
            self.logger.info("Starting Blink authentication")
            try:
                result = await self.blink.start()
                self.logger.info(f"Blink.start() result: {result}, available: {self.blink.available}")
            except BlinkTwoFARequiredError:
                self.logger.info("2FA required during initial login")
                # The exception will be handled below

            # Handle 2FA if needed
            if not self.blink.available:
                await self._handle_2fa_authentication(session)

            # Verify and save
            await self._verify_and_save_blink()
            
            self.update_health_status(healthy=True, message="Blink initialized successfully")
            self.logger.info("Blink initialization complete")

        except Exception as e:
            self.logger.exception(f"Failed to initialize Blink: {e}")
            self.update_health_status(healthy=False, message="Blink initialization failed", error=e)
            raise

    def _init_blink_safe(self):
        """Initialize Blink with error handling for startup."""
        try:
            self.init_blink()
            self.blink_initialized = True
            self.update_health_status(healthy=True, message="Application started successfully")
        except Exception as e:
            self.blink_initialized = False
            self.logger.error(f"Failed to initialize Blink during startup: {e}")
            self.update_health_status(
                healthy=False,
                message="Blink initialization failed at startup",
                error=e
            )

    def _close_session(self):
        """Close aiohttp session if open."""
        try:
            if (
                hasattr(self, 'blink')
                and self.blink
                and hasattr(self.blink, 'auth')
                and hasattr(self.blink.auth, 'session')
                and self.blink.auth.session
                and not self.blink.auth.session.closed
            ):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.blink.auth.session.close())
                loop.close()
                self.logger.info("Closed aiohttp session")
        except Exception as e:
            self.logger.warning(f"Error closing session: {e}")

    def reinit_blink(self):
        """Reinitialize Blink connection."""
        self._close_session()
        self.blink = None
        self.init_blink()

    @catch_exceptions(cancel_on_failure=False)
    @blink_retry("BLINK_RETRY_LIMIT")
    @async_to_sync
    async def update_thumbnails(self):
        """Update camera thumbnails."""
        for name, camera in self.blink.cameras.items():
            await camera.snap_picture()

    @catch_exceptions(cancel_on_failure=False)
    @blink_retry("BLINK_RETRY_LIMIT")
    @async_to_sync
    async def rearm_cameras(self):
        """Rearm all camera sync modules."""
        for sync_name, sync in self.blink.sync.items():
            await sync.async_arm(True)

    @catch_exceptions(cancel_on_failure=False)
    @blink_retry("BLINK_RETRY_LIMIT")
    @async_to_sync
    async def snooze_cameras(self):
        """Snooze cameras (except excluded ones)."""
        for sync_name, sync in self.blink.sync.items():
            if sync_name in self.NO_SNOOZE_SYNCS:
                continue
            for camera_name, camera in sync.cameras.items():
                if camera_name not in self.NO_SNOOZE_CAMS:
                    await camera.async_snooze()

    def _init_schedule(self):
        """Initialize scheduled tasks."""
        schedule.every().hour.at(":00").do(self.update_thumbnails)
        schedule.every().hour.at(":00").do(self.rearm_cameras)
        schedule.every().hour.at(":00").do(self.snooze_cameras)

    def _run_all_jobs(self):
        """Run all scheduled jobs immediately."""
        self.logger.info("Running all scheduled jobs on startup")
        self.update_thumbnails()
        self.rearm_cameras()
        self.snooze_cameras()
        self.logger.info("Completed all scheduled jobs on startup")

    def run(self):
        """Main application loop."""
        log_timer = 0
        health_timer = 0
        log_interval = self.MIN_TO_NEXT_STATUS * 60

        self.logger.info("Starting main application loop")

        # Run all jobs immediately if RUN_ON_START is enabled
        if self.RUN_ON_START:
            self.logger.info("RUN_ON_START is enabled")
            if self.blink_initialized:
                self._run_all_jobs()
            else:
                self.logger.warning("Blink not initialized, skipping initial job run")

        while True:
            try:
                schedule.run_pending()
                
                # Log next job ETA
                next_job_eta = schedule.idle_seconds()
                if next_job_eta is not None and log_timer == log_interval:
                    self.logger.info(f"{next_job_eta:.0f} seconds until next job")
                log_timer = (log_timer + 1) if log_timer <= log_interval else 0

                # Update health status periodically
                if health_timer >= self.HEALTH_UPDATE_INTERVAL:
                    if not self.blink_initialized:
                        self.update_health_status(
                            healthy=False,
                            message="Blink failed to initialize"
                        )
                    elif self.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                        self.update_health_status(
                            healthy=False,
                            message=f"Too many consecutive errors: {self.consecutive_errors}"
                        )
                    else:
                        self.update_health_status(healthy=True, message="Running normally")
                    health_timer = 0
                else:
                    health_timer += 1

                time.sleep(1)

            except KeyboardInterrupt:
                self.logger.info("Shutting down gracefully")
                self._close_session()
                self.update_health_status(healthy=False, message="Application shutting down")
                sys.exit(0)
            except Exception as e:
                self.logger.exception(f"Unexpected error in main loop: {e}")
                self.update_health_status(healthy=False, message="Main loop error", error=e)
                time.sleep(5)


if __name__ == "__main__":
    app = MyBlink()
    app.run()
