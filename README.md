# myblink

## Install
```
git submodule update --init
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Docker Healthcheck

The container includes a comprehensive healthcheck system that monitors the application's actual health status, not just whether the process is running.

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
      - ./config.json:/app/config.json
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
      - ./config.json:/app/config.json
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
      - ./config.json:/app/config.json
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
      - ./config.json:/app/config.json
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

TEST

