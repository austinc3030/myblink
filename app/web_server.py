"""
Web interface for MyBlink camera management.

Provides a responsive PWA web interface for managing Blink cameras,
including toggling snooze/arm/thumbnail operations and configuration.
"""

import asyncio
import json
import logging
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_from_directory, Response
from werkzeug.serving import make_server
import threading

# Import authentication modules
from modules import AuthConfig, AuthManager

# Type checking
try:
    from myblink import MyBlink, AppConfig
except ImportError:
    pass


class WebServer:
    """Flask-based web server for MyBlink management interface.
    
    Provides REST API endpoints and serves the PWA frontend for
    managing camera operations and configuration.
    """
    
    def __init__(self, myblink_app: 'MyBlink', host: str = "0.0.0.0", port: int = 8080):
        """
        Initialize web server.
        
        Args:
            myblink_app: MyBlink application instance
            host: Host to bind to
            port: Port to listen on
        """
        self.myblink_app = myblink_app
        self.host = host
        self.port = port
        self.logger = logging.getLogger(__name__)
        
        # Log storage (in-memory for now)
        self.web_logs: List[Dict[str, str]] = []
        self.blink_logs: List[Dict[str, str]] = []
        self.max_logs = 1000  # Keep last 1000 logs
        
        # Setup log handler
        self._setup_log_handler()
        
        # Create Flask app
        self.app = Flask(__name__, 
                         static_folder='web_static',
                         static_url_path='/static')
        
        # Initialize authentication
        self.auth_manager: Optional[AuthManager] = None
        self._init_authentication()
        
        # Setup routes
        self._setup_routes()
        
        # Server thread
        self.server: Optional[Any] = None
        self.server_thread: Optional[threading.Thread] = None
    
    def _init_authentication(self) -> None:
        """Initialize authentication if enabled."""
        try:
            auth_config_dict = self.myblink_app.config.get_auth_config()
            auth_config = AuthConfig.from_dict(auth_config_dict)
            
            if auth_config.enabled:
                self.auth_manager = AuthManager(self.app, auth_config)
                self.logger.info(f"Authentication enabled: method={auth_config.method}")
            else:
                self.logger.info("Authentication disabled")
        except Exception as e:
            self.logger.error(f"Failed to initialize authentication: {e}")
            self.auth_manager = None
    
    def _setup_log_handler(self) -> None:
        """Setup log handler to capture logs for web interface."""
        class LogCapture(logging.Handler):
            def __init__(self, web_server):
                super().__init__()
                self.web_server = web_server
            
            def emit(self, record):
                try:
                    log_entry = {
                        'message': self.format(record),
                        'level': record.levelname
                    }
                    
                    # Separate web logs from blink logs
                    if record.name.startswith('werkzeug') or record.name == __name__:
                        self.web_server.web_logs.append(log_entry)
                        if len(self.web_server.web_logs) > self.web_server.max_logs:
                            self.web_server.web_logs.pop(0)
                    else:
                        self.web_server.blink_logs.append(log_entry)
                        if len(self.web_server.blink_logs) > self.web_server.max_logs:
                            self.web_server.blink_logs.pop(0)
                except Exception:
                    pass
        
        # Add handler to root logger
        handler = LogCapture(self)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(handler)
    
    def _require_auth(self, f):
        """Helper to apply auth decorator if auth is enabled."""
        if self.auth_manager:
            return self.auth_manager.require_auth(f)
        return f
    
    def _setup_routes(self) -> None:
        """Setup Flask routes."""
        
        # Frontend routes - no auth required for static assets
        # Main page requires auth if enabled
        @self.app.route('/')
        @self._require_auth
        def index():
            """Serve main page."""
            return send_from_directory('web_static', 'index_new.html')
        
        @self.app.route('/static/app.js')
        def app_js():
            """Serve app JavaScript."""
            return send_from_directory('web_static', 'app_new.js')
        
        @self.app.route('/manifest.json')
        def manifest():
            """Serve PWA manifest."""
            return send_from_directory('web_static', 'manifest.json')
        
        @self.app.route('/sw.js')
        def service_worker():
            """Serve service worker."""
            return send_from_directory('web_static', 'sw.js')
        
        # Setup/Configuration API routes - require auth
        @self.app.route('/api/setup/status')
        @self._require_auth
        def setup_status():
            """Check if application is configured."""
            try:
                return jsonify({
                    "configured": self.myblink_app.is_configured()
                })
            except Exception as e:
                self.logger.error(f"Error checking setup status: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/setup/credentials', methods=['POST'])
        def save_credentials():
            """Save credentials and initialize services."""
            try:
                data = request.get_json()
                
                # Validate required fields
                if not data:
                    return jsonify({"error": "No data provided"}), 400
                
                required_fields = [
                    ('blink', 'username'),
                    ('blink', 'password'),
                    ('voipms', 'username'),
                    ('voipms', 'password'),
                    ('voipms', 'did')
                ]
                
                for section, field in required_fields:
                    if section not in data or field not in data[section]:
                        return jsonify({"error": f"Missing required field: {section}.{field}"}), 400
                
                # Set credentials (this will also initialize services)
                self.myblink_app.set_credentials(data)
                
                return jsonify({"success": True, "message": "Credentials saved successfully"})
                
            except Exception as e:
                self.logger.error(f"Error saving credentials: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/setup/start', methods=['POST'])
        @self._require_auth
        def start_system():
            """Initialize Blink system and start operations."""
            try:
                if not self.myblink_app.is_configured():
                    return jsonify({"error": "Application not configured"}), 400
                
                # Initialize Blink in event loop
                if self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        self.myblink_app.initialize_blink(),
                        self.myblink_app._event_loop
                    )
                    future.result(timeout=60)
                    
                    # Run initial jobs
                    future = asyncio.run_coroutine_threadsafe(
                        self.myblink_app.run_scheduled_jobs(),
                        self.myblink_app._event_loop
                    )
                    future.result(timeout=300)
                    
                return jsonify({"success": True, "message": "System started successfully"})
                
            except Exception as e:
                self.logger.error(f"Error starting system: {e}")
                return jsonify({"error": str(e)}), 500
        
        # Camera/Sync state API routes - require auth
        @self.app.route('/api/state')
        @self._require_auth
        def get_state():
            """Get current state of all cameras and syncs."""
            try:
                # Check if configured
                if not self.myblink_app.is_configured():
                    return jsonify({"configured": False})
                
                state = self._get_current_state()
                state["configured"] = True
                return jsonify(state)
            except Exception as e:
                self.logger.error(f"Error getting state: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/config')
        @self._require_auth
        def get_config():
            """Get current configuration."""
            try:
                config = self._get_config()
                return jsonify(config)
            except Exception as e:
                self.logger.error(f"Error getting config: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/config', methods=['POST'])
        @self._require_auth
        def update_config():
            """Update configuration."""
            try:
                data = request.get_json()
                self._update_config(data)
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error updating config: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/snooze', methods=['POST'])
        @self._require_auth
        def toggle_camera_snooze(camera_name: str):
            """Toggle snooze for a specific camera."""
            try:
                data = request.get_json()
                enabled = data.get('enabled', False)
                self._update_camera_setting(camera_name, 'snooze', enabled)
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error toggling camera snooze: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/arm', methods=['POST'])
        @self._require_auth
        def toggle_camera_arm(camera_name: str):
            """Toggle arm for a specific camera."""
            try:
                data = request.get_json()
                enabled = data.get('enabled', False)
                self._update_camera_setting(camera_name, 'arm', enabled)
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error toggling camera arm: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/thumbnail', methods=['POST'])
        @self._require_auth
        def toggle_camera_thumbnail(camera_name: str):
            """Toggle thumbnail for a specific camera."""
            try:
                data = request.get_json()
                enabled = data.get('enabled', False)
                self._update_camera_setting(camera_name, 'thumbnail', enabled)
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error toggling camera thumbnail: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/info', methods=['GET'])
        @self._require_auth
        def get_camera_info(camera_name: str):
            """Get detailed information about a specific camera."""
            try:
                camera = self._find_camera(camera_name)
                if not camera:
                    return jsonify({"error": "Camera not found"}), 404
                
                # Get camera attributes
                info = camera.attributes.copy()
                
                # Add cached image/video availability
                info['has_cached_thumbnail'] = camera.image_from_cache is not None
                info['has_cached_video'] = camera.video_from_cache is not None
                info['has_recent_clips'] = len(camera.recent_clips) > 0
                
                # Convert None values to strings for JSON
                for key, value in info.items():
                    if value is None:
                        info[key] = "N/A"
                
                return jsonify(info)
            except Exception as e:
                self.logger.error(f"Error getting camera info: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/media/thumbnail', methods=['GET'])
        @self._require_auth
        def get_camera_thumbnail(camera_name: str):
            """Get cached thumbnail for a camera without triggering a new capture."""
            try:
                camera = self._find_camera(camera_name)
                if not camera:
                    return jsonify({"error": "Camera not found"}), 404
                
                if not camera.image_from_cache:
                    return jsonify({"error": "No cached thumbnail available"}), 404
                
                # Return the cached image
                return Response(camera.image_from_cache, mimetype='image/jpeg')
            except Exception as e:
                self.logger.error(f"Error getting camera thumbnail: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/media/thumbnail/new', methods=['POST'])
        @self._require_auth
        def capture_camera_thumbnail(camera_name: str):
            """Capture a new thumbnail for a camera and return it."""
            try:
                camera = self._find_camera(camera_name)
                if not camera:
                    return jsonify({"error": "Camera not found"}), 404
                
                # Run async snap_picture in event loop
                if self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        camera.snap_picture(),
                        self.myblink_app._event_loop
                    )
                    future.result(timeout=30)
                    
                    # Get the newly captured thumbnail
                    future = asyncio.run_coroutine_threadsafe(
                        camera.get_media(),
                        self.myblink_app._event_loop
                    )
                    future.result(timeout=30)
                    
                    if camera.image_from_cache:
                        return Response(camera.image_from_cache, mimetype='image/jpeg')
                    else:
                        return jsonify({"error": "Failed to capture thumbnail"}), 500
                else:
                    return jsonify({"error": "Event loop not available"}), 500
            except Exception as e:
                self.logger.error(f"Error capturing camera thumbnail: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/media/clip', methods=['GET'])
        @self._require_auth
        def get_camera_clip(camera_name: str):
            """Get the latest video clip for a camera."""
            try:
                camera = self._find_camera(camera_name)
                if not camera:
                    return jsonify({"error": "Camera not found"}), 404
                
                if not camera.video_from_cache:
                    return jsonify({"error": "No cached video clip available"}), 404
                
                # Return the cached video
                return Response(camera.video_from_cache, mimetype='video/mp4')
            except Exception as e:
                self.logger.error(f"Error getting camera clip: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/media/clips', methods=['GET'])
        @self._require_auth
        def get_camera_clips(camera_name: str):
            """Get list of recent clips for a camera."""
            try:
                camera = self._find_camera(camera_name)
                if not camera:
                    return jsonify({"error": "Camera not found"}), 404
                
                # Return recent clips list
                clips = camera.recent_clips if camera.recent_clips else []
                return jsonify({"clips": clips})
            except Exception as e:
                self.logger.error(f"Error getting camera clips: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/media/clip/download', methods=['POST'])
        @self._require_auth
        def download_camera_clip(camera_name: str):
            """Download a specific clip by URL."""
            try:
                camera = self._find_camera(camera_name)
                if not camera:
                    return jsonify({"error": "Camera not found"}), 404
                
                data = request.get_json()
                clip_url = data.get('clip_url')
                
                if not clip_url:
                    return jsonify({"error": "clip_url is required"}), 400
                
                # Run async get_video_clip in event loop
                if self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        camera.get_video_clip(url=clip_url),
                        self.myblink_app._event_loop
                    )
                    response = future.result(timeout=60)
                    
                    if response and response.status == 200:
                        # Read the video data in the event loop
                        future = asyncio.run_coroutine_threadsafe(
                            response.read(),
                            self.myblink_app._event_loop
                        )
                        video_data = future.result(timeout=60)
                        
                        return Response(video_data, mimetype='video/mp4')
                    else:
                        return jsonify({"error": "Failed to download clip"}), 500
                else:
                    return jsonify({"error": "Event loop not available"}), 500
            except Exception as e:
                self.logger.error(f"Error downloading camera clip: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/night_vision', methods=['GET'])
        @self._require_auth
        def get_night_vision(camera_name: str):
            """Get night vision setting for a camera."""
            try:
                camera = self._find_camera(camera_name)
                if not camera:
                    return jsonify({"error": "Camera not found"}), 404
                
                # Get night vision status
                if self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        camera.night_vision,
                        self.myblink_app._event_loop
                    )
                    nv_status = future.result(timeout=30)
                    return jsonify({"night_vision": nv_status})
                else:
                    return jsonify({"error": "Event loop not available"}), 500
            except Exception as e:
                self.logger.error(f"Error getting night vision: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/night_vision', methods=['POST'])
        @self._require_auth
        def set_night_vision(camera_name: str):
            """Set night vision mode for a camera."""
            try:
                camera = self._find_camera(camera_name)
                if not camera:
                    return jsonify({"error": "Camera not found"}), 404
                
                data = request.get_json()
                mode = data.get('mode', '').lower()
                
                if mode not in ['on', 'off', 'auto']:
                    return jsonify({"error": "Invalid mode. Must be 'on', 'off', or 'auto'"}), 400
                
                # Set night vision mode
                if self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        camera.async_set_night_vision(mode),
                        self.myblink_app._event_loop
                    )
                    result = future.result(timeout=30)
                    
                    if result:
                        return jsonify({"success": True, "mode": mode})
                    else:
                        return jsonify({"error": "Failed to set night vision"}), 500
                else:
                    return jsonify({"error": "Event loop not available"}), 500
            except Exception as e:
                self.logger.error(f"Error setting night vision: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/record', methods=['POST'])
        @self._require_auth
        def start_recording(camera_name: str):
            """Start video recording on a camera."""
            try:
                camera = self._find_camera(camera_name)
                if not camera:
                    return jsonify({"error": "Camera not found"}), 404
                
                # Start recording
                if self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        camera.record(),
                        self.myblink_app._event_loop
                    )
                    result = future.result(timeout=30)
                    
                    if result:
                        return jsonify({"success": True, "message": "Recording started"})
                    else:
                        return jsonify({"error": "Failed to start recording"}), 500
                else:
                    return jsonify({"error": "Event loop not available"}), 500
            except Exception as e:
                self.logger.error(f"Error starting recording: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/sync/<sync_name>/snooze', methods=['POST'])
        @self._require_auth
        def toggle_sync_snooze(sync_name: str):
            """Toggle snooze for a sync module."""
            try:
                data = request.get_json()
                enabled = data.get('enabled', False)
                self._update_sync_setting(sync_name, 'snooze', enabled)
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error toggling sync snooze: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/sync/<sync_name>/arm', methods=['POST'])
        @self._require_auth
        def toggle_sync_arm(sync_name: str):
            """Toggle arm for a sync module."""
            try:
                data = request.get_json()
                enabled = data.get('enabled', False)
                self._update_sync_setting(sync_name, 'arm', enabled)
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error toggling sync arm: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/refresh', methods=['POST'])
        @self._require_auth
        def refresh():
            """Refresh camera list from Blink."""
            try:
                # Run async refresh in event loop
                if self.myblink_app.blink and self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        self.myblink_app.blink.refresh(force=True),
                        self.myblink_app._event_loop
                    )
                    future.result(timeout=30)
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error refreshing: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/run-jobs', methods=['POST'])
        @self._require_auth
        def run_jobs():
            """Manually trigger scheduled jobs."""
            try:
                if self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        self.myblink_app.run_scheduled_jobs(),
                        self.myblink_app._event_loop
                    )
                    future.result(timeout=300)
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error running jobs: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/logs')
        @self._require_auth
        def get_logs():
            """Get web and blink logs."""
            try:
                return jsonify({
                    "web_logs": self.web_logs[-500:],  # Last 500 logs
                    "blink_logs": self.blink_logs[-500:]
                })
            except Exception as e:
                self.logger.error(f"Error getting logs: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/logs/clear', methods=['POST'])
        @self._require_auth
        def clear_logs():
            """Clear all logs."""
            try:
                self.web_logs.clear()
                self.blink_logs.clear()
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error clearing logs: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/credentials', methods=['POST'])
        @self._require_auth
        def update_credentials():
            """Update credentials (passwords are optional)."""
            try:
                data = request.get_json()
                
                if not data:
                    return jsonify({"error": "No data provided"}), 400
                
                # Build credentials dict, preserving existing if not provided
                creds_dict = {}
                
                if 'blink' in data:
                    creds_dict['blink'] = {
                        'username': data['blink'].get('username', self.myblink_app.config.blink_username if self.myblink_app.config else ''),
                        'password': data['blink'].get('password', self.myblink_app.config.blink_password if self.myblink_app.config else '')
                    }
                
                if 'voipms' in data:
                    creds_dict['voipms'] = {
                        'username': data['voipms'].get('username', self.myblink_app.config.voipms_username if self.myblink_app.config else ''),
                        'password': data['voipms'].get('password', self.myblink_app.config.voipms_password if self.myblink_app.config else ''),
                        'did': data['voipms'].get('did', self.myblink_app.config.voipms_did if self.myblink_app.config else '')
                    }
                
                # Update credentials
                self.myblink_app.set_credentials(creds_dict)
                
                return jsonify({"success": True, "message": "Credentials updated successfully"})
                
            except Exception as e:
                self.logger.error(f"Error updating credentials: {e}")
                return jsonify({"error": str(e)}), 500
    
    def _get_current_state(self) -> Dict[str, Any]:
        """Get current state of all cameras and syncs."""
        if not self.myblink_app.blink or not self.myblink_app.config:
            return {"syncs": [], "cameras": {}}
        
        config = self.myblink_app.config
        syncs = []
        
        for sync_name, sync in self.myblink_app.blink.sync.items():
            # Get sync-level settings
            sync_data = {
                "name": sync_name,
                "snooze_enabled": sync_name in config.snooze_syncs,
                "arm_enabled": sync_name in config.arm_syncs,
                "cameras": []
            }
            
            # Get cameras for this sync
            if hasattr(sync, 'cameras'):
                for camera_name, camera in sync.cameras.items():
                    camera_data = {
                        "name": camera_name,
                        "snooze_enabled": camera_name in config.snooze_cams,
                        "arm_enabled": camera_name in config.arm_cams,
                        "thumbnail_enabled": camera_name in config.thumbnail_cams
                    }
                    sync_data["cameras"].append(camera_data)
            
            syncs.append(sync_data)
        
        return {"syncs": syncs}
    
    def _get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        if not self.myblink_app.config:
            return {}
        
        config = self.myblink_app.config
        return {
            "schedule_interval_hours": config.schedule_interval_hours,
            "blink_retry_limit": config.blink_retry_limit,
            "voipms_sms_wait": config.voipms_sms_wait,
            "theme": config.web_theme,
            "blink_username": config.blink_username,
            "voipms_username": config.voipms_username,
            "voipms_did": config.voipms_did
        }
    
    def _update_config(self, data: Dict[str, Any]) -> None:
        """Update configuration and save to file."""
        if not self.myblink_app.config or not self.myblink_app._config_file:
            raise ValueError("Configuration not initialized")
        
        # Update in-memory config
        if 'schedule_interval_hours' in data:
            self.myblink_app.config.schedule_interval_hours = int(data['schedule_interval_hours'])
        if 'blink_retry_limit' in data:
            self.myblink_app.config.blink_retry_limit = int(data['blink_retry_limit'])
        if 'voipms_sms_wait' in data:
            self.myblink_app.config.voipms_sms_wait = int(data['voipms_sms_wait'])
        if 'theme' in data:
            self.myblink_app.config.web_theme = data['theme']
        
        # Save to file
        self._save_config_to_file()
    
    def _update_camera_setting(self, camera_name: str, setting: str, enabled: bool) -> None:
        """Update camera setting and save to file."""
        if not self.myblink_app.config:
            raise ValueError("Configuration not initialized")
        
        config = self.myblink_app.config
        
        if setting == 'snooze':
            # Remove from both lists first
            if camera_name in config.snooze_cams:
                config.snooze_cams.remove(camera_name)
            if camera_name in config.no_snooze_cams:
                config.no_snooze_cams.remove(camera_name)
            
            # Add to appropriate list
            if enabled:
                config.snooze_cams.append(camera_name)
            else:
                config.no_snooze_cams.append(camera_name)
        
        elif setting == 'arm':
            if camera_name in config.arm_cams:
                config.arm_cams.remove(camera_name)
            if camera_name in config.no_arm_cams:
                config.no_arm_cams.remove(camera_name)
            
            if enabled:
                config.arm_cams.append(camera_name)
            else:
                config.no_arm_cams.append(camera_name)
        
        elif setting == 'thumbnail':
            if camera_name in config.thumbnail_cams:
                config.thumbnail_cams.remove(camera_name)
            if camera_name in config.no_thumbnail_cams:
                config.no_thumbnail_cams.remove(camera_name)
            
            if enabled:
                config.thumbnail_cams.append(camera_name)
            else:
                config.no_thumbnail_cams.append(camera_name)
        
        # Check if all cameras in sync have same setting - optimize to sync level
        self._optimize_sync_settings()
        
        # Save to file
        self._save_config_to_file()
    
    def _update_sync_setting(self, sync_name: str, setting: str, enabled: bool) -> None:
        """Update sync setting and save to file."""
        if not self.myblink_app.config or not self.myblink_app.blink:
            raise ValueError("Configuration or Blink not initialized")
        
        config = self.myblink_app.config
        
        if setting == 'snooze':
            # Remove from both lists
            if sync_name in config.snooze_syncs:
                config.snooze_syncs.remove(sync_name)
            if sync_name in config.no_snooze_syncs:
                config.no_snooze_syncs.remove(sync_name)
            
            # Add to appropriate list
            if enabled:
                config.snooze_syncs.append(sync_name)
            else:
                config.no_snooze_syncs.append(sync_name)
            
            # Also update all cameras in this sync
            sync = self.myblink_app.blink.sync.get(sync_name)
            if sync and hasattr(sync, 'cameras'):
                for camera_name in sync.cameras.keys():
                    if camera_name in config.snooze_cams:
                        config.snooze_cams.remove(camera_name)
                    if camera_name in config.no_snooze_cams:
                        config.no_snooze_cams.remove(camera_name)
                    
                    if enabled:
                        config.snooze_cams.append(camera_name)
                    else:
                        config.no_snooze_cams.append(camera_name)
        
        elif setting == 'arm':
            if sync_name in config.arm_syncs:
                config.arm_syncs.remove(sync_name)
            if sync_name in config.no_arm_syncs:
                config.no_arm_syncs.remove(sync_name)
            
            if enabled:
                config.arm_syncs.append(sync_name)
            else:
                config.no_arm_syncs.append(sync_name)
            
            # Also update all cameras in this sync
            sync = self.myblink_app.blink.sync.get(sync_name)
            if sync and hasattr(sync, 'cameras'):
                for camera_name in sync.cameras.keys():
                    if camera_name in config.arm_cams:
                        config.arm_cams.remove(camera_name)
                    if camera_name in config.no_arm_cams:
                        config.no_arm_cams.remove(camera_name)
                    
                    if enabled:
                        config.arm_cams.append(camera_name)
                    else:
                        config.no_arm_cams.append(camera_name)
        
        # Save to file
        self._save_config_to_file()
    
    def _find_camera(self, camera_name: str) -> Optional[Any]:
        """
        Find a camera by name across all sync modules.
        
        Args:
            camera_name: Name of the camera to find
            
        Returns:
            Camera object if found, None otherwise
        """
        if not self.myblink_app.blink:
            return None
        
        for sync_name, sync in self.myblink_app.blink.sync.items():
            if hasattr(sync, 'cameras') and camera_name in sync.cameras:
                return sync.cameras[camera_name]
        
        return None
    
    def _optimize_sync_settings(self) -> None:
        """
        Optimize camera settings to sync-level when all cameras have same setting.
        
        If all cameras in a sync have the same setting, move the setting to the
        sync level to reduce API calls.
        """
        if not self.myblink_app.config or not self.myblink_app.blink:
            return
        
        config = self.myblink_app.config
        
        for sync_name, sync in self.myblink_app.blink.sync.items():
            if not hasattr(sync, 'cameras') or not sync.cameras:
                continue
            
            camera_names = list(sync.cameras.keys())
            
            # Check snooze settings
            all_snooze = all(cam in config.snooze_cams for cam in camera_names)
            all_no_snooze = all(cam in config.no_snooze_cams for cam in camera_names)
            
            if all_snooze and sync_name not in config.snooze_syncs:
                config.snooze_syncs.append(sync_name)
                if sync_name in config.no_snooze_syncs:
                    config.no_snooze_syncs.remove(sync_name)
            elif all_no_snooze and sync_name not in config.no_snooze_syncs:
                config.no_snooze_syncs.append(sync_name)
                if sync_name in config.snooze_syncs:
                    config.snooze_syncs.remove(sync_name)
            
            # Check arm settings
            all_arm = all(cam in config.arm_cams for cam in camera_names)
            all_no_arm = all(cam in config.no_arm_cams for cam in camera_names)
            
            if all_arm and sync_name not in config.arm_syncs:
                config.arm_syncs.append(sync_name)
                if sync_name in config.no_arm_syncs:
                    config.no_arm_syncs.remove(sync_name)
            elif all_no_arm and sync_name not in config.no_arm_syncs:
                config.no_arm_syncs.append(sync_name)
                if sync_name in config.arm_syncs:
                    config.arm_syncs.remove(sync_name)
    
    def _save_config_to_file(self) -> None:
        """Save current configuration to YAML file."""
        if not self.myblink_app.config or not hasattr(self.myblink_app, 'config_manager'):
            return
        
        # Update config_manager's config reference
        self.myblink_app.config_manager.config = self.myblink_app.config
        
        # Use ConfigManager's save method (handles all fields including auth)
        self.myblink_app.config_manager.save_config()
        
        self.logger.info("Configuration saved")
    
    def start(self) -> None:
        """Start the web server in a background thread."""
        self.logger.info(f"Starting web server on {self.host}:{self.port}")
        
        # Create server
        self.server = make_server(self.host, self.port, self.app, threaded=True)
        
        # Start in thread
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        
        self.logger.info(f"Web interface available at http://{self.host}:{self.port}")
    
    def stop(self) -> None:
        """Stop the web server."""
        if self.server:
            self.logger.info("Stopping web server")
            self.server.shutdown()
            if self.server_thread:
                self.server_thread.join(timeout=5)
