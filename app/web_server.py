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

from flask import Flask, jsonify, request, send_from_directory, Response, redirect, session
from flask_login import login_user
from werkzeug.serving import make_server
import threading

# Import authentication modules
from modules import AuthConfig, AuthManager
from modules.auth import User

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
    
    def _is_first_run(self) -> bool:
        """Check if this is the first run (no admin credentials configured)."""
        config = self.myblink_app.config
        # First run if auth is not enabled OR no password hash set
        return not config.auth_enabled or not config.auth_basic_password_hash
    
    def _is_app_configured(self) -> bool:
        """Check if application credentials are configured."""
        config = self.myblink_app.config
        # App is configured if we have Blink and VoIP.ms credentials
        return bool(
            config.blink_username and 
            config.blink_password and 
            config.voipms_username and 
            config.voipms_password and 
            config.voipms_did
        )
    
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
        
        # First-run setup route - no auth required
        @self.app.route('/setup')
        def setup():
            """Serve first-run setup page."""
            if not self._is_first_run():
                # Already configured, redirect to main page
                return redirect('/')
            response = send_from_directory('web_static', 'setup.html')
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        
        # API endpoint to save initial admin credentials
        @self.app.route('/api/setup/admin', methods=['POST'])
        def setup_admin():
            """Save initial admin credentials (first-run only)."""
            if not self._is_first_run():
                return jsonify({'error': 'Setup already completed'}), 403
            
            try:
                data = request.get_json()
                username = data.get('username', '').strip()
                password = data.get('password', '')
                
                if not username or len(username) < 3:
                    return jsonify({'error': 'Username must be at least 3 characters'}), 400
                
                if not password or len(password) < 8:
                    return jsonify({'error': 'Password must be at least 8 characters'}), 400
                
                # Hash the password
                try:
                    import bcrypt
                    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                except ImportError:
                    return jsonify({'error': 'bcrypt not installed'}), 500
                
                # Update config
                config = self.myblink_app.config
                config.auth_enabled = True
                config.auth_method = "basic"
                config.auth_basic_username = username
                config.auth_basic_password_hash = password_hash
                
                # Save to config file
                self.myblink_app.config_manager.save_config()
                
                # Re-initialize authentication
                self._init_authentication()
                
                # Auto-login the user after setup
                user = User(user_id=username, username=username)
                login_user(user, remember=True)
                session.permanent = True
                session['user_data'] = {
                    'id': username,
                    'username': username
                }
                
                self.logger.info(f"Admin credentials configured for user: {username}")
                
                return jsonify({
                    'success': True,
                    'message': 'Admin credentials saved and logged in successfully.'
                })
                
            except Exception as e:
                self.logger.error(f"Failed to save admin credentials: {e}")
                return jsonify({'error': str(e)}), 500
        
        # Frontend routes
        @self.app.route('/')
        @self._require_auth
        def index():
            """Serve main page."""
            # Check if first run - redirect to setup
            if self._is_first_run():
                return redirect('/setup')
            # Check if app is configured - redirect to configure
            if not self._is_app_configured():
                return redirect('/configure')
            response = send_from_directory('web_static', 'index.html')
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        
        @self.app.route('/static/app.js')
        def app_js():
            """Serve app JavaScript."""
            response = send_from_directory('web_static', 'app.js')
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        
        @self.app.route('/manifest.json')
        def manifest():
            """Serve PWA manifest."""
            response = send_from_directory('web_static', 'manifest.json')
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return response
        
        @self.app.route('/sw.js')
        def service_worker():
            """Serve service worker."""
            response = send_from_directory('web_static', 'sw.js')
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        
        # Configuration setup route
        @self.app.route('/configure')
        @self._require_auth
        def configure():
            """Serve configuration page."""
            # Redirect to setup if admin not configured
            if self._is_first_run():
                return redirect('/setup')
            # If already configured, redirect to main page
            if self._is_app_configured():
                return redirect('/')
            response = send_from_directory('web_static', 'configure.html')
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        
        # Configuration API routes
        @self.app.route('/api/config/current')
        @self._require_auth
        def get_current_config():
            """Get current configuration without passwords."""
            try:
                config = self.myblink_app.config
                return jsonify({
                    'blink_username': config.blink_username,
                    'voipms_username': config.voipms_username,
                    'voipms_did': config.voipms_did
                })
            except Exception as e:
                self.logger.error(f"Error getting current config: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/config/save', methods=['POST'])
        @self._require_auth
        def save_config():
            """Save Blink and VoIP.ms credentials."""
            try:
                data = request.get_json()
                
                # Validate required fields
                required = ['blink_username', 'blink_password', 'voipms_username', 'voipms_password', 'voipms_did']
                for field in required:
                    if not data.get(field):
                        return jsonify({'error': f'Missing required field: {field}'}), 400
                
                # Transform flat structure to nested structure for set_credentials
                creds_dict = {
                    'blink': {
                        'username': data['blink_username'].strip(),
                        'password': data['blink_password']
                    },
                    'voipms': {
                        'username': data['voipms_username'].strip(),
                        'password': data['voipms_password'],
                        'did': data['voipms_did'].strip()
                    }
                }
                
                # Set credentials (this will also initialize services)
                self.myblink_app.set_credentials(creds_dict)
                
                # Trigger async initialization of Blink connection
                if self.myblink_app._event_loop and self.myblink_app.blink_handler:
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            self.myblink_app.blink_handler.initialize(),
                            self.myblink_app._event_loop
                        )
                        # Wait up to 30 seconds for initialization
                        future.result(timeout=30)
                        self.logger.info("Blink initialized successfully")
                    except Exception as init_error:
                        self.logger.error(f"Failed to initialize Blink: {init_error}")
                        return jsonify({
                            'error': f'Credentials saved but Blink initialization failed: {str(init_error)}'
                        }), 500
                
                self.logger.info(f"Configuration saved for Blink user: {data['blink_username']}")
                
                return jsonify({
                    'success': True,
                    'message': 'Configuration saved and Blink initialized successfully'
                })
                
            except Exception as e:
                self.logger.error(f"Failed to save configuration: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/config/test', methods=['POST'])
        @self._require_auth
        def test_config():
            """Test Blink and VoIP.ms credentials."""
            try:
                data = request.get_json()
                
                # For now, just validate the format
                # Full connection testing could be added later
                blink_username = data.get('blink_username', '').strip()
                voipms_username = data.get('voipms_username', '').strip()
                voipms_did = data.get('voipms_did', '').strip()
                
                if not '@' in blink_username:
                    return jsonify({'error': 'Invalid Blink email address'}), 400
                
                if not '@' in voipms_username:
                    return jsonify({'error': 'Invalid VoIP.ms email address'}), 400
                
                if not voipms_did.isdigit() or len(voipms_did) < 10:
                    return jsonify({'error': 'Invalid phone number (must be at least 10 digits)'}), 400
                
                return jsonify({
                    'success': True,
                    'message': 'Credentials format is valid'
                })
                
            except Exception as e:
                self.logger.error(f"Failed to test configuration: {e}")
                return jsonify({'error': str(e)}), 500
        
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
                
                if not self.myblink_app.blink_handler:
                    return jsonify({"error": "Blink handler not initialized"}), 500
                
                # Initialize Blink in event loop
                if self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        self.myblink_app.blink_handler.initialize(),
                        self.myblink_app._event_loop
                    )
                    future.result(timeout=60)
                    
                    # Run initial jobs
                    future = asyncio.run_coroutine_threadsafe(
                        self.myblink_app.blink_handler.run_scheduled_jobs(),
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
                    return jsonify({"configured": False, "syncs": [], "cameras": {}})
                
                # Get actual state from Blink (async operation)
                if self.myblink_app._event_loop and self.myblink_app.blink_handler:
                    future = asyncio.run_coroutine_threadsafe(
                        self._get_current_state_async(),
                        self.myblink_app._event_loop
                    )
                    state = future.result(timeout=30)
                else:
                    state = {"syncs": []}
                
                state["configured"] = True
                return jsonify(state)
            except Exception as e:
                self.logger.error(f"Error getting state: {e}", exc_info=True)
                # Return safe default state even on error
                return jsonify({"configured": False, "syncs": [], "cameras": {}, "error": str(e)})
        
        @self.app.route('/api/config')
        @self._require_auth
        def get_config():
            """Get current configuration."""
            try:
                config = self._get_config()
                return jsonify(config)
            except Exception as e:
                self.logger.error(f"Error getting config: {e}", exc_info=True)
                # Return safe default config
                return jsonify({
                    "schedule_interval_hours": 1,
                    "blink_retry_limit": 3,
                    "voipms_sms_wait": 30,
                    "theme": "dark",
                    "blink_username": "",
                    "voipms_username": "",
                    "voipms_did": ""
                })
        
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
                
                self.logger.info(f"Toggle camera snooze request: {camera_name}, enabled={enabled}")
                
                # Update config first
                self._update_camera_setting(camera_name, 'snooze', enabled)
                
                if enabled:
                    # Apply snooze via Blink API
                    camera = self._find_camera(camera_name)
                    if not camera:
                        self.logger.error(f"Camera {camera_name} not found")
                        return jsonify({"error": f"Camera {camera_name} not found"}), 404
                    
                    if not self.myblink_app._event_loop:
                        self.logger.error("Event loop not available")
                        return jsonify({"error": "Event loop not available"}), 500
                    
                    # Get and validate product_type
                    product_type = getattr(camera, 'product_type', None)
                    camera_type = getattr(camera, 'camera_type', '')
                    
                    # Attempt to determine product_type if None
                    if not product_type:
                        # Try to infer from camera_type or other attributes
                        if 'mini' in camera_type.lower():
                            product_type = 'owl'
                        elif 'doorbell' in camera_type.lower():
                            product_type = 'doorbell'
                        else:
                            # Default to 'owl' for most cameras
                            product_type = 'owl'
                        self.logger.warning(f"Camera {camera_name} had no product_type, using: {product_type}")
                    
                    # Log camera details for debugging
                    self.logger.info(f"Camera found: {camera_name}, product_type={product_type}, camera_type={camera_type}, camera_id={getattr(camera, 'camera_id', 'unknown')}")
                    
                    # Validate product_type is supported
                    supported_types = ["owl", "catalina", "doorbell", "hawk", "lotus", "sedona"]
                    if product_type not in supported_types:
                        error_msg = f"Camera {camera_name} has unsupported product_type: {product_type}"
                        self.logger.error(error_msg)
                        return jsonify({"error": error_msg}), 400
                    
                    # Use 300 seconds (5 minutes) instead of 3600 (1 hour)
                    # Some Blink cameras may not support longer durations
                    snooze_time = 300
                    future = asyncio.run_coroutine_threadsafe(
                        camera.async_snooze(snooze_time),
                        self.myblink_app._event_loop
                    )
                    result = future.result(timeout=30)
                    
                    self.logger.info(f"Snooze API result: {result}")
                    
                    if result:
                        self.logger.info(f"Camera {camera_name} snoozed for {snooze_time}s")
                        # Refresh to get updated state (non-blocking, longer timeout)
                        if self.myblink_app.blink_handler and self.myblink_app.blink_handler.blink:
                            try:
                                future = asyncio.run_coroutine_threadsafe(
                                    self.myblink_app.blink_handler.blink.refresh(force=True),
                                    self.myblink_app._event_loop
                                )
                                # Don't wait for refresh to complete - let it happen async
                                # future.result(timeout=30)
                            except Exception as e:
                                self.logger.warning(f"Refresh after snooze skipped: {e}")
                    else:
                        error_msg = f"Camera {camera_name} snooze returned None - product_type may not be supported"
                        self.logger.warning(error_msg)
                        return jsonify({"error": error_msg}), 400
                else:
                    # De-snooze: disarm and re-arm the sync, then re-snooze other cameras
                    self.logger.info(f"De-snoozing camera {camera_name}")
                    
                    camera = self._find_camera(camera_name)
                    sync_info = self._find_sync_for_camera(camera_name)
                    
                    if not camera or not sync_info:
                        self.logger.error(f"Camera {camera_name} or its sync not found")
                        return jsonify({"error": f"Camera {camera_name} or its sync not found"}), 404
                    
                    if not self.myblink_app._event_loop:
                        self.logger.error("Event loop not available")
                        return jsonify({"error": "Event loop not available"}), 500
                    
                    sync, sync_name = sync_info
                    
                    # Run de-snooze in event loop
                    future = asyncio.run_coroutine_threadsafe(
                        self._desnooze_camera_async(camera_name, camera, sync, sync_name),
                        self.myblink_app._event_loop
                    )
                    success = future.result(timeout=60)
                    
                    if not success:
                        return jsonify({"error": "Failed to de-snooze camera"}), 500
                    
                    # Refresh to get updated state
                    if self.myblink_app.blink_handler and self.myblink_app.blink_handler.blink:
                        try:
                            future = asyncio.run_coroutine_threadsafe(
                                self.myblink_app.blink_handler.blink.refresh(force=True),
                                self.myblink_app._event_loop
                            )
                        except Exception as e:
                            self.logger.warning(f"Refresh after de-snooze skipped: {e}")
                    
                    self.logger.info(f"Camera {camera_name} de-snoozed successfully")
                
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error toggling camera snooze: {e}", exc_info=True)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/camera/<camera_name>/arm', methods=['POST'])
        @self._require_auth
        def toggle_camera_arm(camera_name: str):
            """Toggle arm for a specific camera."""
            try:
                data = request.get_json()
                enabled = data.get('enabled', False)
                
                # Update config first
                self._update_camera_setting(camera_name, 'arm', enabled)
                
                # Apply setting immediately via Blink API
                camera = self._find_camera(camera_name)
                if camera and self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        camera.async_arm(enabled),
                        self.myblink_app._event_loop
                    )
                    result = future.result(timeout=30)
                    self.logger.info(f"Camera {camera_name} {'armed' if enabled else 'disarmed'} - result: {result}")
                    
                    # Update local camera state immediately
                    camera.motion_enabled = enabled
                    
                    # Refresh to get updated state from Blink
                    if self.myblink_app.blink_handler and self.myblink_app.blink_handler.blink:
                        future = asyncio.run_coroutine_threadsafe(
                            self.myblink_app.blink_handler.blink.refresh(force=True),
                            self.myblink_app._event_loop
                        )
                        future.result(timeout=10)
                
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
                
                # Update config first
                self._update_sync_setting(sync_name, 'snooze', enabled)
                
                if enabled:
                    # Apply snooze via Blink API
                    sync = self._find_sync(sync_name)
                    if sync and self.myblink_app._event_loop:
                        snooze_time = 240  # 4 minutes
                        future = asyncio.run_coroutine_threadsafe(
                            sync.async_snooze(snooze_time),
                            self.myblink_app._event_loop
                        )
                        result = future.result(timeout=30)
                        if result:
                            self.logger.info(f"Sync {sync_name} snoozed for {snooze_time}s")
                            # Refresh to get updated state
                            if self.myblink_app.blink_handler and self.myblink_app.blink_handler.blink:
                                future = asyncio.run_coroutine_threadsafe(
                                    self.myblink_app.blink_handler.blink.refresh(force=True),
                                    self.myblink_app._event_loop
                                )
                                future.result(timeout=10)
                        else:
                            self.logger.warning(f"Sync {sync_name} snooze may have failed")
                else:
                    # De-snooze: disarm and re-arm the sync
                    self.logger.info(f"De-snoozing sync {sync_name}")
                    
                    sync = self._find_sync(sync_name)
                    if not sync:
                        self.logger.error(f"Sync {sync_name} not found")
                        return jsonify({"error": f"Sync {sync_name} not found"}), 404
                    
                    if not self.myblink_app._event_loop:
                        self.logger.error("Event loop not available")
                        return jsonify({"error": "Event loop not available"}), 500
                    
                    # Run de-snooze in event loop
                    future = asyncio.run_coroutine_threadsafe(
                        self._desnooze_sync_async(sync, sync_name),
                        self.myblink_app._event_loop
                    )
                    success = future.result(timeout=60)
                    
                    if not success:
                        return jsonify({"error": "Failed to de-snooze sync"}), 500
                    
                    # Refresh to get updated state
                    if self.myblink_app.blink_handler and self.myblink_app.blink_handler.blink:
                        try:
                            future = asyncio.run_coroutine_threadsafe(
                                self.myblink_app.blink_handler.blink.refresh(force=True),
                                self.myblink_app._event_loop
                            )
                            future.result(timeout=10)
                        except Exception as e:
                            self.logger.warning(f"Refresh after de-snooze skipped: {e}")
                    
                    self.logger.info(f"Sync {sync_name} de-snoozed successfully")
                
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
                
                # Update config first
                self._update_sync_setting(sync_name, 'arm', enabled)
                
                # Apply setting immediately via Blink API
                sync = self._find_sync(sync_name)
                if sync and self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        sync.async_arm(enabled),
                        self.myblink_app._event_loop
                    )
                    result = future.result(timeout=30)
                    self.logger.info(f"Sync {sync_name} {'armed' if enabled else 'disarmed'} - result: {result}")
                    
                    # Refresh to get updated state from Blink
                    if self.myblink_app.blink_handler and self.myblink_app.blink_handler.blink:
                        future = asyncio.run_coroutine_threadsafe(
                            self.myblink_app.blink_handler.blink.refresh(force=True),
                            self.myblink_app._event_loop
                        )
                        future.result(timeout=10)
                
                return jsonify({"success": True})
            except Exception as e:
                self.logger.error(f"Error toggling sync arm: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/refresh', methods=['POST'])
        @self._require_auth
        def refresh():
            """Refresh camera list from Blink."""
            try:
                # Check if configured
                if not self.myblink_app.is_configured():
                    return jsonify({"error": "Application not configured"}), 400
                
                # Run async refresh in event loop
                if self.myblink_app.blink_handler and self.myblink_app.blink_handler.blink and self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        self.myblink_app.blink_handler.blink.refresh(force=True),
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
                if not self.myblink_app.blink_handler:
                    return jsonify({"error": "Blink handler not initialized"}), 500
                    
                if self.myblink_app._event_loop:
                    future = asyncio.run_coroutine_threadsafe(
                        self.myblink_app.blink_handler.run_scheduled_jobs(),
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
        """Get current state of all cameras and syncs (sync version - config only)."""
        if not self.myblink_app.blink_handler or not self.myblink_app.blink_handler.blink or not self.myblink_app.config:
            return {"syncs": [], "cameras": {}}
        
        config = self.myblink_app.config
        syncs = []
        
        for sync_name, sync in self.myblink_app.blink_handler.blink.sync.items():
            # Get sync-level settings (frontend expects 'arm', 'snooze')
            sync_data = {
                "name": sync_name,
                "snooze": sync_name in config.snooze_syncs,
                "arm": sync_name in config.arm_syncs,
                "cameras": []
            }
            
            # Get cameras for this sync
            if hasattr(sync, 'cameras'):
                for camera_name, camera in sync.cameras.items():
                    camera_data = {
                        "name": camera_name,
                        "snooze": camera_name in config.snooze_cams,
                        "arm": camera_name in config.arm_cams,
                        "thumbnail": camera_name in config.thumbnail_cams
                    }
                    sync_data["cameras"].append(camera_data)
            
            syncs.append(sync_data)
        
        return {"syncs": syncs}
    
    async def _get_current_state_async(self) -> Dict[str, Any]:
        """Get current state of all cameras and syncs from Blink API (async version)."""
        if not self.myblink_app.blink_handler or not self.myblink_app.blink_handler.blink:
            return {"syncs": []}
        
        syncs = []
        
        for sync_name, sync in self.myblink_app.blink_handler.blink.sync.items():
            # Get actual sync state from Blink
            sync_armed = sync.arm if hasattr(sync, 'arm') else None
            
            # Get snoozed status - avoid hasattr which can trigger async property
            sync_snoozed = False
            try:
                sync_snoozed = await sync.snoozed
            except AttributeError:
                pass
            except Exception as e:
                self.logger.debug(f"Could not get snooze status for sync {sync_name}: {e}")
            
            sync_data = {
                "name": sync_name,
                # Use actual Blink state for display (frontend expects 'arm', 'snooze')
                "arm": sync_armed if sync_armed is not None else False,
                "snooze": sync_snoozed,
                "cameras": []
            }
            
            # Get cameras for this sync
            if hasattr(sync, 'cameras'):
                for camera_name, camera in sync.cameras.items():
                    # Get actual camera state from Blink
                    camera_armed = camera.motion_enabled if hasattr(camera, 'motion_enabled') and camera.motion_enabled is not None else False
                    
                    # Get snoozed status - avoid hasattr which can trigger async property
                    camera_snoozed = False
                    try:
                        camera_snoozed = await camera.snoozed
                    except AttributeError:
                        pass
                    except Exception as e:
                        self.logger.debug(f"Could not get snooze status for {camera_name}: {e}")
                    
                    camera_data = {
                        "name": camera_name,
                        # Use actual Blink state for display (frontend expects 'arm', 'snooze', 'thumbnail')
                        "arm": camera_armed,
                        "snooze": camera_snoozed,
                        # Thumbnail is config-based (not a Blink state)
                        "thumbnail": camera_name in self.myblink_app.config.thumbnail_cams if self.myblink_app.config else False
                    }
                    sync_data["cameras"].append(camera_data)
            
            syncs.append(sync_data)
        
        return {"syncs": syncs}
    
    async def _desnooze_camera_async(self, camera_name: str, camera: Any, sync: Any, sync_name: str) -> bool:
        """
        De-snooze a camera by disarming and re-arming the sync, then re-snoozing other cameras.
        
        Args:
            camera_name: Name of the camera to de-snooze
            camera: Camera object
            sync: Sync module object
            sync_name: Name of the sync module
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"De-snoozing camera {camera_name} on sync {sync_name}")
            
            # Get list of all snoozed cameras on this sync (excluding the one we're de-snoozing)
            snoozed_cameras = []
            if hasattr(sync, 'cameras'):
                for cam_name, cam in sync.cameras.items():
                    if cam_name != camera_name:
                        try:
                            is_snoozed = await cam.snoozed
                            if is_snoozed:
                                snoozed_cameras.append((cam_name, cam))
                                self.logger.info(f"Found snoozed camera: {cam_name}")
                        except Exception as e:
                            self.logger.debug(f"Could not check snooze status for {cam_name}: {e}")
            
            # Step 1: Disarm the sync module
            self.logger.info(f"Disarming sync {sync_name}")
            await sync.async_arm(False)
            
            # Step 2: Re-arm the sync module
            self.logger.info(f"Re-arming sync {sync_name}")
            await sync.async_arm(True)
            
            # Step 3: Re-snooze all other cameras that were snoozed
            snooze_time = 300  # 5 minutes
            for cam_name, cam in snoozed_cameras:
                try:
                    self.logger.info(f"Re-snoozing camera {cam_name}")
                    await cam.async_snooze(snooze_time)
                except Exception as e:
                    self.logger.warning(f"Failed to re-snooze camera {cam_name}: {e}")
            
            self.logger.info(f"Successfully de-snoozed camera {camera_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error de-snoozing camera {camera_name}: {e}", exc_info=True)
            return False
    
    async def _desnooze_sync_async(self, sync: Any, sync_name: str) -> bool:
        """
        De-snooze a sync module by disarming and re-arming it.
        
        Args:
            sync: Sync module object
            sync_name: Name of the sync module
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"De-snoozing sync {sync_name}")
            
            # Step 1: Disarm the sync module
            self.logger.info(f"Disarming sync {sync_name}")
            await sync.async_arm(False)
            
            # Step 2: Re-arm the sync module
            self.logger.info(f"Re-arming sync {sync_name}")
            await sync.async_arm(True)
            
            self.logger.info(f"Successfully de-snoozed sync {sync_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error de-snoozing sync {sync_name}: {e}", exc_info=True)
            return False
    
    def _get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        if not self.myblink_app.config:
            return {
                "schedule_interval_hours": 1,
                "blink_retry_limit": 3,
                "voipms_sms_wait": 30,
                "theme": "dark",
                "blink_username": "",
                "voipms_username": "",
                "voipms_did": ""
            }
        
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
        if not self.myblink_app.config or not self.myblink_app.blink_handler or not self.myblink_app.blink_handler.blink:
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
            sync = self.myblink_app.blink_handler.blink.sync.get(sync_name)
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
            sync = self.myblink_app.blink_handler.blink.sync.get(sync_name)
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
        if not self.myblink_app.blink_handler or not self.myblink_app.blink_handler.blink:
            return None
        
        for sync_name, sync in self.myblink_app.blink_handler.blink.sync.items():
            if hasattr(sync, 'cameras') and camera_name in sync.cameras:
                return sync.cameras[camera_name]
        
        return None
    
    def _find_sync_for_camera(self, camera_name: str) -> Optional[tuple[Any, str]]:
        """
        Find the sync module that a camera belongs to.
        
        Args:
            camera_name: Name of the camera
            
        Returns:
            Tuple of (sync object, sync name) if found, None otherwise
        """
        if not self.myblink_app.blink_handler or not self.myblink_app.blink_handler.blink:
            return None
        
        for sync_name, sync in self.myblink_app.blink_handler.blink.sync.items():
            if hasattr(sync, 'cameras') and camera_name in sync.cameras:
                return (sync, sync_name)
        
        return None

    
    def _find_sync(self, sync_name: str) -> Optional[Any]:
        """
        Find a sync module by name.
        
        Args:
            sync_name: Name of the sync module to find
            
        Returns:
            Sync module object if found, None otherwise
        """
        if not self.myblink_app.blink_handler or not self.myblink_app.blink_handler.blink:
            return None
        
        return self.myblink_app.blink_handler.blink.sync.get(sync_name)
    
    def _optimize_sync_settings(self) -> None:
        """
        Optimize camera settings to sync-level when all cameras have same setting.
        
        If all cameras in a sync have the same setting, move the setting to the
        sync level to reduce API calls.
        """
        if not self.myblink_app.config or not self.myblink_app.blink_handler or not self.myblink_app.blink_handler.blink:
            return
        
        config = self.myblink_app.config
        
        for sync_name, sync in self.myblink_app.blink_handler.blink.sync.items():
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
