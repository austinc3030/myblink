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

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.serving import make_server
import threading

# Type checking
try:
    from myblink import MyBlink, AppConfig
except ImportError:
    pass


class WebServer:
    """
    Flask-based web server for MyBlink management interface.
    
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
        
        # Create Flask app
        self.app = Flask(__name__, 
                         static_folder='web_static',
                         static_url_path='/static')
        
        # Setup routes
        self._setup_routes()
        
        # Server thread
        self.server: Optional[Any] = None
        self.server_thread: Optional[threading.Thread] = None
    
    def _setup_routes(self) -> None:
        """Setup Flask routes."""
        
        # Frontend routes
        @self.app.route('/')
        def index():
            """Serve main page."""
            return send_from_directory('web_static', 'index.html')
        
        @self.app.route('/manifest.json')
        def manifest():
            """Serve PWA manifest."""
            return send_from_directory('web_static', 'manifest.json')
        
        @self.app.route('/sw.js')
        def service_worker():
            """Serve service worker."""
            return send_from_directory('web_static', 'sw.js')
        
        # Setup/Configuration API routes
        @self.app.route('/api/setup/status')
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
        
        # Camera/Sync state API routes
        @self.app.route('/api/state')
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
        def get_config():
            """Get current configuration."""
            try:
                config = self._get_config()
                return jsonify(config)
            except Exception as e:
                self.logger.error(f"Error getting config: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/config', methods=['POST'])
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
        
        @self.app.route('/api/sync/<sync_name>/snooze', methods=['POST'])
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
            "theme": config.web_theme
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
        if not self.myblink_app.config or not self.myblink_app._config_file:
            return
        
        config = self.myblink_app.config
        config_dict = {
            "debug_mode": config.debug_mode,
            "health_file": config.health_file,
            "health_check_interval": config.health_check_interval,
            "max_consecutive_errors": config.max_consecutive_errors,
            "blink_retry_limit": config.blink_retry_limit,
            "snooze_syncs": config.snooze_syncs,
            "no_snooze_syncs": config.no_snooze_syncs,
            "snooze_cams": config.snooze_cams,
            "no_snooze_cams": config.no_snooze_cams,
            "arm_syncs": config.arm_syncs,
            "no_arm_syncs": config.no_arm_syncs,
            "arm_cams": config.arm_cams,
            "no_arm_cams": config.no_arm_cams,
            "thumbnail_cams": config.thumbnail_cams,
            "no_thumbnail_cams": config.no_thumbnail_cams,
            "voipms_message_keyword": config.voipms_message_keyword,
            "voipms_retry_limit": config.voipms_retry_limit,
            "voipms_retry_delay": config.voipms_retry_delay,
            "voipms_sms_wait": config.voipms_sms_wait,
            "schedule_interval_hours": config.schedule_interval_hours,
            "status_log_interval": config.status_log_interval,
            "main_loop_sleep": config.main_loop_sleep,
            "error_recovery_sleep": config.error_recovery_sleep,
            "web_enabled": config.web_enabled,
            "web_port": config.web_port,
            "web_host": config.web_host,
        }
        
        with open(self.myblink_app._config_file, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
        
        self.logger.info(f"Configuration saved to {self.myblink_app._config_file}")
    
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
