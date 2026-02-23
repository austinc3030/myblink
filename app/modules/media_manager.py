"""
Media management for automatic clip and thumbnail downloads.

Handles downloading, storage, retention policies, and NAS connectivity
for Blink camera clips and thumbnails.
"""

import asyncio
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class MediaDownloadConfig:
    """Configuration for media downloads."""
    
    # Enable/disable features
    enabled: bool = False
    download_clips: bool = True
    download_thumbnails: bool = True
    
    # Storage paths
    base_path: str = "/app/media"
    
    # Retention policies
    retention_type: str = "count"  # "count", "days", or "size"
    retention_count: int = 100  # Keep last N clips per camera
    retention_days: int = 30  # Keep last N days
    retention_size_gb: float = 10.0  # Keep last N GB per camera
    
    # NAS settings
    use_nas: bool = False
    nas_type: str = "smb"  # "smb" or "nfs"
    nas_host: str = ""
    nas_share: str = ""
    nas_username: str = ""
    nas_password: str = ""
    nas_mount_point: str = "/mnt/nas"
    
    # Download interval
    check_interval_minutes: int = 15
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'MediaDownloadConfig':
        """Create config from dictionary."""
        return cls(
            enabled=config_dict.get("enabled", False),
            download_clips=config_dict.get("download_clips", True),
            download_thumbnails=config_dict.get("download_thumbnails", True),
            base_path=config_dict.get("base_path", "/app/media"),
            retention_type=config_dict.get("retention_type", "count"),
            retention_count=config_dict.get("retention_count", 100),
            retention_days=config_dict.get("retention_days", 30),
            retention_size_gb=config_dict.get("retention_size_gb", 10.0),
            use_nas=config_dict.get("use_nas", False),
            nas_type=config_dict.get("nas_type", "smb"),
            nas_host=config_dict.get("nas_host", ""),
            nas_share=config_dict.get("nas_share", ""),
            nas_username=config_dict.get("nas_username", ""),
            nas_password=config_dict.get("nas_password", ""),
            nas_mount_point=config_dict.get("nas_mount_point", "/mnt/nas"),
            check_interval_minutes=config_dict.get("check_interval_minutes", 15),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)


