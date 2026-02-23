# MyBlink 🎥

**Advanced Blink Camera Management Platform**

A comprehensive, web-based management system for Blink security cameras with automated 2FA, scheduled operations, and complete camera control through an intuitive PWA interface.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## 📑 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Web Interface & Camera Control](#-web-interface--camera-control)
- [Authentication](#-authentication)
- [Credential Configuration](#-credential-configuration)
- [Configuration](#-configuration)
- [API Reference](#-api-reference)
- [Docker Deployment](#-docker-deployment)
- [Project Structure](#-project-structure)
- [Camera Features & Capabilities](#-camera-features--capabilities)
- [Troubleshooting](#troubleshooting)
- [Additional Documentation](#-additional-documentation)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Features

### 🎯 Core Capabilities
- 🔒 **Automatic 2FA Authentication**: Seamless VoIP.ms SMS integration for Blink 2FA codes
- 🔐 **Multi-Auth Support**: Optional basic authentication or enterprise OIDC/SSO (Google, GitHub, Okta, etc.)
- 📸 **Complete Camera Control**: Full access to every Blink camera feature
- 🔄 **Advanced Scheduling System**: Create flexible automated rules with interval-based execution, time windows, day restrictions, and auto-disable timers
- 💪 **Resilient & Self-Healing**: Auto-retry with intelligent error recovery and reinitialization
- 🏥 **Advanced Health Monitoring**: Production-ready Docker healthcheck with active status validation

### 🌐 Modern Web Interface (PWA)
- 📱 **Progressive Web App**: Install on any device for native-app experience
- 🖼️ **Camera Dashboard**: Visual overview of all cameras with real-time status
- 🎛️ **Individual Camera Controls**:
  - Toggle snooze (notification silencing)
  - Arm/disarm motion detection
  - Auto-thumbnail updates
  - Night vision mode (On/Off/Auto)
  - 📸 One-click photo capture
  - 🎥 Instant video recording
  - ℹ️ Detailed info modal with complete camera data
- 📅 **Schedule Management**:
  - Intuitive schedule creation interface
  - Run actions every X hours/minutes
  - Execute at specific minute of each hour
  - Time window restrictions (e.g., only 9 PM - 6 AM)
  - Day-of-week filtering
  - Auto-disable after duration
  - Pause/resume schedules
  - Real-time next-run display
- 📹 **Media Management**:
  - View and download cached thumbnails
  - Capture new photos on-demand
  - Download latest video clips
  - Browse and download recent clips with timestamps
- 🎨 **Professional UI**:
  - Responsive design (mobile/tablet/desktop)
  - Dark/light theme auto-switching
  - Intuitive card-based layout
  - Real-time status updates
  - Toast notifications for all actions

### ⚙️ Advanced Features
- 🔧 **Zero-Config Startup**: Complete setup wizard on first run
- 🎯 **Smart Configuration**: Auto-optimization of camera-to-sync settings
- 📊 **Comprehensive API**: RESTful endpoints for all operations
- 🐳 **Docker-First**: Production-ready containerization with health monitoring
- 🔄 **Auto-Discovery**: Detects new cameras automatically
- 💾 **Persistent Storage**: Configuration survives container restarts
- 🌍 **Multi-Instance**: Run multiple deployments with isolated configs

## 🚀 Quick Start

### Using Docker (Recommended)

1. **Clone the repository**:
   ```bash
   git clone --recurse-submodules https://github.com/austinc3030/myblink.git
   cd myblink
   ```

2. **Start the container**:
   ```bash
   docker-compose up -d
   ```

3. **Configure via web interface**:
   - Open http://localhost:8080 in your browser
   - Enter your Blink credentials (email and password)
   - Enter your VoIP.ms API credentials (username, password, and DID)
   - Click "Save & Start"

That's it! The system will automatically:
- Save your credentials securely
- Initialize the Blink connection with 2FA
- Start managing your cameras
- Run scheduled jobs every hour

📱 **Install as PWA**: On mobile, use "Add to Home Screen" for a native app experience!

## 🎮 Web Interface & Camera Control

MyBlink provides a feature-rich web interface with complete control over all Blink camera functions. Everything is accessible through an intuitive, responsive design that works on any device.

### 📸 Camera Cards - Quick Access Controls

Each camera displays as a card with instant access to:

#### **Status Toggles**
- **Snooze** - Temporarily disable motion notifications
- **Arm** - Enable/disable motion detection and recording
- **Thumbnail** - Enable automatic thumbnail updates

#### **Night Vision Control**
- Dropdown selector with three modes:
  - **Off**: IR illuminator disabled
  - **On**: IR illuminator always on
  - **Auto**: Automatic based on lighting conditions

#### **Quick Action Buttons**
- **📸 Capture**: Take a new photo instantly (auto-downloads)
- **🎥 Record**: Start video recording (saves to recent clips)

#### **ℹ️ Info Button**: Opens detailed camera information modal

### 🔍 Camera Information Modal

Click the info (ℹ️) button on any camera to view comprehensive details:

#### **📸 Camera Details**
- Camera ID and serial number
- Product type and firmware version
- Network ID and sync module assignment

#### **📊 Status Information**
- **Motion**: Enabled status and detection state
- **Battery**: Level percentage, state (ok/replace), and voltage
- **Temperature**: Current reading in °F and °C
- **WiFi**: Signal strength
- **Sync Strength**: Connection quality to sync module
- **Last Record**: Timestamp of most recent motion event

#### **⚙️ Settings Controls**
- **Night Vision**: Change mode directly from info modal
- Settings automatically sync with camera card controls

#### **📷 Media Management**
- **Cached Thumbnail**: Download last cached image (no new capture)
- **New Thumbnail**: Capture fresh photo and download
- **Latest Video Clip**: Download most recent video
- **Recent Clips**: View list with:
  - Full timestamps (e.g., "2/12/2026, 3:45:23 PM")
  - Relative time ("5 minutes ago", "2 hours ago")
  - Individual download buttons for each clip

### 🔄 Sync Module Controls

Control all cameras in a sync module at once:
- **Snooze All**: Silence all cameras simultaneously
- **Arm All**: Enable motion detection for entire module
- Individual cameras can override sync-level settings

### 🎯 Smart Features

- **Auto-Loading**: Night vision status loads automatically for each camera
- **Real-Time Updates**: Changes reflect immediately in the interface
- **Error Handling**: Clear success/error messages for every action
- **Loading States**: Visual feedback during operations ("⏳ Capturing...", "⏳ Recording...")
- **Auto-Downloads**: Media files download with descriptive names automatically
- **Theme Support**: Seamless dark/light mode switching

### 📱 Mobile Experience

- **Responsive Design**: Optimized for phones, tablets, and desktops
- **Touch-Friendly**: Large tap targets and swipe gestures
- **PWA Installation**: Add to home screen for offline access
- **Fast & Lightweight**: Minimal data usage, instant response

## 🔐 Authentication

MyBlink now supports optional authentication to protect your web interface and API:

### Authentication Options

- **No Authentication** (default): Open access, no login required
- **Basic Authentication**: Simple username/password protection
- **OIDC/SSO**: Enterprise single sign-on (Google, GitHub, Okta, etc.)

### Quick Setup

**Enable Basic Auth:**

```yaml
# config.yaml
auth_enabled: true
auth_method: basic
auth_basic_username: admin
auth_basic_password_hash: $2b$12$...  # bcrypt hash
```

Generate password hash:
```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'YourPassword', bcrypt.gensalt()).decode())"
```

**Enable OIDC/SSO:**

```yaml
# config.yaml
auth_enabled: true
auth_method: oidc
auth_oidc_client_id: your-client-id
auth_oidc_client_secret: your-secret
auth_oidc_server_metadata_url: https://accounts.google.com/.well-known/openid-configuration
auth_oidc_allowed_domains:
  - yourdomain.com
```

📖 **Full Authentication Guide**: See [AUTH_GUIDE.md](AUTH_GUIDE.md) and [AUTH_QUICKSTART.md](AUTH_QUICKSTART.md) for detailed configuration instructions.

## 🔑 Credential Configuration

MyBlink supports **three ways** to provide credentials, checked in this priority order:

### 1. Environment Variables (Highest Priority)

Perfect for containerized deployments and CI/CD pipelines. **Environment variables are automatically saved to the config file** so they can be edited via the web UI later.

```bash
docker run -d \
  -e BLINK_USERNAME="your-email@example.com" \
  -e BLINK_PASSWORD="your-blink-password" \
  -e VOIPMS_USERNAME="your-voipms-email@example.com" \
  -e VOIPMS_PASSWORD="your-voipms-api-password" \
  -e VOIPMS_DID="5551234567" \
  -p 8080:8080 \
  myblink
```

Or in `docker-compose.yml`:

```yaml
services:
  myblink:
    environment:
      - BLINK_USERNAME=your-email@example.com
      - BLINK_PASSWORD=your-blink-password
      - VOIPMS_USERNAME=your-voipms-email@example.com
      - VOIPMS_PASSWORD=your-voipms-api-password
      - VOIPMS_DID=5551234567
```

### 2. Config File

Credentials are stored in the main config file (`config.yaml`). You can manually create this or let the web UI generate it:

```yaml
# ...other config settings...
blink_username: "your-email@example.com"
blink_password: "your-blink-password"
voipms_username: "your-voipms-email@example.com"
voipms_password: "your-voipms-api-password"
voipms_did: "5551234567"
```

### 3. Web Interface (Fallback)

If no credentials are found, the web UI automatically shows a setup wizard:
1. Open http://localhost:8080
2. Enter your credentials in the form
3. Click "Save & Start"

Credentials are saved to `config.yaml` and can be edited anytime via the web UI.

**Note**: Once configured, you can change credentials anytime through the web interface at http://localhost:8080

### Local Development

1. **Clone and setup**:
   ```bash
   git clone --recurse-submodules https://github.com/austinc3030/myblink.git
   cd myblink/app
   pip install -r requirements.txt
   ```

2. **Start the application**:
   ```bash
   python myblink.py
   ```

3. **Configure**: Open http://localhost:8080 and complete the setup wizard

**Note**: No config files needed! Everything is configured through the web interface or environment variables.

## 📖 Configuration

### System Configuration (Optional)

The application works out-of-the-box with sensible defaults. All configuration is done through the web interface.

For advanced users who need to customize low-level system settings, you can create a `config.yaml` file in the Docker volume (`/data/config.yaml`) or local directory with these options:

```yaml
# Debug and monitoring
debug_mode: false
health_file: /tmp/myblink_health.json
health_check_interval: 30
max_consecutive_errors: 3

# VoIP.ms SMS filtering (not configurable via web UI)
voipms_message_keyword: "Blink"
voipms_retry_limit: 10
voipms_retry_delay: 3

# Internal timing
status_log_interval: 60
main_loop_sleep: 1
error_recovery_sleep: 5
```

**Common settings** (retry limits, intervals, theme) are configurable via the web interface and automatically saved to the config file.

### Additional Environment Variables

Configure the application paths and web server:

```bash
WEB_PORT=8080                    # Port for web interface (default: 8080)
WEB_HOST=0.0.0.0                 # Host to bind to (default: 0.0.0.0)
MYBLINK_CONFIG=/data/config.yaml # Config file path (default: /app/config.yaml)
```

**Credential Environment Variables** (see Credential Configuration section above):
```bash
BLINK_USERNAME      # Blink account email
BLINK_PASSWORD      # Blink account password
VOIPMS_USERNAME     # VoIP.ms API username
VOIPMS_PASSWORD     # VoIP.ms API password
VOIPMS_DID          # VoIP.ms DID (phone number)
```

### Camera Operations (Web UI)

All camera and sync module settings are managed exclusively through the web interface:

- **Snooze**: Enable/disable motion detection
- **Arm**: Enable/disable camera arming
- **Thumbnails**: Enable/disable automatic thumbnail updates

Changes are saved automatically and take effect on the next scheduled run.

## � API Reference

MyBlink exposes a comprehensive RESTful API for programmatic access to all camera and system functions. All endpoints require authentication if auth is enabled.

### 🔒 Authentication Endpoints (when enabled)

```
POST   /auth/login              # Basic auth: submit credentials
GET    /auth/callback           # OIDC: OAuth callback endpoint
GET    /auth/logout             # End session
GET    /auth/status             # Check authentication status
```

### 📊 System Endpoints

```
GET    /api/state               # Current state of all cameras and syncs
GET    /api/config              # Application configuration
POST   /api/config              # Update configuration
POST   /api/refresh             # Force refresh from Blink API
POST   /api/run-jobs            # Manually trigger scheduled jobs
GET    /api/logs                # Retrieve application logs
POST   /api/logs/clear          # Clear log history
GET    /api/setup/status        # Check if credentials configured
POST   /api/setup/credentials   # Set/update Blink and VoIP.ms credentials
```

### 📸 Camera Control Endpoints

#### Camera Settings
```
POST   /api/camera/<name>/snooze          # Enable/disable snooze
POST   /api/camera/<name>/arm             # Enable/disable arming
POST   /api/camera/<name>/thumbnail       # Enable/disable thumbnails
GET    /api/camera/<name>/night_vision    # Get night vision mode
POST   /api/camera/<name>/night_vision    # Set night vision (on/off/auto)
```

#### Camera Actions
```
POST   /api/camera/<name>/record          # Start video recording
GET    /api/camera/<name>/info            # Get detailed camera information
```

#### Media Operations
```
GET    /api/camera/<name>/media/thumbnail       # Download cached thumbnail
POST   /api/camera/<name>/media/thumbnail/new   # Capture new thumbnail
GET    /api/camera/<name>/media/clip            # Download latest video clip
GET    /api/camera/<name>/media/clips           # List recent clips
POST   /api/camera/<name>/media/clip/download   # Download specific clip by URL
```

### 🔄 Sync Module Endpoints

```
POST   /api/sync/<name>/snooze            # Enable/disable snooze for all cameras
POST   /api/sync/<name>/arm               # Enable/disable arming for all cameras
```

### 📝 API Request Examples

#### Get Current State
```bash
curl http://localhost:8080/api/state
```

**Response:**
```json
{
  "syncs": [
    {
      "name": "Sync Module",
      "snooze_enabled": false,
      "arm_enabled": true,
      "cameras": [
        {
          "name": "Front Door",
          "snooze_enabled": false,
          "arm_enabled": true,
          "thumbnail_enabled": true
        }
      ]
    }
  ]
}
```

#### Get Camera Details
```bash
curl http://localhost:8080/api/camera/Front%20Door/info
```

**Response:**
```json
{
  "name": "Front Door",
  "camera_id": 123456,
  "serial": "ABCD1234",
  "type": "catalina",
  "version": "9.62",
  "battery_level": 3,
  "battery": "ok",
  "battery_voltage": 165,
  "temperature": 72,
  "temperature_c": 22.2,
  "wifi_strength": 5,
  "motion_enabled": true,
  "motion_detected": false,
  "network_id": 789012,
  "sync_module": "Sync Module",
  "recent_clips": [...]
}
```

#### Set Night Vision
```bash
curl -X POST http://localhost:8080/api/camera/Front%20Door/night_vision \
  -H "Content-Type: application/json" \
  -d '{"mode": "auto"}'
```

**Response:**
```json
{
  "success": true,
  "mode": "auto"
}
```

#### Capture Photo
```bash
curl -X POST http://localhost:8080/api/camera/Front%20Door/media/thumbnail/new \
  --output front_door.jpg
```

#### Start Recording
```bash
curl -X POST http://localhost:8080/api/camera/Front%20Door/record
```

**Response:**
```json
{
  "success": true,
  "message": "Recording started"
}
```

#### Download Recent Clip
```bash
# First, get the list of recent clips
curl http://localhost:8080/api/camera/Front%20Door/media/clips

# Then download a specific clip
curl -X POST http://localhost:8080/api/camera/Front%20Door/media/clip/download \
  -H "Content-Type: application/json" \
  -d '{"clip_url": "https://..."}' \
  --output video.mp4
```

#### Update Camera Settings
```bash
# Enable snooze
curl -X POST http://localhost:8080/api/camera/Front%20Door/snooze \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Disable arming
curl -X POST http://localhost:8080/api/camera/Front%20Door/arm \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

#### Control Sync Module
```bash
# Arm all cameras in sync module
curl -X POST http://localhost:8080/api/sync/Sync%20Module/arm \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### � Schedule Management Endpoints

The schedule management system allows you to create automated rules that run at specified intervals with flexible time restrictions.

```
GET    /api/schedules              # List all scheduled rules
POST   /api/schedules              # Create a new schedule
PUT    /api/schedules/<id>         # Update existing schedule
DELETE /api/schedules/<id>         # Delete a schedule
GET    /api/history/battery        # Get battery level history
GET    /api/history/status         # Get camera online/offline status history
GET    /api/history/media          # Get media download history
```

#### Create Schedule Example

Create a schedule to enable motion detection every 4 hours for 4 hours:

```bash
curl -X POST http://localhost:8080/api/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "Barn Driveway Motion",
    "rule_type": "CAMERA_MOTION",
    "target_id": "Front Door",
    "action": "enable",
    "enabled": true,
    "interval_hours": 4,
    "interval_minutes": 0,
    "duration_hours": 4,
    "start_minute": 0
  }'
```

#### Schedule at Specific Minute Example

Run a thumbnail capture at 27 minutes past each hour:

```bash
curl -X POST http://localhost:8080/api/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "Hourly Thumbnail",
    "rule_type": "CAMERA_THUMBNAIL",
    "target_id": "Front Door",
    "action": "capture",
    "enabled": true,
    "interval_hours": 1,
    "interval_minutes": 0,
    "start_minute": 27
  }'
```

#### Schedule with Time Window

Only arm cameras between 9 PM and 6 AM on weekdays:

```bash
curl -X POST http://localhost:8080/api/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "Nighttime Armed",
    "rule_type": "SYNC_ARM",
    "target_id": "Home",
    "action": "arm",
    "enabled": true,
    "interval_hours": 1,
    "interval_minutes": 0,
    "start_time": "21:00",
    "end_time": "06:00",
    "days_of_week": "mon,tue,wed,thu,fri"
  }'
```

**Schedule Fields:**
- `rule_name` - Descriptive name for the schedule
- `rule_type` - Action type: `CAMERA_MOTION`, `CAMERA_THUMBNAIL`, `SYNC_ARM`, `SYNC_DISARM`
- `target_id` - Camera or sync module name
- `action` - Specific action: `enable`, `disable`, `capture`, `arm`, `disarm`
- `enabled` - Whether the schedule is active
- `interval_hours` - Hours between runs (0-24)
- `interval_minutes` - Minutes between runs (0-59)
- `start_minute` - Optional: Run at specific minute (0-59)
- `duration_hours` - Optional: Auto-disable after this many hours
- `start_time` - Optional: Only run after this time (HH:MM)
- `end_time` - Optional: Only run before this time (HH:MM)
- `days_of_week` - Optional: Comma-separated days (mon,tue,wed,thu,fri,sat,sun)

### �🔐 Authenticated Requests

When authentication is enabled, include credentials:

**Basic Auth:**
```bash
curl -u username:password http://localhost:8080/api/state
```

**Session Cookie:**
```bash
# Login first
curl -c cookies.txt -X POST http://localhost:8080/auth/login \
  -d "username=admin&password=secret"

# Use session cookie
curl -b cookies.txt http://localhost:8080/api/state
```

## �🐳 Docker Deployment

### Using Docker Compose (Recommended)

1. **Clone and start**:
   ```bash
   git clone --recurse-submodules https://github.com/austinc3030/myblink.git
   cd myblink
   docker-compose up -d
   ```

2. **Configure**: Open http://localhost:8080 and enter your credentials

3. **Check logs**:
   ```bash
   docker-compose logs -f myblink
   ```

**Note**: Configuration and credentials are stored in the Docker volume `myblink-data` for persistence across container restarts.

### Using Docker Directly

```bash
# Build the image
docker build -t myblink .

# Create a volume for persistent data
docker volume create myblink-data

# Run the container
docker run -d \
  --name myblink \
  -v myblink-data:/data \
  -p 8080:8080 \
  -e WEB_PORT=8080 \
  -e WEB_HOST=0.0.0.0 \
  -e TZ=America/New_York \
  --restart unless-stopped \
  myblink
```

### Environment Variables

- `WEB_PORT`: Port for web interface (default: 8080)
- `WEB_HOST`: Host to bind to (default: 0.0.0.0)
- `MYBLINK_CONFIG`: Path to config file (default: /data/config.yaml)
- `MYBLINK_CREDS`: Path to credentials file (default: /data/credentials.json)
- `TZ`: Timezone (e.g., America/New_York)

### Managing Docker Volume Data

**View volume location**:
```bash
docker volume inspect myblink-data
```

**Backup volume**:
```bash
docker run --rm -v myblink-data:/data -v $(pwd):/backup alpine tar czf /backup/myblink-backup.tar.gz -C /data .
```

**Restore volume**:
```bash
docker run --rm -v myblink-data:/data -v $(pwd):/backup alpine tar xzf /backup/myblink-backup.tar.gz -C /data
```

**Remove volume** (⚠️ deletes all config and credentials):
```bash
docker-compose down -v
# Or: docker volume rm myblink-data
```

## 🔄 Migration Guide

### For Existing Users

If you're upgrading from a previous version with YAML credentials:

1. **Backup your old credentials**:
   ```bash
   cp app/credentials.yaml app/credentials.yaml.backup
   ```

2. **Start the new version**:
   ```bash
   python app/myblink.py
   # Or: docker-compose up -d
   ```

3. **Re-enter credentials** via web interface at http://localhost:8080

4. **Verify** everything works, then remove the old file:
   ```bash
   rm app/credentials.yaml.backup
   ```

### From Root Directory Structure

If upgrading from the old structure (files at root), run the migration script:

```bash
chmod +x migrate_to_app.sh
./migrate_to_app.sh
```

This moves all files into the `app/` directory and updates submodule paths.

## 📊 Project Structure

```
myblink/
├── app/                           # All application code
│   ├── myblink.py                # Main application orchestrator (470 lines)
│   ├── web_server.py             # Flask web server with PWA interface (930+ lines)
│   ├── healthcheck.py            # Docker healthcheck validator
│   ├── startup.sh                # Container initialization script
│   ├── requirements.txt          # Python dependencies
│   │
│   ├── modules/                  # Modular application components
│   │   ├── __init__.py          # Package exports
│   │   ├── models.py            # Data models and configuration (318 lines)
│   │   ├── exceptions.py        # Custom exception hierarchy
│   │   ├── config_manager.py    # Configuration persistence (378 lines)
│   │   ├── health_monitor.py    # Health status tracking
│   │   ├── voipms_handler.py    # VoIP.ms 2FA integration (205 lines)
│   │   ├── blink_handler.py     # Blink API integration (638 lines)
│   │   └── auth.py              # Authentication system (620 lines)
│   │
│   ├── web_static/              # Progressive Web App
│   │   ├── index.html           # Responsive UI with camera cards
│   │   ├── app.js               # Full-featured SPA (875+ lines)
│   │   ├── manifest.json        # PWA configuration
│   │   ├── sw.js                # Service worker for offline support
│   │   └── create_icons.py     # Icon generator utility
│   │
│   ├── blinkpy/                 # Blink API library (git submodule)
│   │   └── blinkpy/            # Core library with camera/sync modules
│   │
│   └── python-voipms/           # VoIP.ms API library (git submodule)
│       └── voipms/             # VoIP.ms client implementation
│
├── Dockerfile                    # Multi-stage container build
├── docker-compose.yml           # Docker Compose orchestration
├── config.example.yaml          # Configuration template with docs
├── credentials.example.yaml     # Credentials template (legacy)
├── migrate_config.py            # Config migration utility
└── README.md                    # This comprehensive guide

Docker Volume (persistent data):
├── config.yaml                  # System & operational configuration
└── (no separate credentials file - stored in config.yaml)

Documentation:
├── AUTH_GUIDE.md               # Complete authentication setup guide
├── AUTH_QUICKSTART.md          # Quick auth configuration
├── AUTH_REFERENCE.md           # Developer auth reference
├── AUTHENTICATION_IMPLEMENTED.md  # Implementation details
├── CONFIG_GUIDE.md             # Configuration reference
├── STATE_PERSISTENCE.md        # How state management works
└── MIGRATION_GUIDE.md          # Upgrade instructions
```

### Architecture Highlights

- **Modular Design**: Clean separation of concerns across 6 focused modules
- **Web-First**: Comprehensive REST API + intuitive PWA interface
- **Type Safety**: Dataclass models with validation
- **Error Resilience**: Hierarchical exception handling
- **Async Core**: Full async/await for non-blocking I/O
- **Health Monitoring**: Production-ready with active status tracking
- **Authentication**: Flexible multi-provider system (optional)
- **State Persistence**: Auto-saving YAML configuration

## Docker Healthcheck

The container includes a comprehensive healthcheck system that monitors the application's actual health status, not just whether the process is running.

**Important:** The healthcheck will correctly mark the container as **unhealthy** if Blink initialization fails, even if the process is still running. This allows Docker orchestration tools to detect and restart failed containers.

### How It Works

1. **Health Status Tracking**: `myblink.py` continuously writes its health status to `/tmp/myblink_health.json`
2. **Error Monitoring**: The application tracks consecutive errors and marks itself unhealthy after 3 consecutive failures
3. **Staleness Detection**: If the health status file isn't updated within 5 minutes, the container is marked unhealthy
4. **Active Verification**: The `healthcheck.py` script actively validates the health status every 30 seconds

### Health Check Thresholds

- **Update Interval**: Health status is updated every 30 seconds during normal operation
- **Timeout**: 5 minutes without updates = unhealthy
- **Max Consecutive Errors**: 3 errors in a row = unhealthy
- **Docker Check Interval**: Every 30 seconds
- **Retries**: 3 failed checks before marking container unhealthy

### Monitoring Health

Check container health status:
```bash
docker ps  # Shows health status in STATUS column
docker inspect myblink --format='{{.State.Health.Status}}'
```

View health check logs:
```bash
docker inspect myblink --format='{{range .State.Health.Log}}{{.Output}}{{end}}'
```

Manual health check:
```bash
docker exec myblink python3 /app/healthcheck.py
```

### Docker Compose Configuration

The healthcheck is built into the Dockerfile, but you can also configure or override it in your `docker-compose.yml`:

#### Basic Configuration (uses Dockerfile healthcheck)
```yaml
version: '3.8'
services:
  myblink:
    build: .
    container_name: myblink
    volumes:
      - ./app/config.yaml:/app/config.yaml
      - ./app/credentials.yaml:/app/credentials.yaml
    ports:
      - "8080:8080"
    restart: unless-stopped
```

#### With Restart on Unhealthy
```yaml
version: '3.8'
services:
  myblink:
    build: .
    container_name: myblink
    volumes:
      - ./app/config.yaml:/app/config.yaml
      - ./app/credentials.yaml:/app/credentials.yaml
    ports:
      - "8080:8080"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python3", "/app/healthcheck.py"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

#### With Custom Healthcheck Parameters
```yaml
version: '3.8'
services:
  myblink:
    build: .
    container_name: myblink
    volumes:
      - ./app/config.yaml:/app/config.yaml
      - ./app/credentials.yaml:/app/credentials.yaml
    ports:
      - "8080:8080"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python3", "/app/healthcheck.py"]
      interval: 1m        # Check every minute
      timeout: 10s        # Max 10 seconds per check
      retries: 5          # 5 failures before unhealthy
      start_period: 2m    # 2 minute grace period on startup
```

#### With Autoheal (automatically restart unhealthy containers)

First, add the autoheal container to automatically restart unhealthy services:

```yaml
version: '3.8'
services:
  myblink:
    build: .
    container_name: myblink
    volumes:
      - ./app/config.yaml:/app/config.yaml
      - ./app/credentials.yaml:/app/credentials.yaml
    ports:
      - "8080:8080"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python3", "/app/healthcheck.py"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    labels:
      - "autoheal=true"
  
  autoheal:
    image: willfarrell/autoheal:latest
    container_name: autoheal
    restart: unless-stopped
    environment:
      - AUTOHEAL_CONTAINER_LABEL=autoheal
      - AUTOHEAL_INTERVAL=10
      - AUTOHEAL_START_PERIOD=30
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

The autoheal container will automatically restart myblink if it becomes unhealthy.

## 📹 Camera Features  & Capabilities

MyBlink exposes **every function** of the BlinkPy library through its web interface and API. Here's a complete breakdown of what you can do with your cameras:

### 🎬 Camera Operations

#### **Motion Detection & Recording**
- **Arm/Disarm** (`arm_enabled`)
  - Enable/disable motion detection
  - Controls whether camera records on motion
  - Can be set per-camera or per-sync module
  
- **Snooze** (`snooze_enabled`)
  - Temporarily disable motion notifications
  - Camera still records, but notifications are silenced
  - Useful for high-traffic periods
  
- **Record Video** (`/api/camera/<name>/record`)
  - Manually trigger video recording
  - Creates clip saved to Blink cloud
  - Available in recent clips after completion

#### **Image Capture**
- **Thumbnail Updates** (`thumbnail_enabled`)
  - Auto-update thumbnails on schedule
  - Managed through configuration
  
- **Manual Capture** (`/api/camera/<name>/media/thumbnail/new`)
  - Instant photo capture via web UI or API
  - Downloads immediately after capture
  - Does not affect scheduled thumbnails

#### **Night Vision Control**
- **Three Modes** (`/api/camera/<name>/night_vision`)
  - **Off**: IR illuminator disabled
  - **On**: IR illuminator always active
  - **Auto**: Automatic based on ambient light
  - Controllable from camera card or info modal

### 📊 Camera Information

MyBlink provides access to all camera properties:

#### **Identity & Configuration**
- Camera name, ID, and serial number
- Product type (Catalina, Owl, Mini, Doorbell, etc.)
- Firmware version
- Network ID and sync module assignment

#### **Status & Health**
- **Battery**: Level (1-3), state (ok/replace), voltage
- **Temperature**: Current reading (°F and °C)
- **Temperature Calibrated**: Adjusted reading
- **WiFi Strength**: Signal quality (1-5 bars)
- **Sync Signal Strength**: Connection to sync module
- **Motion Detected**: Current motion state
- **Motion Enabled**: Armed status

#### **Media Library**
- **Thumbnail**: Current cached image
- **Latest Clip**: Most recent video recording
- **Recent Clips**: List of recent motion events with:
  - Timestamp (ISO format)
  - Clip URL for download
  - Automatic expiration after 24 hours
- **Last Record**: Timestamp of most recent event

### 🔄 Sync Module Functions

#### **Module-Wide Control**
- **Arm All Cameras**: Enable motion detection for entire module
- **Snooze All**: Silence notifications for all cameras
- Individual cameras can override module settings

#### **Module Information**
- Sync module name and ID
- Connected camera list
- Local storage status (Sync Module 2 only):
  - Enabled/disabled state
  - Storage compatibility
  - Active status
  - Manifest readiness

### 🎯 Advanced Features

#### **Local Storage** (Sync Module 2)
- Check storage status and compatibility
- View manifest state
- Access locally stored clips (when available)

#### **Live Streaming**
- Initialize live stream connection
- Get RTSP/IMMIS URLs
- Real-time video access (API integration required)

#### **Media Management**
- **Download Operations**:
  - Cached thumbnails (instant)
  - Fresh captures (triggers camera)
  - Latest video clips
  - Individual recent clips
- **Auto-Expiration**: Recent clips expire after set period
- **Bulk Download**: Via web UI or API

### 🔧 Configuration Persistence

All camera settings persist across restarts:
- **config.yaml** serves as state cache
- Web UI changes auto-save
- Settings applied on startup via `run_scheduled_jobs()`
- Smart sync-level optimization for efficiency

### 📱 Web UI Integration

Every BlinkPy feature is accessible through:
- **Camera Cards**: Quick controls (arm, snooze, thumbnails, night vision)
- **Action Buttons**: Capture and record
- **Info Modal**: Complete details and media management
- **API Endpoints**: Programmatic access for automation

### 🎨 User Experience Design

- **No Manual Config**: Everything through intuitive UI
- **Real-Time Feedback**: Loading states and success/error messages
- **Auto-Downloads**: Media files download with descriptive names
- **Smart Defaults**: Sensible settings out-of-the-box
- **Clear Labels**: No technical jargon, just plain actions

## Troubleshooting

### "Malformed login response: None" or Blink Authentication Failures

Your saved Blink credentials may be expired. See detailed troubleshooting guide: [BLINK_AUTH_TROUBLESHOOTING.md](BLINK_AUTH_TROUBLESHOOTING.md)

**Quick fix:**
```bash
docker stop myblink
# Clear the "blinkpy_conf" value in config.json (set it to "")
docker start myblink
docker logs -f myblink
```

### AttributeError: 'Blink' object has no attribute 'key_required'

This error means the git submodules are not initialized:

**Solution**:
```bash
# Initialize submodules
git submodule update --init --recursive

# Rebuild the Docker image
docker build -t myblink . --no-cache

# Recreate the container
docker-compose down
docker-compose up -d
```

### DeprecationWarning: There is no current event loop

This warning has been fixed in the latest version. If you see it:
```bash
git pull
docker build -t myblink .
docker-compose up -d --force-recreate
```

### Permission Errors in Docker

If you see permission errors like `Permission denied: '/app/.venv'` or `Permission denied: '/.local'`:

**Solution**: The startup.sh has been updated to not use virtual environments inside Docker. Rebuild your image:
```bash
docker build -t myblink .
docker-compose up -d --force-recreate
```

### Submodule Installation Failures

If you see errors installing `./blinkpy` or `./python-voipms`:

**Solution**: Ensure git submodules are initialized before building:
```bash
git submodule update --init --recursive
docker build -t myblink .
```

### Container Starts but App Crashes

Check the logs for specific errors:
```bash
docker logs myblink -f
```

If you see `AttributeError: 'Blink' object has no attribute 'key_required'`, this may indicate an outdated blinkpy version. Update submodules:
```bash
cd blinkpy
git pull origin main
cd ..
docker build -t myblink . --no-cache
```

### Health Check Fails Immediately

The healthcheck has a 60-second grace period on startup. If it fails before that:
- Check that `/tmp/myblink_health.json` exists in the container
- Verify the application is writing health status: `docker exec myblink cat /tmp/myblink_health.json`
- Check application logs: `docker logs myblink`

## 🌐 Web Interface

MyBlink includes an optional responsive web interface (PWA) for easy camera management.

### Features

- 📱 **Progressive Web App**: Install on iOS/Android for native app experience
- 🎛️ **Camera Controls**: Toggle snooze/arm/thumbnail for individual cameras
- 🔄 **Sync Management**: Control entire sync modules at once
- ⚙️ **Configuration**: Adjust settings through the UI
- 🌓 **Dark Mode**: Automatic light/dark theme support
- 📊 **Real-time Updates**: Auto-refresh to show new cameras
- 🎯 **Smart Optimization**: Automatically consolidates camera settings to sync-level

### Enabling the Web Interface

1. **Edit config.yaml**:
   ```yaml
   web_enabled: true
   web_port: 8080
   web_host: "0.0.0.0"
   ```

2. **Access the interface**:
   - Local: http://localhost:8080
   - Network: http://YOUR_SERVER_IP:8080

3. **Install as PWA** (optional):
   - **iOS**: Safari → Share → Add to Home Screen
   - **Android**: Chrome → Menu → Install app

### Docker with Web Interface

Add port mapping to docker-compose.yml:

```yaml
version: '3.8'
services:
  myblink:
    build: .
    container_name: myblink
    volumes:
      - ./app/config.yaml:/app/config.yaml
      - ./app/credentials.yaml:/app/credentials.yaml
    ports:
      - "8080:8080"  # Add this line
    restart: unless-stopped
```

Then enable in your config.yaml and restart:
```bash
docker-compose down
docker-compose up -d
```

### Security Warning

⚠️ **The web interface has NO AUTHENTICATION by default.**

**Recommendations**:
- Only expose on trusted networks
- Use a reverse proxy with authentication for remote access
- Configure firewall rules to restrict access
- Consider VPN for remote management

See [WEB_INTERFACE.md](WEB_INTERFACE.md) for detailed security recommendations.

### Configuration Management

MyBlink uses a hybrid configuration approach:

**Managed via config.yaml** (system/infrastructure settings):
- `debug_mode` - Enable debug logging
- `health_file` - Health check file path
- `health_check_interval` - Health monitoring frequency
- `max_consecutive_errors` - Error threshold
- `voipms_message_keyword` - SMS keyword for 2FA
- `voipms_retry_limit` - 2FA retrieval attempts
- `voipms_retry_delay` - Delay between 2FA attempts
- `status_log_interval` - Status logging frequency
- `main_loop_sleep` - Main loop sleep duration
- `error_recovery_sleep` - Error recovery delay
- `web_enabled` - Enable/disable web interface
- `web_port` - Web server port
- `web_host` - Web server host binding

**Managed via Web UI** (operational settings):
- `schedule_interval_hours` - Job scheduling interval
- `blink_retry_limit` - Blink API retry limit
- `voipms_sms_wait` - SMS delivery wait time
- All camera/sync operation settings:
  - `snooze_syncs`, `no_snooze_syncs`
  - `snooze_cams`, `no_snooze_cams`
  - `arm_syncs`, `no_arm_syncs`
  - `arm_cams`, `no_arm_cams`
  - `thumbnail_cams`, `no_thumbnail_cams`

The web UI automatically saves changes back to config.yaml, so all settings persist across restarts.

### Documentation

- [Quick Start Guide](QUICKSTART_WEB.md) - Get started quickly
- [Full Web Interface Documentation](WEB_INTERFACE.md) - Complete guide including API endpoints, customization, and security

## 📚 Additional Documentation

### Core Documentation
- [Authentication Guide](AUTH_GUIDE.md) - Complete authentication setup (Basic + OIDC)
- [Authentication Quick Start](AUTH_QUICKSTART.md) - Quick auth configuration
- [Authentication Reference](AUTH_REFERENCE.md) - Developer quick reference
- [State Persistence](STATE_PERSISTENCE.md) - How configuration state works

### Configuration & Setup
- [Configuration Guide](CONFIG_GUIDE.md) - Detailed configuration reference
- [Migration Guide](MIGRATION_GUIDE.md) - Upgrading to app/ structure
- [Config Update Summary](CONFIG_UPDATE_SUMMARY.md) - Latest configuration changes

### Advanced Topics
- [Blink Auth Troubleshooting](BLINK_AUTH_TROUBLESHOOTING.md) - Credential issues
- [Authentication Implementation](AUTHENTICATION_IMPLEMENTED.md) - Technical implementation details

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

### Reporting Issues
1. Check [existing issues](https://github.com/austinc3030/myblink/issues) first
2. Use issue templates when available
3. Include:
   - MyBlink version
   - Docker/Python version
   - Steps to reproduce
   - Relevant log excerpts

### Submitting Pull Requests
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes:
   - Follow existing code style
   - Add tests if applicable
   - Update documentation
4. Commit with clear messages (`git commit -m 'Add amazing feature'`)
5. Push to your fork (`git push origin feature/amazing-feature`)
6. Open a Pull Request

### Development Setup
```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/austinc3030/myblink.git
cd myblink/app

# Install dependencies
pip install -r requirements.txt

# Run locally
python myblink.py
```

### Code Guidelines
- **Python**: Follow PEP 8, use type hints where possible
- **JavaScript**: ES6+, clear variable names, comments for complex logic
- **Documentation**: Update README.md and relevant docs
- **Testing**: Test manually with real Blink cameras when possible

## 🙏 Acknowledgments

MyBlink is built on the shoulders of giants:

### Core Libraries
- **[BlinkPy](https://github.com/fronzbot/blinkpy)** by [@fronzbot](https://github.com/fronzbot) - The excellent Blink API library that powers camera communication
- **[python-voipms](https://github.com/4doom4/python-voipms)** by [@4doom4](https://github.com/4doom4) - VoIP.ms API client for 2FA SMS retrieval

### Framework & Tools
- **[Flask](https://flask.palletsprojects.com/)** - Lightweight web framework
- **[Flask-Login](https://flask-login.readthedocs.io/)** - Session management
- **[Authlib](https://authlib.org/)** - OAuth/OIDC implementation
- **[bcrypt](https://github.com/pyca/bcrypt/)** - Secure password hashing
- **[aiohttp](https://docs.aiohttp.org/)** - Async HTTP client/server
- **[PyYAML](https://pyyaml.org/)** - YAML parser

### Special Thanks
- All contributors who have submitted PRs, issues, and feedback
- The Blink community for testing and feature requests
- Docker team for excellent containerization tools

## 📄 License

This project is licensed under the MIT License - see below for details:

```
MIT License

Copyright (c) 2024 Austin Chastain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 🔗 Links

- **Repository**: https://github.com/austinc3030/myblink
- **Issues**: https://github.com/austinc3030/myblink/issues
- **Docker Hub**: *(coming soon)*
- **Discussions**: https://github.com/austinc3030/myblink/discussions

---

<div align="center">

**Made with ❤️ for the Blink community**

If you find MyBlink useful, please give it a ⭐ on GitHub!

[Report Bug](https://github.com/austinc3030/myblink/issues) · [Request Feature](https://github.com/austinc3030/myblink/issues) · [Contribute](https://github.com/austinc3030/myblink/pulls)

</div>


