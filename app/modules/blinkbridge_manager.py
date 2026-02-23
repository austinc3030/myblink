"""
BlinkBridge - RTSP Stream Manager for Blink Cameras

Provides RTSP streaming of Blink camera clips using MediaMTX and FFmpeg.
When motion is detected, downloads the clip and publishes it via RTSP.
Between motion events, loops a still frame from the last clip.
"""

import asyncio
import subprocess
import logging
import threading
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Union, List
from collections import defaultdict


logger = logging.getLogger(__name__)


class FFmpegStreamParameters:
    """Extract stream parameters from video using ffprobe."""
    
    def __init__(self, video_file: Union[str, Path]):
        ffprobe_params = [
            'ffprobe',
            '-hide_banner',
            '-loglevel', 'fatal',
            '-show_streams',
            '-print_format', 'json',
            str(video_file)
        ]
        self.process = subprocess.Popen(ffprobe_params, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    def wait(self) -> tuple:
        """Wait for ffprobe to complete and return audio/video stream parameters."""
        out, err = self.process.communicate()
        
        if self.process.returncode != 0:
            raise Exception(f"ffprobe failed: {err.decode('utf-8')}")
        
        js = json.loads(out.decode('utf-8'), parse_float=str, parse_int=str)
        streams = js['streams']
        
        stream_audio = next((s for s in streams if s.get('codec_name') == 'aac'), {})
        stream_video = next((s for s in streams if s.get('codec_name') == 'h264'), {})
        
        return stream_audio, stream_video


class VideoToLastFrame:
    """Extract last frame from video as image."""
    
    def __init__(self, input_video: Union[str, Path], output_image: Union[str, Path]):
        ffmpeg_params = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-y',
            '-sseof', '-1.0',
            '-i', str(input_video),
            '-update', '1',
            '-pix_fmt', 'yuv420p',
            '-vf', 'scale=out_range=pc',
            '-q:v', '1',
            str(output_image)
        ]
        
        self.process = subprocess.Popen(ffmpeg_params, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    def wait(self) -> None:
        """Wait for frame extraction to complete."""
        out, err = self.process.communicate()
        
        if self.process.returncode != 0:
            raise Exception(f"ffmpeg failed to extract last frame: {err.decode('utf-8')}")


class FrameToVideo:
    """Convert still frame to video with audio."""
    
    def __init__(self, 
                 image_file: Union[str, Path],
                 params_video: Dict,
                 params_audio: Dict,
                 output_duration: float,
                 output_file: Union[str, Path]):
        
        time_base_denominator = params_video['time_base'].split('/')[1]
        fps_value = params_video['r_frame_rate']
        
        ffmpeg_params = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-y',
            '-loop', '1',
            '-i', str(image_file),
            '-f', 'lavfi',
            '-i', f"anullsrc=channel_layout={params_audio['channels']}:sample_rate={params_audio['sample_rate']}",
            '-c:v', params_video['codec_name'],
            '-pix_fmt', params_video['pix_fmt'],
            '-t', str(output_duration),
            '-vf', f"scale={params_video['width']}:{params_video['height']},fps={fps_value}",
            '-b:v', params_video['bit_rate'],
            '-profile:v', params_video['profile'],
            '-level:v', params_video['level'],
            '-movflags', 'faststart',
            '-video_track_timescale', time_base_denominator,
            '-fps_mode', 'passthrough',
            '-c:a', 'aac',
            '-ar', params_audio['sample_rate'],
            '-ac', params_audio['channels'],
            str(output_file)
        ]
        
        self.process = subprocess.Popen(ffmpeg_params, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    def wait(self) -> None:
        """Wait for video creation to complete."""
        out, err = self.process.communicate()
        
        if self.process.returncode != 0:
            raise Exception(f"ffmpeg failed to create video: {err.decode('utf-8')}")


class StillVideoCreator:
    """Create a still video from the last frame of a video clip."""
    
    def __init__(self,
                 input_video: Union[str, Path],
                 output_duration: float,
                 output_video: Union[str, Path],
                 work_dir: Path):
        self.thread = threading.Thread(
            target=self._run,
            args=(input_video, output_duration, output_video, work_dir)
        )
        self.thread.start()
    
    def _run(self, input_video, output_duration, output_video, work_dir):
        """Extract last frame and convert to video."""
        try:
            still_image = work_dir / 'last_frame.jpg'
            
            # Extract last frame
            lfg = VideoToLastFrame(input_video, still_image)
            params_audio, params_video = FFmpegStreamParameters(input_video).wait()
            lfg.wait()
            
            if not params_audio or not params_video:
                raise Exception("Failed to extract stream parameters")
            
            # Convert frame to video
            FrameToVideo(
                still_image,
                params_video,
                params_audio,
                output_duration,
                output_video
            ).wait()
            
            # Cleanup
            if still_image.exists():
                still_image.unlink()
                
        except Exception as e:
            logger.error(f"Error creating still video: {e}")
            raise
    
    def wait(self) -> None:
        """Wait for still video creation to complete."""
        self.thread.join()


class CameraStreamServer:
    """Manages RTSP stream for a single camera using MediaMTX and FFmpeg."""
    
    def __init__(self,
                 camera_name: str,
                 rtsp_host: str,
                 rtsp_port: int,
                 work_dir: Path):
        self.camera_name = camera_name
        self.stream_name = camera_name.replace(' ', '_').lower()
        self.rtsp_host = rtsp_host
        self.rtsp_port = rtsp_port
        self.work_dir = work_dir
        self.process: Optional[subprocess.Popen] = None
        self.current_still_video: Optional[Path] = None
        self.failure_count = 0
        self.datetime_started: Optional[datetime] = None
        
        # Create camera-specific directory
        self.camera_dir = work_dir / self.stream_name
        self.camera_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def rtsp_url(self) -> str:
        """Get the RTSP URL for this camera stream."""
        return f"rtsp://{self.rtsp_host}:{self.rtsp_port}/{self.stream_name}"
    
    def _make_concat_files(self) -> Path:
        """Create FFmpeg concat demuxer files for seamless video looping."""
        logger.debug(f"{self.camera_name}: creating concat files")
        
        next_concat = self.camera_dir / 'next.concat'
        concat_file = self.camera_dir / 'stream.concat'
        
        with open(concat_file, 'w') as f:
            f.write("ffconcat version 1.0\n")
            f.write(f"file '{next_concat.resolve()}'\n")
            f.write(f"option safe 0\n")
            f.write(f"file '{next_concat.resolve()}'\n")
            f.write(f"option safe 0\n")
        
        return concat_file
    
    def _enqueue_clip(self, video_file: Path) -> None:
        """Add a video clip to the stream queue."""
        logger.debug(f"{self.camera_name}: enqueueing {video_file}")
        
        next_concat = self.camera_dir / 'next.concat'
        
        with open(next_concat, 'w') as f:
            f.write("ffconcat version 1.0\n")
            f.write(f"file '{video_file.resolve()}'\n")
    
    def _start_ffmpeg_process(self, concat_file: Path) -> None:
        """Start FFmpeg process to publish stream to MediaMTX."""
        logger.debug(f"{self.camera_name}: starting FFmpeg process")
        
        ffmpeg_args = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-y',
            '-fflags', '+igndts+genpts',
            '-re',
            '-stream_loop', '-1',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file.resolve()),
            '-flush_packets', '0',
            '-c:v', 'copy',
            '-c:a', 'copy',
            '-f', 'rtsp',
            '-fps_mode', 'drop',
            self.rtsp_url
        ]
        
        self.process = subprocess.Popen(
            ffmpeg_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        logger.info(f"{self.camera_name}: stream ready at {self.rtsp_url}")
    
    def add_video(self, video_file: Path, still_only: bool = False) -> None:
        """
        Add a new video clip to the stream.
        
        Args:
            video_file: Path to the video file
            still_only: If True, only create and enqueue still video (for initialization)
        """
        try:
            if not still_only:
                # Enqueue full clip immediately
                self._enqueue_clip(video_file)
            
            # Create still video from last frame
            dt = datetime.now()
            still_video = self.camera_dir / f"still_{dt.strftime('%Y-%m-%d_%H-%M-%S-%f')}.mp4"
            
            logger.debug(f"{self.camera_name}: creating still video {still_video}")
            still_video_duration = 0.5  # Half second still video
            
            svc = StillVideoCreator(
                video_file,
                still_video_duration,
                still_video,
                self.camera_dir
            )
            
            # Wait for still video to be created
            svc.wait()
            
            # Enqueue still video
            self._enqueue_clip(still_video)
            
            # Delete old still video
            if self.current_still_video and not still_only:
                if self.current_still_video.exists():
                    logger.debug(f"{self.camera_name}: deleting old still video")
                    self.current_still_video.unlink()
            
            self.current_still_video = still_video
            
        except Exception as e:
            logger.error(f"{self.camera_name}: error adding video: {e}")
            raise
    
    def start_server(self, initial_video: Path) -> None:
        """
        Start the RTSP stream server.
        
        Args:
            initial_video: Path to the initial video clip
        """
        logger.debug(f"{self.camera_name}: starting server with {initial_video}")
        
        concat_file = self._make_concat_files()
        self.add_video(initial_video, still_only=True)
        self._start_ffmpeg_process(concat_file)
        self.datetime_started = datetime.now()
    
    def is_running(self) -> bool:
        """Check if the FFmpeg process is still running."""
        return self.process is not None and self.process.poll() is None
    
    def stop(self) -> None:
        """Stop the stream server."""
        if self.is_running():
            logger.info(f"{self.camera_name}: stopping stream server")
            self.process.kill()
            self.process.wait()
        
        # Cleanup still video
        if self.current_still_video and self.current_still_video.exists():
            self.current_still_video.unlink()


class BlinkBridgeManager:
    """
    Manages RTSP streams for all enabled Blink cameras.
    
    Monitors cameras for motion and publishes video clips to RTSP streams.
    """
    
    def __init__(self, myblink_app, config: Dict):
        """
        Initialize BlinkBridge manager.
        
        Args:
            myblink_app: MyBlink application instance
            config: BlinkBridge configuration dictionary
        """
        self.myblink_app = myblink_app
        self.config = config
        self.stream_servers: Dict[str, CameraStreamServer] = {}
        self.camera_last_record: Dict[str, Optional[str]] = defaultdict(lambda: None)
        self.running = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.mediamtx_process: Optional[subprocess.Popen] = None
        
        # Setup directories
        self.work_dir = Path(config.get('work_dir', '/tmp/blinkbridge'))
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        # RTSP server settings
        self.rtsp_host = config.get('rtsp_host', 'localhost')
        self.rtsp_port = config.get('rtsp_port', 8554)
        
        # Stream settings
        self.poll_interval = config.get('poll_interval', 1.0)
        self.max_failures = config.get('max_failures', 3)
        self.restart_delay = timedelta(seconds=config.get('restart_delay_seconds', 60))
    
    def start_mediamtx(self) -> None:
        """Start MediaMTX RTSP server."""
        if self.mediamtx_process and self.mediamtx_process.poll() is None:
            logger.info("MediaMTX already running")
            return
        
        logger.info(f"Starting MediaMTX on port {self.rtsp_port}")
        
        # Start MediaMTX with custom port
        env = {
            'MTX_RTSPADDRESS': f':{self.rtsp_port}',
            'PATH': '/usr/local/bin:/usr/bin:/bin'
        }
        
        self.mediamtx_process = subprocess.Popen(
            ['mediamtx'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        
        logger.info("MediaMTX started successfully")
    
    def stop_mediamtx(self) -> None:
        """Stop MediaMTX RTSP server."""
        if self.mediamtx_process and self.mediamtx_process.poll() is None:
            logger.info("Stopping MediaMTX")
            self.mediamtx_process.terminate()
            try:
                self.mediamtx_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.mediamtx_process.kill()
            logger.info("MediaMTX stopped")
    
    async def _save_latest_clip(self, camera_name: str, force: bool = False) -> Optional[Path]:
        """
        Download and save the latest clip for a camera.
        
        Args:
            camera_name: Name of the camera
            force: Force download even if file exists
            
        Returns:
            Path to the saved video file, or None if no clip available
        """
        camera_name_sanitized = camera_name.replace(' ', '_').lower()
        file_name = self.work_dir / f"{camera_name_sanitized}_latest.mp4"
        
        # Don't download if clip already exists
        if file_name.exists() and not force:
            logger.debug(f"{camera_name}: using existing clip {file_name}")
            return file_name
        
        try:
            camera = self.myblink_app.blink_handler.blink.cameras.get(camera_name)
            if not camera:
                logger.warning(f"{camera_name}: camera not found")
                return None
            
            # Get video clip
            if not camera.clip:
                logger.warning(f"{camera_name}: no clip URL available")
                return None
            
            logger.debug(f"{camera_name}: downloading clip from {camera.clip}")
            
            response = await camera.get_video_clip()
            if response and response.status == 200:
                logger.debug(f"{camera_name}: saving clip to {file_name}")
                with open(file_name, 'wb') as f:
                    f.write(await response.read())
                return file_name
            else:
                logger.error(f"{camera_name}: failed to download clip, status={response.status if response else 'None'}")
                return None
                
        except Exception as e:
            logger.error(f"{camera_name}: error downloading clip: {e}")
            return None
    
    async def _check_for_motion(self, camera_name: str) -> Optional[Path]:
        """
        Check if motion was detected and download new clip if available.
        
        Args:
            camera_name: Name of the camera
            
        Returns:
            Path to new video file if motion detected, None otherwise
        """
        try:
            # Refresh camera state
            camera = self.myblink_app.blink_handler.blink.cameras.get(camera_name)
            if not camera:
                return None
            
            # Check if motion detected and last record changed
            if not camera.motion_detected:
                return None
            
            if self.camera_last_record[camera_name] == camera.last_record:
                return None
            
            logger.info(f"{camera_name}: motion detected, last_record={camera.last_record}")
            
            # Download new clip
            camera_name_sanitized = camera_name.replace(' ', '_').lower()
            file_name = self.work_dir / f"{camera_name_sanitized}_latest.mp4"
            
            await camera.video_to_file(str(file_name))
            self.camera_last_record[camera_name] = camera.last_record
            
            return file_name
            
        except Exception as e:
            logger.error(f"{camera_name}: error checking for motion: {e}")
            return None
    
    async def _start_camera_stream(self, camera_name: str, redownload: bool = False) -> Optional[CameraStreamServer]:
        """
        Start RTSP stream for a camera.
        
        Args:
            camera_name: Name of the camera
            redownload: Force redownload of latest clip
            
        Returns:
            CameraStreamServer instance or None if failed
        """
        try:
            logger.info(f"{camera_name}: starting stream")
            
            # Get latest clip
            video_file = await self._save_latest_clip(camera_name, force=redownload)
            if not video_file:
                logger.error(f"{camera_name}: no video available to start stream")
                return None
            
            # Create and start stream server
            server = CameraStreamServer(
                camera_name,
                self.rtsp_host,
                self.rtsp_port,
                self.work_dir
            )
            
            server.start_server(video_file)
            self.stream_servers[camera_name] = server
            
            return server
            
        except Exception as e:
            logger.error(f"{camera_name}: error starting stream: {e}")
            return None
    
    async def _monitor_cameras(self) -> None:
        """Monitor cameras for motion and manage streams."""
        logger.info("Starting camera monitoring")
        
        while self.running:
            try:
                # Check each stream for motion
                for camera_name in list(self.stream_servers.keys()):
                    server = self.stream_servers[camera_name]
                    
                    # Check if server is still running
                    if not server.is_running():
                        logger.warning(f"{camera_name}: stream server stopped")
                        
                        # Remove if too many failures
                        if server.failure_count >= self.max_failures - 1:
                            logger.error(f"{camera_name}: max failures reached, disabling")
                            self.stream_servers.pop(camera_name)
                            continue
                        
                        # Check restart delay
                        if datetime.now() < server.datetime_started + self.restart_delay:
                            continue
                        
                        # Restart stream
                        logger.info(f"{camera_name}: restarting stream (failure {server.failure_count + 1})")
                        new_server = await self._start_camera_stream(camera_name, redownload=True)
                        
                        if new_server:
                            new_server.failure_count = server.failure_count + 1
                        
                        continue
                    
                    # Check for motion
                    try:
                        new_clip = await self._check_for_motion(camera_name)
                        if new_clip:
                            logger.info(f"{camera_name}: adding new clip to stream")
                            server.add_video(new_clip)
                    except Exception as e:
                        logger.error(f"{camera_name}: error checking motion: {e}")
                
                # Wait before next check
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in camera monitoring: {e}")
                await asyncio.sleep(self.poll_interval)
    
    async def start(self, enabled_cameras: Optional[List[str]] = None) -> None:
        """
        Start BlinkBridge with specified cameras.
        
        Args:
            enabled_cameras: List of camera names to enable, or None for all
        """
        if self.running:
            logger.warning("BlinkBridge already running")
            return
        
        logger.info("Starting BlinkBridge")
        
        # Start MediaMTX
        self.start_mediamtx()
        await asyncio.sleep(2)  # Give MediaMTX time to start
        
        # Get list of cameras to enable
        if enabled_cameras is None:
            if self.myblink_app.blink_handler and self.myblink_app.blink_handler.blink:
                enabled_cameras = list(self.myblink_app.blink_handler.blink.cameras.keys())
            else:
                logger.error("No Blink handler available")
                return
        
        logger.info(f"Enabling cameras: {enabled_cameras}")
        
        # Start streams for each camera
        for camera_name in enabled_cameras:
            server = await self._start_camera_stream(camera_name)
            if server:
                server.failure_count = 0
        
        # Start monitoring task
        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_cameras())
        
        logger.info("BlinkBridge started successfully")
    
    async def stop(self) -> None:
        """Stop BlinkBridge and all camera streams."""
        if not self.running:
            return
        
        logger.info("Stopping BlinkBridge")
        
        self.running = False
        
        # Cancel monitoring task
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        # Stop all stream servers
        for server in self.stream_servers.values():
            server.stop()
        
        self.stream_servers.clear()
        
        # Stop MediaMTX
        self.stop_mediamtx()
        
        logger.info("BlinkBridge stopped")
    
    def get_stream_info(self) -> Dict:
        """Get information about all active streams."""
        return {
            camera_name: {
                'rtsp_url': server.rtsp_url,
                'running': server.is_running(),
                'failure_count': server.failure_count,
                'started': server.datetime_started.isoformat() if server.datetime_started else None
            }
            for camera_name, server in self.stream_servers.items()
        }
    
    def get_frigate_config(self, cameras: Optional[List[str]] = None) -> str:
        """
        Generate Frigate configuration for enabled cameras.
        
        Args:
            cameras: List of camera names, or None for all active streams
            
        Returns:
            YAML configuration string for Frigate
        """
        if cameras is None:
            cameras = list(self.stream_servers.keys())
        
        config_lines = ["cameras:"]
        
        for camera_name in cameras:
            server = self.stream_servers.get(camera_name)
            if not server:
                continue
            
            stream_name = server.stream_name
            rtsp_url = server.rtsp_url
            
            config_lines.extend([
                f"  {stream_name}:",
                f"    enabled: True",
                f"    ffmpeg:",
                f"      inputs:",
                f"        - path: {rtsp_url}",
                f"          roles:",
                f"            - detect",
                f"            - record",
                ""
            ])
        
        return '\n'.join(config_lines)
