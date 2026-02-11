# myblink

Automated Blink camera management with VoIP.ms 2FA integration and web-first configuration.

## ✨ Features

- 🔒 **Automatic 2FA**: Retrieves 2FA codes from VoIP.ms SMS
- 📸 **Scheduled Operations**: Auto-update thumbnails, rearm cameras, and manage snoozing
- 🌐 **Web Interface**: Responsive PWA for setup, configuration, and camera management
- 🔄 **Smart Refresh**: Auto-detects new cameras and handles configuration
- 💪 **Resilient**: Auto-retry with reinitialization on errors
- 🏥 **Health Monitoring**: Built-in healthcheck for Docker orchestration
- ⚡ **Zero Config**: No manual file editing - everything configurable via web UI

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

**Note**: No config files needed! Everything is configured through the web interface.

### Environment Variables

Configure the web server using environment variables:

```bash
export WEB_PORT=8080          # Port for web interface (default: 8080)
export WEB_HOST=0.0.0.0       # Host to bind to (default: 0.0.0.0)
export MYBLINK_CONFIG=/app/config.yaml        # Config file path (optional)
export MYBLINK_CREDS=/app/credentials.json    # Credentials file path (auto-created)
python myblink.py
```

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

### Credentials (Web UI Only)

**Do not manually create credentials files!** All credentials are managed through the web interface:

1. **Blink Account**: Your Blink email and password
2. **VoIP.ms API**: Your API username, password, and DID (phone number)

Credentials are automatically saved to `credentials.json` in a secure format.

### Camera Operations (Web UI Only)

All camera and sync module settings are managed exclusively through the web interface:

- **Snooze**: Enable/disable motion detection
- **Arm**: Enable/disable camera arming
- **Thumbnails**: Enable/disable automatic thumbnail updates

Changes are saved automatically and take effect on the next scheduled run.

## 🐳 Docker Deployment

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
├── app/                      # All application code
│   ├── myblink.py           # Main application
│   ├── web_server.py        # Web interface server
│   ├── healthcheck.py       # Docker healthcheck
│   ├── startup.sh           # Container startup script
│   ├── requirements.txt     # Python dependencies
│   ├── web_static/          # Web UI files
│   │   ├── index.html       # PWA interface
│   │   ├── app.js           # JavaScript application
│   │   ├── manifest.json    # PWA manifest
│   │   └── sw.js            # Service worker
│   ├── blinkpy/             # Blink API library (submodule)
│   └── python-voipms/       # VoIP.ms API library (submodule)
├── Dockerfile               # Container definition
├── docker-compose.yml       # Docker Compose configuration
├── migrate_to_app.sh        # Migration script
└── README.md               # This file

Docker Volume (persistent data):
├── config.yaml              # Your config (created by web UI)
└── credentials.json         # Your credentials (created by web UI)
```

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

- [Migration Guide](MIGRATION_GUIDE.md) - Complete guide for upgrading to app/ structure
- [Configuration Guide](CONFIG_GUIDE.md) - Detailed configuration options
- [Config Update Summary](CONFIG_UPDATE_SUMMARY.md) - Latest configuration changes

TEST