class MediaManager:
    """Manages automatic downloading and retention of Blink media."""
    
    def __init__(self, blink_handler, config: MediaDownloadConfig, history_manager=None, logger: Optional[logging.Logger] = None):
        """
        Initialize media manager.
        
        Args:
            blink_handler: BlinkHandler instance for API access
            config: MediaDownloadConfig instance
            history_manager: HistoryManager instance for database tracking
            logger: Logger instance
        """
        self.blink_handler = blink_handler
        self.config = config
        self.history_manager = history_manager
        self.logger = logger or logging.getLogger(__name__)
        self.tracking_file = Path("/app/media_tracking.json")
        self.downloaded_clips: Dict[str, Set[str]] = {}  # camera_name -> set of clip IDs
        self.downloaded_thumbnails: Dict[str, str] = {}  # camera_name -> latest thumbnail ID
        self.download_start_time: Optional[str] = None  # When media downloads were first enabled
        self.last_check_time: Optional[str] = None  # Last successful check time
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        
        self._load_tracking()
    
    def _load_tracking(self) -> None:
        """Load tracking data from file and database."""
        try:
            # First, try loading from database if available
            if self.history_manager:
                try:
                    # Get all media downloads from database
                    media_history = self.history_manager.get_all_media_downloads()
                    
                    # Build downloaded clips set from database records
                    self.downloaded_clips = {}
                    for record in media_history:
                        if record.media_type == 'clip':
                            if record.camera_name not in self.downloaded_clips:
                                self.downloaded_clips[record.camera_name] = set()
                            self.downloaded_clips[record.camera_name].add(record.media_id)
                        elif record.media_type == 'thumbnail':
                            self.downloaded_thumbnails[record.camera_name] = record.media_id
                    
                    self.logger.info(f"Loaded tracking data from database: {len(self.downloaded_clips)} cameras tracked")
                except Exception as db_error:
                    self.logger.warning(f"Failed to load from database, falling back to JSON: {db_error}")
            
            # Fall back to JSON file if database not available or failed
            if self.tracking_file.exists():
                with open(self.tracking_file, 'r') as f:
                    data = json.load(f)
                    # Only load if not already loaded from database
                    if not self.downloaded_clips:
                        self.downloaded_clips = {k: set(v) for k, v in data.get("clips", {}).items()}
                    if not self.downloaded_thumbnails:
                        self.downloaded_thumbnails = data.get("thumbnails", {})
                    self.download_start_time = data.get("download_start_time")
                    self.last_check_time = data.get("last_check_time")
                self.logger.info(f"Loaded tracking data from JSON file")
        except Exception as e:
            self.logger.warning(f"Failed to load tracking data: {e}")
            self.downloaded_clips = {}
            self.downloaded_thumbnails = {}
            self.download_start_time = None
            self.last_check_time = None
    
    def _save_tracking(self) -> None:
        """Save tracking data to file."""
        try:
            self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.tracking_file, 'w') as f:
                json.dump({
                    "clips": {k: list(v) for k, v in self.downloaded_clips.items()},
                    "thumbnails": self.downloaded_thumbnails,
                    "download_start_time": self.download_start_time,
                    "last_check_time": self.last_check_time
                }, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save tracking data: {e}")
    
    def _get_storage_path(self) -> Path:
        """Get the base storage path (local or NAS mount)."""
        if self.config.use_nas:
            return Path(self.config.nas_mount_point) / Path(self.config.base_path).name
        return Path(self.config.base_path)
    
    def _get_camera_clip_path(self, sync_name: str, camera_name: str) -> Path:
        """Get the directory path for camera clips."""
        base = self._get_storage_path()
        return base / "clips" / sync_name / camera_name
    
    def _get_camera_thumbnail_path(self, sync_name: str, camera_name: str) -> Path:
        """Get the directory path for camera thumbnails."""
        base = self._get_storage_path()
        return base / "thumbnails" / sync_name / camera_name
    
    async def _ensure_nas_mounted(self) -> bool:
        """Ensure NAS is mounted if configured."""
        if not self.config.use_nas:
            return True
        
        mount_point = Path(self.config.nas_mount_point)
        
        # Check if already mounted
        if mount_point.exists() and any(mount_point.iterdir()):
            return True
        
        try:
            mount_point.mkdir(parents=True, exist_ok=True)
            
            if self.config.nas_type == "smb":
                # Mount SMB/CIFS share
                cmd = [
                    "mount", "-t", "cifs",
                    f"//{self.config.nas_host}/{self.config.nas_share}",
                    str(mount_point),
                    "-o", f"username={self.config.nas_username},password={self.config.nas_password}"
                ]
            else:  # nfs
                # Mount NFS share
                cmd = [
                    "mount", "-t", "nfs",
                    f"{self.config.nas_host}:{self.config.nas_share}",
                    str(mount_point)
                ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.logger.info(f"Successfully mounted NAS at {mount_point}")
                return True
            else:
                self.logger.error(f"Failed to mount NAS: {stderr.decode()}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error mounting NAS: {e}")
            return False
    
    async def download_clip(self, camera_name: str, sync_name: str, clip_id: str, clip_url: str, created_at: str = None) -> Optional[Path]:
        """
        Download a single clip.
        
        Args:
            camera_name: Name of the camera
            sync_name: Name of the sync module
            clip_id: Unique clip identifier
            clip_url: URL to download clip from
            created_at: Optional creation timestamp from clip metadata
            
        Returns:
            Path to downloaded file or None if failed
        """
        try:
            clip_path = self._get_camera_clip_path(sync_name, camera_name)
            clip_path.mkdir(parents=True, exist_ok=True)
            
            # Create filename from timestamp
            if created_at:
                # Use the clip's actual creation time
                try:
                    from dateutil.parser import parse
                    dt = parse(created_at)
                    timestamp = dt.strftime("%Y%m%d_%H%M%S")
                except:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            filename = f"{timestamp}.mp4"
            file_path = clip_path / filename
            
            # Download using blink handler
            if not self.blink_handler or not self.blink_handler.blink:
                return None
            
            # Get camera object
            camera = None
            for sync in self.blink_handler.blink.sync.values():
                if hasattr(sync, 'cameras') and camera_name in sync.cameras:
                    camera = sync.cameras[camera_name]
                    break
            
            if not camera:
                return None
            
            # Construct full URL from relative path
            full_url = clip_url
            if clip_url.startswith('/'):
                # Relative URL - prepend base URL
                base_url = self.blink_handler.blink.urls.base_url
                full_url = f"{base_url}{clip_url}"
            
            # Download the clip using the full URL - returns ClientResponse
            response = await camera.get_video_clip(url=full_url)
            if response and hasattr(response, 'status') and response.status == 200:
                # Read bytes from response
                clip_data = await response.read()
                if clip_data:
                    with open(file_path, 'wb') as f:
                        f.write(clip_data)
                    
                    self.logger.info(f"Downloaded clip {clip_id} for {camera_name}")
                    
                    # Record in database if history manager is available
                    if self.history_manager:
                        try:
                            file_size = file_path.stat().st_size
                            self.history_manager.record_media_download(
                                camera_name=camera_name,
                                sync_name=sync_name,
                                media_type='clip',
                                media_id=clip_id,
                                file_path=str(file_path),
                                file_size_bytes=file_size,
                                created_at=created_at
                            )
                        except Exception as db_error:
                            self.logger.warning(f"Failed to record clip download in database: {db_error}")
                    
                    # Generate thumbnail from video
                    try:
                        await self._generate_video_thumbnail(file_path)
                    except Exception as thumb_error:
                        self.logger.warning(f"Failed to generate thumbnail for {file_path.name}: {thumb_error}")
                    
                    return file_path
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to download clip {clip_id}: {e}", exc_info=True)
            return None
    
    async def download_thumbnail(self, camera_name: str, sync_name: str) -> Optional[Path]:
        """
        Download latest thumbnail for a camera.
        
        Args:
            camera_name: Name of the camera
            sync_name: Name of the sync module
            
        Returns:
            Path to downloaded file or None if failed
        """
        try:
            thumb_path = self._get_camera_thumbnail_path(sync_name, camera_name)
            thumb_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}.jpg"
            file_path = thumb_path / filename
            
            # Download thumbnail using blink handler
            if not self.blink_handler or not self.blink_handler.blink:
                return None
            
            # Get camera object
            camera = None
            for sync in self.blink_handler.blink.sync.values():
                if hasattr(sync, 'cameras') and camera_name in sync.cameras:
                    camera = sync.cameras[camera_name]
                    break
            
            if not camera:
                return None
            
            # Download thumbnail - returns ClientResponse
            response = await camera.get_thumbnail()
            if response and hasattr(response, 'status') and response.status == 200:
                # Read bytes from response
                thumbnail_data = await response.read()
                if thumbnail_data:
                    with open(file_path, 'wb') as f:
                        f.write(thumbnail_data)
                    
                    self.logger.info(f"Downloaded thumbnail for {camera_name}")
                    
                    # Record in database if history manager is available  
                    if self.history_manager:
                        try:
                            file_size = file_path.stat().st_size
                            self.history_manager.record_media_download(
                                camera_name=camera_name,
                                sync_name=sync_name,
                                media_type='thumbnail',
                                media_id=timestamp,
                                file_path=str(file_path),
                                file_size_bytes=file_size
                            )
                        except Exception as db_error:
                            self.logger.warning(f"Failed to record thumbnail download in database: {db_error}")
                    
                    return file_path
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to download thumbnail: {e}", exc_info=True)
            return None
    
    async def _generate_video_thumbnail(self, video_path: Path) -> Optional[Path]:
        """
        Generate a thumbnail image from a video file.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Path to generated thumbnail or None if failed
        """
        try:
            import subprocess
            
            thumb_path = video_path.with_suffix('.jpg')
            
            # Use ffmpeg to extract a frame at 1 second into the video
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-ss', '00:00:01',  # Seek to 1 second
                '-vframes', '1',     # Extract 1 frame
                '-vf', 'scale=320:-1',  # Resize to 320px width
                '-y',               # Overwrite output file
                str(thumb_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and thumb_path.exists():
                self.logger.debug(f"Generated thumbnail for {video_path.name}")
                return thumb_path
            else:
                self.logger.warning(f"ffmpeg failed to generate thumbnail: {stderr.decode()}")
                return None
                
        except FileNotFoundError:
            self.logger.warning("ffmpeg not found - video thumbnails will not be generated")
            return None
        except Exception as e:
            self.logger.warning(f"Failed to generate video thumbnail: {e}")
            return None
    
    async def check_and_download_new_media(self) -> None:
        """Check for new clips and thumbnails and download them."""
        if not self.config.enabled:
            return
        
        if not self.blink_handler or not self.blink_handler.blink:
            self.logger.warning("Blink handler not available")
            return
        
        # Set the start time if not already set (first time enabled)
        if not self.download_start_time:
            self.download_start_time = datetime.now().isoformat()
            self._save_tracking()
            self.logger.info(f"Media downloads enabled, starting from {self.download_start_time}")
        
        # Ensure NAS is mounted if configured
        if self.config.use_nas:
            if not await self._ensure_nas_mounted():
                self.logger.error("Failed to mount NAS, skipping download")
                return
        
        try:
            # Iterate through all cameras
            for sync_name, sync in self.blink_handler.blink.sync.items():
                if not hasattr(sync, 'cameras'):
                    continue
                
                for camera_name, camera in sync.cameras.items():
                    # Initialize tracking for this camera if needed
                    if camera_name not in self.downloaded_clips:
                        self.downloaded_clips[camera_name] = set()
                    
                    # Download clips if enabled
                    if self.config.download_clips:
                        await self._download_new_clips(camera_name, sync_name, camera)
                    
                    # Download thumbnails if enabled
                    if self.config.download_thumbnails:
                        await self._download_new_thumbnail(camera_name, sync_name, camera)
            
            # Update last check time to now (for downtime recovery)
            self.last_check_time = datetime.now().isoformat()
            
            # Save tracking data
            self._save_tracking()
            
            # Apply retention policies
            await self.apply_retention_policies()
            
        except Exception as e:
            self.logger.error(f"Error checking for new media: {e}", exc_info=True)
    
    async def _download_new_clips(self, camera_name: str, sync_name: str, camera: Any) -> None:
        """Download new clips for a camera."""
        try:
            # Get list of clips from Blink API
            if not self.blink_handler or not self.blink_handler.blink:
                self.logger.debug(f"Blink handler not available for {camera_name}")
                return
            
            # Use last_check_time if available (for downtime recovery), otherwise download_start_time
            # This allows catching up on clips missed while the app was down
            since_time = self.last_check_time or self.download_start_time
            since_date = datetime.fromisoformat(since_time)
            since_str = since_date.strftime("%Y/%m/%d %H:%M:%S")
            
            # Fetch video metadata from Blink - limit to 5 pages (~125 clips max)
            self.logger.debug(f"Fetching video metadata for {camera_name} since {since_str}")
            clips_metadata = await self.blink_handler.blink.get_videos_metadata(
                since=since_str,
                stop=5
            )
            
            self.logger.info(f"Found {len(clips_metadata)} total clips for {camera_name}")
            
            # Build clips list from metadata
            clips = []
            for clip_meta in clips_metadata:
                device_name = clip_meta.get('device_name')
                is_deleted = clip_meta.get('deleted', False)
                self.logger.debug(f"Clip metadata: device={device_name}, deleted={is_deleted}, camera={camera_name}")
                
                # Filter by camera name and skip deleted clips
                if device_name == camera_name and not is_deleted:
                    # Extract clip ID from media path (e.g., "/path/to/12345.mp4" -> "12345")
                    media_path = clip_meta.get('media', '')
                    created_at = clip_meta.get('created_at', '')
                    if media_path:
                        # Use the full media path as clip ID (more unique than just filename)
                        clip_id = media_path.strip('/').replace('/', '_').replace('.mp4', '')
                        if clip_id and clip_id not in self.downloaded_clips[camera_name]:
                            clips.append({
                                'id': clip_id,
                                'url': media_path,
                                'created_at': created_at
                            })
                            self.logger.debug(f"Added clip {clip_id} to download queue")
            
            self.logger.info(f"Found {len(clips)} new clips to download for {camera_name}")
            
            # Download each new clip
            for clip in clips:
                clip_id = clip.get('id')
                if clip_id not in self.downloaded_clips[camera_name]:
                    clip_url = clip.get('url')
                    created_at = clip.get('created_at')
                    if await self.download_clip(camera_name, sync_name, clip_id, clip_url, created_at):
                        self.downloaded_clips[camera_name].add(clip_id)
                        
        except Exception as e:
            self.logger.error(f"Failed to download clips for {camera_name}: {e}", exc_info=True)
    
    async def _download_new_thumbnail(self, camera_name: str, sync_name: str, camera: Any) -> None:
        """Download new thumbnail for a camera if changed."""
        try:
            # Check if thumbnail has changed (simplified)
            await self.download_thumbnail(camera_name, sync_name)
        except Exception as e:
            self.logger.error(f"Failed to download thumbnail for {camera_name}: {e}")
    
    async def apply_retention_policies(self) -> None:
        """Apply retention policies to downloaded media."""
        if not self.config.enabled:
            return
        
        try:
            base_path = self._get_storage_path()
            
            # Apply retention to clips
            if self.config.download_clips:
                clips_path = base_path / "clips"
                if clips_path.exists():
                    await self._apply_retention_recursive(clips_path)
            
            # Apply retention to thumbnails
            if self.config.download_thumbnails:
                thumbnails_path = base_path / "thumbnails"
                if thumbnails_path.exists():
                    await self._apply_retention_recursive(thumbnails_path)
                    
        except Exception as e:
            self.logger.error(f"Error applying retention policies: {e}")
    
    async def _apply_retention_recursive(self, path: Path) -> None:
        """Recursively apply retention policies to all camera folders."""
        for sync_dir in path.iterdir():
            if not sync_dir.is_dir():
                continue
            for camera_dir in sync_dir.iterdir():
                if not camera_dir.is_dir():
                    continue
                await self._apply_retention_to_folder(camera_dir)
    
    async def _apply_retention_to_folder(self, folder: Path) -> None:
        """Apply retention policy to a single camera folder."""
        try:
            files = sorted(folder.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)
            
            if self.config.retention_type == "count":
                # Keep only the N most recent files
                for file in files[self.config.retention_count:]:
                    file.unlink()
                    self.logger.debug(f"Deleted old file (count): {file}")
                    
            elif self.config.retention_type == "days":
                # Keep files from last N days
                cutoff = datetime.now() - timedelta(days=self.config.retention_days)
                for file in files:
                    if datetime.fromtimestamp(file.stat().st_mtime) < cutoff:
                        file.unlink()
                        self.logger.debug(f"Deleted old file (days): {file}")
                        
            elif self.config.retention_type == "size":
                # Keep files until size limit reached
                total_size = 0
                size_limit = self.config.retention_size_gb * 1024 * 1024 * 1024  # Convert GB to bytes
                for file in files:
                    total_size += file.stat().st_size
                    if total_size > size_limit:
                        file.unlink()
                        self.logger.debug(f"Deleted old file (size): {file}")
                        
        except Exception as e:
            self.logger.error(f"Error applying retention to {folder}: {e}")
    
    async def run_periodic_check(self) -> None:
        """Run periodic checks for new media."""
        self.is_running = True
        self.logger.info(f"Starting periodic media check (interval: {self.config.check_interval_minutes} minutes)")
        
        while self.is_running:
            try:
                await self.check_and_download_new_media()
                await asyncio.sleep(self.config.check_interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in periodic media check: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before retrying
        
        self.logger.info("Stopped periodic media check")
    
    def start(self, event_loop: asyncio.AbstractEventLoop) -> None:
        """Start the media manager."""
        if not self.config.enabled:
            self.logger.info("Media manager disabled")
            return
        
        if self.task and not self.task.done():
            self.logger.warning("Media manager already running")
            return
        
        self.task = event_loop.create_task(self.run_periodic_check())
        self.logger.info("Media manager started")
    
    def stop(self) -> None:
        """Stop the media manager."""
        self.is_running = False
        if self.task:
            self.task.cancel()
        self.logger.info("Media manager stopped")
