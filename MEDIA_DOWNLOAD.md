# Media Download & Archival Feature

## Overview

The Media Download & Archival feature automatically downloads and saves Blink camera clips and thumbnails to local storage or a NAS (Network Attached Storage). This ensures you have permanent copies of your camera footage with configurable retention policies.

## Features

### Automatic Downloads
- **Clips**: Automatically download motion-triggered video clips
- **Thumbnails**: Save camera thumbnail snapshots
- **Incremental**: Only downloads new media, tracking what's already downloaded
- **Scheduled**: Runs on a configurable interval (default: 15 minutes)

### Storage Organization
Files are organized in a structured directory hierarchy:
```
base_path/
├── clips/
│   └── [sync_name]/
│       └── [camera_name]/
│           ├── 20240115_143022_clip123.mp4
│           └── 20240115_150015_clip124.mp4
└── thumbnails/
    └── [sync_name]/
        └── [camera_name]/
            ├── 20240115_143022.jpg
            └── 20240115_150015.jpg
```

### Retention Policies
Choose how long to keep downloaded media:

1. **By Count** (default)
   - Keep the N most recent clips per camera
   - Example: Keep last 100 clips
   - Oldest files deleted when limit exceeded

2. **By Days**
   - Keep clips from the last N days
   - Example: Keep last 30 days of footage
   - Files older than threshold are deleted

3. **By Size**
   - Keep last N GB of clips per camera
   - Example: Keep last 10 GB per camera
   - Oldest files deleted when size limit exceeded

### NAS Support
Store media on network-attached storage:

- **SMB/CIFS**: Windows file shares, Samba
  - Requires username and password
  - Example: `//192.168.1.100/blink-media`

- **NFS**: Unix/Linux network file system
  - No authentication required (relies on network security)
  - Example: `192.168.1.100:/volume1/blink`

## Configuration

### Via Web Interface

1. Navigate to **Settings** (⚙️ icon)
2. Scroll to **💾 Media Download & Archival** section
3. Enable the feature with the checkbox
4. Configure options:
   - **Base Path**: Local directory for storage
   - **Check Interval**: How often to check for new media (minutes)
   - **Download Options**: Enable/disable clips and thumbnails
   - **Retention Policy**: Choose count/days/size and set value
   - **NAS Settings**: Optional network storage configuration

5. Click **Save Media Settings**
6. Use **Download Now** to manually trigger a download

### Via Configuration File

Add to `/app/config.yaml`:

```yaml
# Media download settings
media_download_enabled: true
media_download_clips: true
media_download_thumbnails: true
media_download_base_path: "/app/media"

# Retention policy
media_retention_type: "count"  # Options: count, days, size
media_retention_count: 100
media_retention_days: 30
media_retention_size_gb: 10.0

# Check interval
media_check_interval_minutes: 15

# NAS settings (optional)
media_use_nas: false
media_nas_type: "smb"  # Options: smb, nfs
media_nas_host: "192.168.1.100"
media_nas_share: "blink-media"
media_nas_username: "myblinkuser"
media_nas_password: "secure_password"
media_nas_mount_point: "/mnt/nas"
```

## API Endpoints

### Get Media Configuration
```bash
GET /api/media/config
```

Returns current media download configuration.

### Update Media Configuration
```bash
POST /api/media/config
Content-Type: application/json

{
  "enabled": true,
  "download_clips": true,
  "base_path": "/app/media",
  "retention_type": "count",
  "retention_count": 100,
  ...
}
```

### Get Download Status
```bash
GET /api/media/status
```

Returns:
```json
{
  "enabled": true,
  "running": true,
  "total_clips": 156,
  "total_thumbnails": 89,
  "total_size_bytes": 2147483648,
  "total_size_mb": 2048.0,
  "base_path": "/app/media"
}
```

### Manually Trigger Download
```bash
POST /api/media/download
```

Starts an immediate download job without waiting for the next scheduled run.

## Docker Configuration

### Volume Mounts

To persist downloaded media, mount a volume:

```yaml
services:
  myblink:
    volumes:
      - ./media:/app/media  # Media storage
      - ./config:/app/config  # Configuration
```

### NAS Mounting

For SMB/CIFS NAS access, the container needs elevated privileges:

```yaml
services:
  myblink:
    cap_add:
      - SYS_ADMIN  # Required for mounting filesystems
    devices:
      - /dev/fuse  # Required for FUSE mounts
    volumes:
      - ./media:/app/media
```

**Note**: Be cautious with `SYS_ADMIN` capability as it grants broad system access.

## Storage Recommendations

### Local Storage
- **Minimum**: 10 GB for basic archival
- **Recommended**: 50-100 GB for extensive recording
- **Large Deployment**: 500+ GB for multiple cameras with long retention

### NAS Storage
- Ideal for multi-terabyte archives
- Provides redundancy (RAID configurations)
- Can be shared with other applications
- Consider network bandwidth (downloads run periodically)

### Retention Guidelines
- **By Count**: 100 clips = ~1-2 GB per camera (varies by clip length)
- **By Days**: 30 days = 5-20 GB per camera (depends on motion frequency)
- **By Size**: 10 GB = approximately 100-500 clips per camera

## Tracking System

The system maintains a tracking file at `/app/media_tracking.json` to record:
- Downloaded clip IDs per camera
- Latest thumbnail downloads
- Prevents re-downloading existing media

This file is automatically managed and should not be edited manually.

## Troubleshooting

### Media Not Downloading

1. **Check media manager status** in Settings
   - Ensure "Enable automatic media downloads" is checked
   - Verify it shows "✅ Running"

2. **Verify base path** is writable
   ```bash
   docker exec myblink ls -la /app/media
   ```

3. **Check logs** for errors
   - Navigate to Settings → View Logs
   - Look for "media" related errors

### NAS Connection Issues

1. **Verify network connectivity**
   ```bash
   docker exec myblink ping [nas-host]
   ```

2. **Test NAS credentials**
   - Ensure username/password are correct
   - Check NAS allows connections from Docker network

3. **Check mount status**
   ```bash
   docker exec myblink mount | grep nas
   ```

### Disk Space Issues

1. **Check available space**
   ```bash
   docker exec myblink df -h /app/media
   ```

2. **Adjust retention policy** if needed
   - Reduce clip count
   - Decrease retention days
   - Lower size limit

3. **Manual cleanup** (if necessary)
   ```bash
   docker exec myblink find /app/media -type f -mtime +60 -delete
   ```

## Performance Considerations

- **Download frequency**: Balance between freshness and system load
  - More frequent = more CPU/network usage
  - Less frequent = larger download batches

- **Large deployments**: With many cameras
  - Consider staggered downloads
  - Increase check interval
  - Use NAS with good network bandwidth

- **Retention policies**: More retained media = more storage and slower cleanup
  - "By count" = most predictable storage usage
  - "By days" = easier to understand retention period
  - "By size" = guarantees space won't exceed limit

## Security Notes

1. **NAS Credentials**: Stored in config file
   - Ensure `/app/config` volume has restricted permissions
   - Consider using read-only NAS accounts

2. **SYS_ADMIN Capability**: Required for NAS mounting
   - Only enable if using remote storage
   - Understand the security implications

3. **Network Security**: NAS access
   - Use VLANs to isolate camera/storage network
   - Enable firewall rules on NAS
   - Consider encrypted shares (if performance allows)

## Future Enhancements

Potential improvements for future versions:
- Cloud storage integration (S3, Google Drive)
- Video transcoding (reduce file sizes)
- Motion detection zones (selective recording)
- Webhook notifications on new clips
- Web-based video player
- Search and tagging
- Timeline view
