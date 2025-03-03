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
from logging.handlers import RotatingFileHandler
from voipms import VoipMs


def catch_exceptions(cancel_on_failure=False):
    def catch_exceptions_decorator(job_func):
        @functools.wraps(job_func)
        def wrapper(*args, **kwargs):
            try:
                return job_func(*args, **kwargs)
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                filename = exc_traceback.tb_frame.f_code.co_filename
                line_number = exc_traceback.tb_lineno
                logging.exception(f"Exception in {filename}:{line_number}: {exc_value}")
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
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(func(*args, **kwargs))

    return wrapper


class myblink:

    # Logging Variables
    log_level = logging.DEBUG
    log_file = "logs/run.log"
    log_size = 10 * 1024 * 1024
    log_count = 5

    # Config Variables
    config_file = "config.json"
    config = {}

    # Blink Variables
    blink_retry_count = 0
    blink_retry_limit = 3
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
        self.init_blink()
        self.init_schedule()

    def init_logger(self):
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

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

    def init_voipms(self):
        self.voipms = VoipMs(
            self.config["voipms"]["username"],
            self.config["voipms"]["password"],
        )

    def get_blink_code(self):
        for retry_count in range(self.voipms_retry_limit):
            blink_msgs = []
            sms_messages = self.get_sms_msgs()

            if sms_messages:
                for msg in sms_messages:
                    if (
                        msg["type"] == "1"
                        and msg["did"] == self.config["voipms"]["did"]
                        and len(msg["contact"]) == 5
                        and self.msg_str in msg["message"]
                    ):
                        blink_msgs.append(msg)

            if blink_msgs and len(blink_msgs) == 1:
                match = re.search(r"\d{6}", blink_msgs[0]["message"])
                if match:
                    return match.group()
            else:
                time.sleep(self.voipms_retry_delay)

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

    @async_to_sync
    async def init_blink(self):
        self.delete_blink_msgs()

        self.blink = Blink(session=ClientSession())
        if self.config["blink"]["blinkpy_conf"]:
            auth_info = json.loads(self.config["blink"]["blinkpy_conf"])
        else:
            auth_info = {
                "username": self.config["blink"]["username"],
                "password": self.config["blink"]["password"],
            }

        self.blink.auth = Auth(auth_info, no_prompt=True)
        await self.blink.start()

        if self.blink.key_required:
            blink_code = self.get_blink_code()
            if blink_code:
                await self.blink.auth.send_auth_key(self.blink, blink_code)
                await self.blink.setup_post_verify()

        self.config["blink"]["blinkpy_conf"] = json.dumps(
            self.blink.auth.login_attributes, indent=4
        )

        self.save_config()

    def reinit_blink(self):
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
        while True:
            schedule.run_pending()
            next_job_eta = schedule.idle_seconds()

            if next_job_eta is not None and log_timer == (self.min_to_next_status * 60):
                self.logger.info(f"{next_job_eta} seconds until next job")
            log_timer = log_timer + 1 if log_timer <= (self.min_to_next_status * 60) else 0
            time.sleep(1)


if __name__ == "__main__":
    myblink = myblink()
    myblink.run()
