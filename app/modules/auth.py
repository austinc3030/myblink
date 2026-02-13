"""
Authentication module for MyBlink web interface.

Supports multiple authentication methods:
- No authentication (disabled mode)
- Basic authentication (username/password)
- OIDC (OpenID Connect) authentication

Uses Flask-Login for session management and bcrypt for password hashing.
"""

import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlencode, urlparse

from flask import Flask, redirect, request, session, url_for, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    bcrypt = None
    BCRYPT_AVAILABLE = False

try:
    from authlib.integrations.flask_client import OAuth
    AUTHLIB_AVAILABLE = True
except ImportError:
    OAuth = None
    AUTHLIB_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class BasicAuthConfig:
    """Configuration for basic username/password authentication."""
    
    username: str
    password_hash: str  # bcrypt hash of password
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BasicAuthConfig':
        """Create from dictionary with plain password."""
        if not BCRYPT_AVAILABLE:
            raise ImportError("bcrypt is required for basic auth. Install with: pip install bcrypt")
        
        password = data.get('password', '')
        if not password:
            raise ValueError("Password is required for basic auth")
        
        # If password is already a hash, use it directly
        if password.startswith('$2b$') or password.startswith('$2a$'):
            password_hash = password
        else:
            # Hash the password
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        return cls(
            username=data.get('username', 'admin'),
            password_hash=password_hash
        )
    
    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        if not BCRYPT_AVAILABLE:
            return False
        try:
            return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False


@dataclass
class OIDCConfig:
    """Configuration for OIDC authentication."""
    
    client_id: str
    client_secret: str
    server_metadata_url: str  # OpenID Connect discovery URL
    redirect_uri: Optional[str] = None  # Will be auto-generated if not provided
    
    # Optional: restrict to specific users/groups/domains
    allowed_emails: Optional[list] = None
    allowed_domains: Optional[list] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OIDCConfig':
        """Create from dictionary."""
        return cls(
            client_id=data.get('client_id', ''),
            client_secret=data.get('client_secret', ''),
            server_metadata_url=data.get('server_metadata_url', ''),
            redirect_uri=data.get('redirect_uri'),
            allowed_emails=data.get('allowed_emails'),
            allowed_domains=data.get('allowed_domains')
        )
    
    def is_user_allowed(self, email: str) -> bool:
        """Check if user email is allowed."""
        if not email:
            return False
        
        # If no restrictions, allow all
        if not self.allowed_emails and not self.allowed_domains:
            return True
        
        # Check specific emails
        if self.allowed_emails and email.lower() in [e.lower() for e in self.allowed_emails]:
            return True
        
        # Check domains
        if self.allowed_domains:
            email_domain = email.split('@')[-1].lower()
            if email_domain in [d.lower() for d in self.allowed_domains]:
                return True
        
        return False


@dataclass
class AuthConfig:
    """Authentication configuration."""
    
    enabled: bool = False
    method: str = "basic"  # "basic" or "oidc"
    session_timeout_minutes: int = 480  # 8 hours
    
    # Basic auth config
    basic: Optional[BasicAuthConfig] = None
    
    # OIDC config
    oidc: Optional[OIDCConfig] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuthConfig':
        """Create from dictionary."""
        if not data:
            return cls(enabled=False)
        
        enabled = data.get('enabled', False)
        method = data.get('method', 'basic')
        
        basic_config = None
        oidc_config = None
        
        if enabled:
            if method == 'basic' and 'basic' in data:
                basic_config = BasicAuthConfig.from_dict(data['basic'])
            elif method == 'oidc' and 'oidc' in data:
                if not AUTHLIB_AVAILABLE:
                    raise ImportError(
                        "authlib is required for OIDC auth. "
                        "Install with: pip install authlib"
                    )
                oidc_config = OIDCConfig.from_dict(data['oidc'])
        
        return cls(
            enabled=enabled,
            method=method,
            session_timeout_minutes=data.get('session_timeout_minutes', 480),
            basic=basic_config,
            oidc=oidc_config
        )


class User(UserMixin):
    """User class for Flask-Login."""
    
    def __init__(self, user_id: str, username: str, email: Optional[str] = None):
        """
        Initialize user.
        
        Args:
            user_id: Unique user identifier
            username: Username
            email: Email address (for OIDC)
        """
        self.id = user_id
        self.username = username
        self.email = email
        self.authenticated_at = datetime.utcnow()
    
    def get_id(self):
        """Return user ID as string."""
        return str(self.id)


