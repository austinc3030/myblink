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

from aiohttp import ClientSession
from blinkpy.auth import Auth
from blinkpy.blinkpy import Blink
from blinkpy.helpers.util import json_load, json_save
from logging.handlers import RotatingFileHandler
from voipms import VoipMs


def catch_exceptions(cancel_on_failure=False):
    def catch_exceptions_decorator(job_func):
        @functools.wraps(job_func)
        def wrapper(*args, **kwargs):
            try:
                result = job_func(*args, **kwargs)
                # If successful, update health status
                if hasattr(args[0], 'update_health_status'):
                    args[0].update_health_status(
                        healthy=True, 
                        message=f"{job_func.__name__} executed successfully"
                    )
                return result
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                filename = exc_traceback.tb_frame.f_code.co_filename
                line_number = exc_traceback.tb_lineno
                logging.exception(f"Exception in {filename}:{line_number}: {exc_value}")
                
                # Update health status on error
                if hasattr(args[0], 'update_health_status'):
                    args[0].update_health_status(
                        healthy=False,
                        message=f"Exception in {job_func.__name__}",
                        error=e
                    )
                    
                if cancel_on_failure:
                    return sys.exit()

        return wrapper

    return catch_exceptions_decorator


def blink_retry(retry_limit_attr):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            attempt = 0
            while attempt < getattr(self, retry_limit_attr):
                try:
                    func(self, *args, **kwargs)
                    break
                except Exception as e:
                    attempt += 1
                    if attempt >= getattr(self, retry_limit_attr):
                        raise Exception(
                            f"Failed after {getattr(self, retry_limit_attr)} attempts"
                        ) from e
                    else:
                        self.reinit_blink()

        return wrapper

    return decorator


@catch_exceptions(cancel_on_failure=False)
def async_to_sync(func):
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args, **kwargs))

    return wrapper


class myblink:

    # Logging Variables
    log_level = logging.DEBUG
    log_file = "stdout"
    log_size = 10 * 1024 * 1024
    log_count = 5

    # Config Variables
    config_file = "/app/config.json"
    config = {}

    # Health Check Variables
    health_file = "/tmp/myblink_health.json"
    health_timeout = 300  # 5 minutes - if no update, considered unhealthy
    max_consecutive_errors = 3  # Max errors before marking unhealthy
    consecutive_errors = 0

    # Blink Variables
    blink_retry_count = 0
    blink_retry_limit = 3
    blink_initialized = False  # Track if Blink was successfully initialized
    no_snooze_syncs = ["Hobo Cams"]
    no_snooze_cams = ["Front Door"]

    # Voip.ms Variables
    msg_str = "Blink"
    voipms_retry_limit = 10
    voipms_retry_delay = 3

    # Schedule Variables
    min_to_next_status = 1

    class CustomRotatingFileHandler(RotatingFileHandler):
        def doRollover(self):
            if self.stream:
                self.stream.close()
                self.stream = None
            if self.backupCount > 0:
                currentTime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                for i in range(self.backupCount - 1, 0, -1):
                    sfn = self.rotation_filename(f"{self.baseFilename}.{i}")
                    dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}")
                    if os.path.exists(sfn):
                        if os.path.exists(dfn):
                            os.remove(dfn)
                        os.rename(sfn, dfn)
                dfn = self.rotation_filename(f"{self.baseFilename}.{currentTime}")
                if os.path.exists(dfn):
                    os.remove(dfn)
                self.rotate(self.baseFilename, dfn)
            if not self.delay:
                self.stream = self._open()

    def __init__(self):
        self.init_logger()
        self.init_config()
        self.init_voipms()
        
        # Try to initialize Blink - if it fails, mark unhealthy but continue
        # This allows the container to stay running for debugging
        try:
            self.init_blink()
            self.blink_initialized = True
            self.update_health_status(healthy=True, message="Application started successfully")
        except Exception as e:
            self.blink_initialized = False
            self.logger.error(f"Failed to initialize Blink during startup: {e}")
            self.update_health_status(healthy=False, message="Blink initialization failed at startup", error=e)
            # Don't raise - let the app continue so healthcheck can report unhealthy
        
        self.init_schedule()

    def __del__(self):
        """Cleanup method to close aiohttp sessions"""
        if hasattr(self, 'blink') and self.blink and hasattr(self.blink, 'auth'):
            try:
                if hasattr(self.blink.auth, 'session') and self.blink.auth.session:
                    asyncio.run(self.blink.auth.session.close())
            except:
                pass

    def init_logger(self):
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        if self.log_file == "stdout":
            handler = logging.StreamHandler(sys.stdout)
        else:
            handler = self.CustomRotatingFileHandler(
                self.log_file,
                maxBytes=self.log_size,
                backupCount=self.log_count,
            )
        handler.setLevel(self.log_level)
        handler.setFormatter(formatter)

        self.logger = logging.getLogger()
        self.logger.setLevel(self.log_level)
        self.logger.addHandler(handler)

    def init_config(self):
        with open(self.config_file, "r") as f:
            self.config = json.load(f)

    def save_config(self):
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=4)

    def update_health_status(self, healthy=True, message="", error=None):
        """Update the health status file for healthcheck monitoring"""
        try:
            health_data = {
                "healthy": healthy,
                "timestamp": time.time(),
                "message": message,
                "consecutive_errors": self.consecutive_errors,
                "error": str(error) if error else None
            }
            with open(self.health_file, "w") as f:
                json.dump(health_data, f, indent=2)
            
            if healthy:
                self.consecutive_errors = 0
            else:
                self.consecutive_errors += 1
                
        except Exception as e:
            logging.error(f"Failed to update health status: {e}")

    def init_voipms(self):
        self.voipms = VoipMs(
            self.config["voipms"]["username"],
            self.config["voipms"]["password"],
        )

    def get_blink_code(self):
        self.logger.info(f"Attempting to retrieve 2FA code from VoIP.ms (up to {self.voipms_retry_limit} retries)...")
        for retry_count in range(self.voipms_retry_limit):
            blink_msgs = []
            sms_messages = self.get_sms_msgs()

            if sms_messages:
                self.logger.debug(f"Retry {retry_count + 1}: Found {len(sms_messages)} total SMS messages")
                for msg in sms_messages:
                    if (
                        msg["type"] == "1"
                        and msg["did"] == self.config["voipms"]["did"]
                        and len(msg["contact"]) == 5
                        and self.msg_str in msg["message"]
                    ):
                        blink_msgs.append(msg)
                        self.logger.debug(f"Found Blink message: {msg['message']}")
            else:
                self.logger.debug(f"Retry {retry_count + 1}: No SMS messages returned")

            if blink_msgs and len(blink_msgs) == 1:
                match = re.search(r"\d{6}", blink_msgs[0]["message"])
                if match:
                    code = match.group()
                    self.logger.info(f"Successfully extracted 2FA code: {code}")
                    return code
            elif blink_msgs and len(blink_msgs) > 1:
                self.logger.warning(f"Found {len(blink_msgs)} Blink messages, expected 1")
            
            if retry_count < self.voipms_retry_limit - 1:
                self.logger.debug(f"Code not found yet, waiting {self.voipms_retry_delay} seconds before retry...")
                time.sleep(self.voipms_retry_delay)

        self.logger.error("Failed to retrieve 2FA code after all retries")
        return None

    def get_sms_msgs(self):
        try:
            return self.voipms.dids.get.sms()["sms"]
        except Exception as e:
            logging.exception(f"Exception: {e}")
            return None

    def get_blink_msgs(self):
        sms_messages = self.get_sms_msgs()
        blink_msgs = []

        if sms_messages:
            for msg in sms_messages:
                if (
                    msg["type"] == "1"
                    and msg["did"] == self.config["voipms"]["did"]
                    and len(msg["contact"]) == 5
                    and self.msg_str in msg["message"]
                ):
                    blink_msgs.append(msg)

            return blink_msgs

    def delete_blink_msgs(self):
        blink_msgs = self.get_blink_msgs()
        if blink_msgs:
            for msg in blink_msgs:
                self.voipms.dids.delete.sms(int(msg["id"]))

    async def _verify_and_save_blink(self):
        """Verify Blink authentication and save credentials."""
        # Verify Blink is available after start
        if not self.blink.available:
            self.logger.error("Blink authentication failed - service not available after start()")
            raise Exception("Blink authentication failed - service not available")

        # Verify we have cameras/syncs
        if not self.blink.sync and not self.blink.cameras:
            self.logger.error("No Blink sync modules or cameras found after authentication")
            raise Exception("No Blink devices found - authentication may have failed")

        # Save successful credentials only if authentication actually worked
        if hasattr(self.blink.auth, 'login_attributes') and self.blink.available:
            self.config["blink"]["blinkpy_conf"] = json.dumps(
                self.blink.auth.login_attributes, indent=4
            )
            self.save_config()
            self.logger.info("Blink credentials saved successfully")

    @async_to_sync
    async def init_blink(self):
        try:
            self.delete_blink_msgs()

            # Create session
            session = ClientSession()
            
            # Create Blink instance
            self.blink = Blink(session=session)
            
            # Start with username/password (always use fresh login for reliability)
            # Saved credentials with expired tokens cause interactive prompts
            self.logger.info("Attempting fresh Blink login")
            
            # Clear any saved credentials to force fresh login and save config
            if self.config["blink"]["blinkpy_conf"]:
                self.logger.info("Clearing saved credentials to avoid expired token issues")
                self.config["blink"]["blinkpy_conf"] = ""
                self.save_config()
                
            # Create fresh auth info with ONLY username and password
            # Explicitly create a new dict to ensure no token data
            auth_info = {
                "username": self.config["blink"]["username"],
                "password": self.config["blink"]["password"],
            }
            
            self.logger.info(f"Creating Auth for user: {auth_info['username']}")
            self.logger.debug(f"Auth info keys: {list(auth_info.keys())}")
            
            # Create Auth with session parameter - this is critical!
            # no_prompt=True prevents interactive input
            self.blink.auth = Auth(auth_info, no_prompt=True, session=session)
            
            # Log what the auth object thinks its state is
            self.logger.debug(f"Auth data after creation: {list(self.blink.auth.data.keys()) if hasattr(self.blink.auth, 'data') else 'no data attr'}")
            
            # Start Blink - this will attempt login
            try:
                self.logger.info("Calling blink.start()...")
                result = await self.blink.start()
                self.logger.info(f"blink.start() completed with result: {result}")
                self.logger.info(f"blink.available: {self.blink.available}")
                
                # Check if 2FA is required even though no exception was raised
                if not self.blink.available:
                    self.logger.info("Blink not available after start(), checking for 2FA requirement...")
                    
                    # Log auth state for debugging
                    self.logger.debug(f"Auth object attributes: {dir(self.blink.auth)}")
                    self.logger.debug(f"Auth login_response: {getattr(self.blink.auth, 'login_response', 'N/A')}")
                    
                    # Check multiple ways if 2FA is needed
                    key_required = False
                    
                    if hasattr(self.blink.auth, 'check_key_required'):
                        try:
                            key_required = self.blink.auth.check_key_required()
                            self.logger.info(f"check_key_required() returned: {key_required}")
                        except Exception as e:
                            self.logger.warning(f"Error calling check_key_required(): {e}")
                    
                    # Also check if there's a key_required attribute
                    if hasattr(self.blink, 'key_required'):
                        self.logger.info(f"blink.key_required: {self.blink.key_required}")
                        key_required = key_required or self.blink.key_required
                    
                    # If not available and no clear 2FA indication, assume 2FA is needed
                    # (Blink sends the code, so we should try to use it)
                    if not key_required:
                        self.logger.info("No explicit 2FA flag, but auth failed - assuming 2FA needed")
                        key_required = True
                    
                    if key_required:
                        try:
                            self.logger.info("2FA required, waiting for SMS code from VoIP.ms...")
                            # Give SMS a moment to arrive
                            await asyncio.sleep(2)
                            
                            blink_code = self.get_blink_code()
                            if blink_code:
                                self.logger.info(f"Retrieved 2FA code: {blink_code}")
                                # Add 2FA code to auth data
                                self.blink.auth.data["2fa_code"] = blink_code
                                self.logger.info("2FA code added to auth data")
                                
                                # Retry login with 2FA code
                                self.logger.info("Retrying login with 2FA code...")
                                login_response = await self.blink.auth.login()
                                self.logger.info(f"Login with 2FA response: {login_response is not None}")
                                
                                if login_response:
                                    # Extract login info from response
                                    self.blink.auth.extract_login_info()
                                    # Get tier info
                                    self.blink.auth.tier_info = await self.blink.auth.get_tier_info()
                                    self.blink.auth.extract_tier_info()
                                    # Setup URLs
                                    self.blink.setup_urls()
                                    # Get homescreen
                                    await self.blink.get_homescreen()
                                    # Setup post verify
                                    if hasattr(self.blink, 'setup_post_verify'):
                                        self.logger.info("Running setup_post_verify()...")
                                        await self.blink.setup_post_verify()
                                        self.logger.info("setup_post_verify() completed")
                                    
                                    # Refresh blink status
                                    self.logger.info(f"After 2FA - blink.available: {self.blink.available}")
                                else:
                                    raise Exception("Login with 2FA failed")
                            else:
                                self.logger.error("Failed to retrieve 2FA code from VoIP.ms after multiple retries")
                                raise Exception("2FA code not received from VoIP.ms")
                        except Exception as check_error:
                            self.logger.error(f"Error handling 2FA after start(): {check_error}")
                            raise
                        
            except EOFError as eof_error:
                # EOFError means it tried to prompt for 2FA - retrieve it from VoIP.ms
                self.logger.info(f"2FA required (EOFError caught: {eof_error}), retrieving code from VoIP.ms")
                blink_code = self.get_blink_code()
                if blink_code:
                    self.logger.info(f"Retrieved 2FA code: {blink_code}")
                    # Add 2FA code to auth_info and recreate Auth
                    auth_info["2fa_code"] = blink_code
                    self.blink.auth = Auth(auth_info, no_prompt=True, session=session)
                    self.logger.info("Retrying blink.start() with 2FA code...")
                    await self.blink.start()
                    self.logger.info("blink.start() with 2FA completed")
                else:
                    self.logger.error("Failed to retrieve 2FA code from VoIP.ms")
                    raise Exception("2FA code not received from VoIP.ms")
            except Exception as e:
                self.logger.error(f"Exception during blink.start(): {type(e).__name__}: {e}")
                self.logger.debug(f"blink.available: {getattr(self.blink, 'available', 'N/A')}")
                self.logger.debug(f"blink.auth.login_response: {getattr(self.blink.auth, 'login_response', 'N/A')}")
                
                # Check if blink is asking for 2FA via check_key_required
                if hasattr(self.blink.auth, 'check_key_required'):
                    try:
                        key_required = self.blink.auth.check_key_required()
                        self.logger.info(f"check_key_required() returned: {key_required}")
                        if key_required:
                            self.logger.info("2FA required (check_key_required=True), retrieving code from VoIP.ms")
                            blink_code = self.get_blink_code()
                            if blink_code:
                                self.logger.info(f"Retrieved 2FA code: {blink_code}")
                                auth_info["2fa_code"] = blink_code
                                self.blink.auth = Auth(auth_info, no_prompt=True, session=session)
                                self.logger.info("Retrying blink.start() with 2FA code...")
                                await self.blink.start()
                                self.logger.info("blink.start() with 2FA completed")
                                # Don't raise - we handled it
                                return await self._verify_and_save_blink()
                    except Exception as check_error:
                        self.logger.warning(f"Error checking for 2FA requirement: {check_error}")
                # Re-raise the original exception if we couldn't handle it
                raise

            # Verify and save
            await self._verify_and_save_blink()
            
            self.update_health_status(healthy=True, message="Blink initialized successfully")
            self.logger.info("Blink initialization complete")
            
        except Exception as e:
            self.logger.exception(f"Failed to initialize Blink: {e}")
            self.update_health_status(healthy=False, message="Blink initialization failed", error=e)
            raise

    def reinit_blink(self):
        # Close existing session if present
        if hasattr(self, 'blink') and self.blink and hasattr(self.blink, 'auth'):
            try:
                if hasattr(self.blink.auth, 'session') and self.blink.auth.session:
                    if not self.blink.auth.session.closed:
                        # Run async close in sync context
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.blink.auth.session.close())
                        loop.close()
                        self.logger.info("Closed old aiohttp session")
            except Exception as e:
                self.logger.warning(f"Error closing old session: {e}")
        
        self.blink = None
        self.init_blink()

    @catch_exceptions(cancel_on_failure=False)
    @blink_retry("blink_retry_limit")
    @async_to_sync
    async def update_thumbnails(self):
        for name, camera in self.blink.cameras.items():
            await camera.snap_picture()

    @catch_exceptions(cancel_on_failure=False)
    @blink_retry("blink_retry_limit")
    @async_to_sync
    async def rearm_cameras(self):
        for sync_name, sync in self.blink.sync.items():
            await sync.async_arm(True)

    @catch_exceptions(cancel_on_failure=False)
    @blink_retry("blink_retry_limit")
    @async_to_sync
    async def snooze_cameras(self):
        for sync_name, sync in self.blink.sync.items():
            if sync_name not in self.no_snooze_syncs:
                for camera_name, camera in sync.cameras.items():
                    if camera_name not in self.no_snooze_cams:
                        await camera.async_snooze()

    def init_schedule(self):
        schedule.every().hour.at(":00").do(self.update_thumbnails)
        schedule.every().hour.at(":00").do(self.rearm_cameras)
        schedule.every().hour.at(":00").do(self.snooze_cameras)

    def run(self):
        log_timer = 0
        health_timer = 0
        while True:
            try:
                schedule.run_pending()
                next_job_eta = schedule.idle_seconds()

                if next_job_eta is not None and log_timer == (self.min_to_next_status * 60):
                    self.logger.info(f"{next_job_eta} seconds until next job")
                log_timer = log_timer + 1 if log_timer <= (self.min_to_next_status * 60) else 0
                
                # Update health status every 30 seconds to show we're alive
                if health_timer >= 30:
                    # Check if Blink was never initialized
                    if not self.blink_initialized:
                        self.update_health_status(
                            healthy=False,
                            message="Blink failed to initialize - container is unhealthy"
                        )
                    elif self.consecutive_errors >= self.max_consecutive_errors:
                        self.update_health_status(
                            healthy=False,
                            message=f"Too many consecutive errors: {self.consecutive_errors}"
                        )
                    else:
                        self.update_health_status(
                            healthy=True,
                            message="Running normally"
                        )
                    health_timer = 0
                else:
                    health_timer += 1
                    
                time.sleep(1)
            except KeyboardInterrupt:
                self.logger.info("Shutting down gracefully...")
                self.cleanup()
                self.update_health_status(healthy=False, message="Application shutting down")
                sys.exit(0)
            except Exception as e:
                self.logger.exception(f"Unexpected error in main loop: {e}")
                self.update_health_status(healthy=False, message="Main loop error", error=e)
                time.sleep(5)  # Brief pause before continuing

    def cleanup(self):
        """Cleanup resources before shutdown"""
        try:
            if hasattr(self, 'blink') and self.blink:
                # Close aiohttp session
                if hasattr(self.blink, 'auth') and hasattr(self.blink.auth, 'session'):
                    session = self.blink.auth.session
                    if session and not session.closed:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(session.close())
                        loop.close()
                        self.logger.info("Closed aiohttp session")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    myblink = myblink()
    myblink.run()