class AuthManager:
    """
    Authentication manager for MyBlink web interface.
    
    Handles both basic auth and OIDC authentication based on configuration.
    """
    
    def __init__(self, app: Flask, config: AuthConfig):
        """
        Initialize authentication manager.
        
        Args:
            app: Flask application instance
            config: Authentication configuration
        """
        self.app = app
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Set secret key for sessions
        if not app.secret_key:
            app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
        
        # Initialize Flask-Login
        self.login_manager = LoginManager()
        self.login_manager.init_app(app)
        self.login_manager.login_view = 'login'
        self.login_manager.session_protection = 'strong'
        
        # Set session lifetime
        app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
            minutes=config.session_timeout_minutes
        )
        
        # User loader
        @self.login_manager.user_loader
        def load_user(user_id):
            """Load user from session."""
            # Get user data from session
            user_data = session.get('user_data')
            if not user_data or user_data.get('id') != user_id:
                return None
            
            return User(
                user_id=user_data['id'],
                username=user_data['username'],
                email=user_data.get('email')
            )
        
        # Initialize OIDC if configured
        self.oauth = None
        self.oidc_client = None
        if config.enabled and config.method == 'oidc' and config.oidc:
            self._init_oidc()
        
        # Add auth routes
        self._add_routes()
    
    def _init_oidc(self):
        """Initialize OIDC provider."""
        if not AUTHLIB_AVAILABLE:
            self.logger.error("authlib not available - OIDC disabled")
            return
        
        if not self.config.oidc:
            return
        
        try:
            # Initialize OAuth
            self.oauth = OAuth(self.app)
            
            # Generate redirect URI if not provided
            redirect_uri = self.config.oidc.redirect_uri
            if not redirect_uri:
                # Will be set dynamically per request
                redirect_uri = None
            
            # Register OIDC client
            self.oidc_client = self.oauth.register(
                name='oidc',
                client_id=self.config.oidc.client_id,
                client_secret=self.config.oidc.client_secret,
                server_metadata_url=self.config.oidc.server_metadata_url,
                client_kwargs={
                    'scope': 'openid email profile'
                }
            )
            
            self.logger.info("OIDC authentication initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize OIDC: {e}")
            self.oidc_client = None
    
    def _add_routes(self):
        """Add authentication routes to Flask app."""
        
        @self.app.route('/auth/login', methods=['GET', 'POST'])
        def login():
            """Login page and handler."""
            # If auth is disabled, redirect to home
            if not self.config.enabled:
                return redirect('/')
            
            # If already logged in, redirect to home
            if current_user.is_authenticated:
                return redirect('/')
            
            # OIDC login
            if self.config.method == 'oidc':
                if request.method == 'POST' or request.args.get('auto') == '1':
                    # Generate redirect URI dynamically
                    redirect_uri = url_for('oidc_callback', _external=True)
                    return self.oidc_client.authorize_redirect(redirect_uri)
                
                # Show OIDC login page
                return '''
                <!DOCTYPE html>
                <html data-theme="dark">
                <head>
                    <title>Login - MyBlink</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                            background: #18181b;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            min-height: 100vh;
                            margin: 0;
                        }
                        .login-box {
                            background: #27272a;
                            padding: 2rem;
                            border-radius: 8px;
                            border: 1px solid #3f3f46;
                            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                            text-align: center;
                            max-width: 400px;
                            width: 90%;
                        }
                        h1 { margin-top: 0; color: #fafafa; }
                        p { color: #a1a1aa; }
                        .btn {
                            background: #71717a;
                            color: white;
                            border: none;
                            padding: 12px 24px;
                            border-radius: 4px;
                            cursor: pointer;
                            font-size: 16px;
                            width: 100%;
                            margin-top: 1rem;
                        }
                        .btn:hover { background: #52525b; }
                    </style>
                </head>
                <body>
                    <div class="login-box">
                        <h1>🔒 MyBlink Login</h1>
                        <p>Please sign in to access the camera management interface.</p>
                        <form method="POST">
                            <button type="submit" class="btn">Sign in with OIDC</button>
                        </form>
                    </div>
                </body>
                </html>
                '''
            
            # Basic auth login
            if request.method == 'POST':
                data = request.get_json() if request.is_json else request.form
                username = data.get('username', '')
                password = data.get('password', '')
                
                if self._verify_basic_auth(username, password):
                    # Create user and login
                    user = User(
                        user_id=username,
                        username=username
                    )
                    login_user(user, remember=True)
                    
                    # Store user data in session
                    session.permanent = True
                    session['user_data'] = {
                        'id': username,
                        'username': username
                    }
                    
                    self.logger.info(f"User {username} logged in successfully")
                    
                    if request.is_json:
                        return jsonify({"success": True, "redirect": "/"})
                    return redirect('/')
                else:
                    self.logger.warning(f"Failed login attempt for username: {username}")
                    if request.is_json:
                        return jsonify({"error": "Invalid username or password"}), 401
                    error = "Invalid username or password"
            else:
                error = None
            
            # Show basic auth login page
            return f'''
            <!DOCTYPE html>
            <html data-theme="dark">
            <head>
                <title>Login - MyBlink</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        background: #18181b;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                    }}
                    .login-box {{
                        background: #27272a;
                        padding: 2rem;
                        border-radius: 8px;
                        border: 1px solid #3f3f46;
                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                        max-width: 400px;
                        width: 90%;
                    }}
                    h1 {{ margin-top: 0; color: #fafafa; }}
                    .form-group {{
                        margin-bottom: 1rem;
                        text-align: left;
                    }}
                    label {{
                        display: block;
                        margin-bottom: 0.5rem;
                        color: #a1a1aa;
                        font-weight: 500;
                    }}
                    input {{
                        width: 100%;
                        padding: 10px;
                        border: 1px solid #3f3f46;
                        background: #18181b;
                        color: #fafafa;
                        border-radius: 4px;
                        font-size: 14px;
                        box-sizing: border-box;
                    }}
                    input:focus {{
                        outline: none;
                        border-color: #71717a;
                    }}
                    .btn {{
                        background: #71717a;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 16px;
                        width: 100%;
                        margin-top: 1rem;
                    }}
                    .btn:hover {{ background: #52525b; }}
                    .error {{
                        background: #7f1d1d;
                        color: #fca5a5;
                        padding: 10px;
                        border-radius: 4px;
                        margin-bottom: 1rem;
                    }}
                </style>
            </head>
            <body>
                <div class="login-box">
                    <h1>🔒 MyBlink Login</h1>
                    {"<div class='error'>" + str(error) + "</div>" if error else ""}
                    <form id="loginForm" method="POST">
                        <div class="form-group">
                            <label for="username">Username</label>
                            <input type="text" id="username" name="username" required autofocus>
                        </div>
                        <div class="form-group">
                            <label for="password">Password</label>
                            <input type="password" id="password" name="password" required>
                        </div>
                        <button type="submit" class="btn">Login</button>
                    </form>
                </div>
                <script>
                    document.getElementById('loginForm').addEventListener('submit', async (e) => {{
                        e.preventDefault();
                        const username = document.getElementById('username').value;
                        const password = document.getElementById('password').value;
                        
                        try {{
                            const response = await fetch('/auth/login', {{
                                method: 'POST',
                                headers: {{ 'Content-Type': 'application/json' }},
                                body: JSON.stringify({{ username, password }})
                            }});
                            
                            const data = await response.json();
                            if (data.success) {{
                                window.location.href = data.redirect || '/';
                            }} else {{
                                alert(data.error || 'Login failed');
                            }}
                        }} catch (err) {{
                            alert('Login failed: ' + err.message);
                        }}
                    }});
                </script>
            </body>
            </html>
            '''
        
        @self.app.route('/auth/callback')
        def oidc_callback():
            """OIDC callback handler."""
            if not self.config.enabled or self.config.method != 'oidc':
                return redirect('/')
            
            try:
                # Get token
                token = self.oidc_client.authorize_access_token()
                
                # Parse user info
                user_info = token.get('userinfo')
                if not user_info:
                    # Try to get userinfo separately
                    user_info = self.oidc_client.userinfo()
                
                email = user_info.get('email', '')
                name = user_info.get('name') or user_info.get('preferred_username') or email
                user_id = user_info.get('sub', email)
                
                # Check if user is allowed
                if self.config.oidc and not self.config.oidc.is_user_allowed(email):
                    self.logger.warning(f"User {email} not allowed to access")
                    return "Access denied: Your email is not authorized", 403
                
                # Create user and login
                user = User(
                    user_id=user_id,
                    username=name,
                    email=email
                )
                login_user(user, remember=True)
                
                # Store user data in session
                session.permanent = True
                session['user_data'] = {
                    'id': user_id,
                    'username': name,
                    'email': email
                }
                
                self.logger.info(f"User {email} logged in successfully via OIDC")
                
                return redirect('/')
                
            except Exception as e:
                self.logger.error(f"OIDC callback error: {e}")
                return f"Authentication failed: {str(e)}", 500
        
        @self.app.route('/auth/logout', methods=['POST', 'GET'])
        def logout():
            """Logout handler."""
            if current_user.is_authenticated:
                username = current_user.username
                logout_user()
                session.clear()
                self.logger.info(f"User {username} logged out")
            
            if request.is_json:
                return jsonify({"success": True})
            return redirect('/auth/login')
        
        @self.app.route('/auth/status')
        def auth_status():
            """Get authentication status."""
            return jsonify({
                "enabled": self.config.enabled,
                "authenticated": current_user.is_authenticated,
                "username": current_user.username if current_user.is_authenticated else None,
                "method": self.config.method if self.config.enabled else None
            })
    
    def _verify_basic_auth(self, username: str, password: str) -> bool:
        """Verify basic authentication credentials."""
        if not self.config.basic:
            return False
        
        return (
            username == self.config.basic.username and
            self.config.basic.verify_password(password)
        )
    
    def require_auth(self, f: Callable) -> Callable:
        """
        Decorator to require authentication for a route.
        
        If auth is disabled, allows access. If enabled, requires login.
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # If auth is disabled, allow access
            if not self.config.enabled:
                return f(*args, **kwargs)
            
            # If authenticated, allow access
            if current_user.is_authenticated:
                return f(*args, **kwargs)
            
            # Not authenticated - return 401
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({"error": "Authentication required"}), 401
            
            # Redirect to login
            return redirect(url_for('login'))
        
        return decorated_function
    
    def get_current_username(self) -> Optional[str]:
        """Get current authenticated username, or None if auth disabled."""
        if not self.config.enabled:
            return None
        
        if current_user.is_authenticated:
            return current_user.username
        
        return None
