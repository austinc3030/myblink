"""
Database models and schema for MyBlink time-series data and scheduling.

Uses SQLite for storing:
- Camera/sync scheduled rules (when to arm/snooze automatically)
- Battery level history (for graphing trends)
- Camera status history (online/offline tracking)
- Media download history (analytics and reporting)
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ScheduleAction(Enum):
    """Actions that can be scheduled."""
    SNOOZE = "snooze"
    ARM = "arm"
    THUMBNAIL = "thumbnail"


class ScheduleTarget(Enum):
    """Target type for scheduled actions."""
    CAMERA = "camera"
    SYNC = "sync"


class CameraStatus(Enum):
    """Camera online/offline status."""
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


# SQLite Schema
SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scheduled rules for cameras and syncs
CREATE TABLE IF NOT EXISTS scheduled_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,  -- 'camera' or 'sync'
    target_name TEXT NOT NULL,  -- camera/sync name
    action TEXT NOT NULL,       -- 'snooze', 'arm', 'thumbnail'
    enabled BOOLEAN DEFAULT 1,
    
    -- Schedule configuration
    interval_hours INTEGER,     -- Run every N hours (NULL for one-time)
    interval_minutes INTEGER,   -- Additional minutes offset
    start_minute INTEGER,       -- Which minute of the hour to start (0-59, NULL for any)
    duration_hours INTEGER,     -- How long to keep action enabled (NULL for permanent)
    
    -- Time window restrictions (optional)
    start_time TEXT,           -- HH:MM format (NULL for any time)
    end_time TEXT,             -- HH:MM format (NULL for any time)
    days_of_week TEXT,         -- Comma-separated: "0,1,2,3,4,5,6" (NULL for all days)
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_run_at TIMESTAMP,     -- When rule last executed
    next_run_at TIMESTAMP,     -- When rule should next execute
    
    -- Constraints
    UNIQUE(target_type, target_name, action)
);

-- Index for efficient rule lookups
CREATE INDEX IF NOT EXISTS idx_scheduled_rules_enabled 
ON scheduled_rules(enabled, next_run_at);

CREATE INDEX IF NOT EXISTS idx_scheduled_rules_target 
ON scheduled_rules(target_type, target_name);

-- Battery level history for trend tracking
CREATE TABLE IF NOT EXISTS battery_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_name TEXT NOT NULL,
    battery_level INTEGER NOT NULL,  -- 0-100 percentage
    voltage REAL,                    -- Battery voltage (if available)
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Index for efficient historical queries
    FOREIGN KEY (camera_name) REFERENCES cameras(name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_battery_history_camera 
ON battery_history(camera_name, recorded_at DESC);

-- Camera status history (online/offline tracking)
CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_name TEXT NOT NULL,
    status TEXT NOT NULL,           -- 'online', 'offline', 'unknown'
    signal_strength INTEGER,        -- WiFi signal strength (if available)
    temperature REAL,               -- Camera temperature (if available)
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (camera_name) REFERENCES cameras(name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_status_history_camera 
ON status_history(camera_name, recorded_at DESC);

-- Media download history for analytics
CREATE TABLE IF NOT EXISTS media_downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_name TEXT NOT NULL,
    sync_name TEXT NOT NULL,
    media_type TEXT NOT NULL,       -- 'clip' or 'thumbnail'
    media_id TEXT NOT NULL,         -- Blink's clip/thumbnail ID
    file_path TEXT NOT NULL,        -- Local file path
    file_size_bytes INTEGER,        -- File size
    created_at TIMESTAMP,           -- When media was created (from Blink)
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- When we downloaded it
    deleted_at TIMESTAMP,           -- When we deleted it (retention policy)
    
    UNIQUE(media_type, media_id)
);

CREATE INDEX IF NOT EXISTS idx_media_downloads_camera 
ON media_downloads(camera_name, downloaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_media_downloads_type 
ON media_downloads(media_type, camera_name);

-- Cameras reference table (for foreign keys)
CREATE TABLE IF NOT EXISTS cameras (
    name TEXT PRIMARY KEY,
    sync_name TEXT NOT NULL,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sync modules reference table
CREATE TABLE IF NOT EXISTS syncs (
    name TEXT PRIMARY KEY,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Schedule execution log for tracking when schedules run
CREATE TABLE IF NOT EXISTS schedule_execution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    target_name TEXT NOT NULL,
    action TEXT NOT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    duration_ms INTEGER,
    
    FOREIGN KEY (rule_id) REFERENCES scheduled_rules(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_schedule_log_rule 
ON schedule_execution_log(rule_id, executed_at DESC);

CREATE INDEX IF NOT EXISTS idx_schedule_log_time 
ON schedule_execution_log(executed_at DESC);

-- Duration timers for auto-reverting temporary arm/snooze actions
CREATE TABLE IF NOT EXISTS duration_timers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,  -- 'camera' or 'sync'
    target_name TEXT NOT NULL,  -- camera/sync name
    action TEXT NOT NULL,       -- 'snooze' or 'arm'
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(target_type, target_name, action)
);

CREATE INDEX IF NOT EXISTS idx_duration_timers_expiry 
ON duration_timers(expires_at);

CREATE INDEX IF NOT EXISTS idx_duration_timers_target 
ON duration_timers(target_type, target_name);
"""


@dataclass
class ScheduledRule:
    """Represents a scheduled rule for automatic camera/sync actions."""
    
    id: Optional[int]
    target_type: ScheduleTarget
    target_name: str
    action: ScheduleAction
    enabled: bool
    
    # Schedule timing
    interval_hours: Optional[int] = None
    interval_minutes: Optional[int] = None
    start_minute: Optional[int] = None
    duration_hours: Optional[int] = None
    
    # Time window restrictions
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    days_of_week: Optional[List[int]] = None
    
    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    
    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> 'ScheduledRule':
        """Create ScheduledRule from database row."""
        days_of_week = None
        if row['days_of_week']:
            days_of_week = [int(d) for d in row['days_of_week'].split(',')]
        
        return cls(
            id=row['id'],
            target_type=ScheduleTarget(row['target_type']),
            target_name=row['target_name'],
            action=ScheduleAction(row['action']),
            enabled=bool(row['enabled']),
            interval_hours=row['interval_hours'],
            interval_minutes=row['interval_minutes'],
            start_minute=row['start_minute'],
            duration_hours=row['duration_hours'],
            start_time=row['start_time'],
            end_time=row['end_time'],
            days_of_week=days_of_week,
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
            last_run_at=datetime.fromisoformat(row['last_run_at']) if row['last_run_at'] else None,
            next_run_at=datetime.fromisoformat(row['next_run_at']) if row['next_run_at'] else None,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'target_type': self.target_type.value,
            'target_name': self.target_name,
            'action': self.action.value,
            'enabled': self.enabled,
            'interval_hours': self.interval_hours,
            'interval_minutes': self.interval_minutes,
            'start_minute': self.start_minute,
            'duration_hours': self.duration_hours,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'days_of_week': self.days_of_week,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_run_at': self.last_run_at.isoformat() if self.last_run_at else None,
            'next_run_at': self.next_run_at.isoformat() if self.next_run_at else None,
        }


@dataclass
class BatteryRecord:
    """Battery level historical record."""
    
    id: Optional[int]
    camera_name: str
    battery_level: int
    voltage: Optional[float]
    recorded_at: datetime
    
    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> 'BatteryRecord':
        """Create BatteryRecord from database row."""
        return cls(
            id=row['id'],
            camera_name=row['camera_name'],
            battery_level=row['battery_level'],
            voltage=row['voltage'],
            recorded_at=datetime.fromisoformat(row['recorded_at']),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'camera_name': self.camera_name,
            'battery_level': self.battery_level,
            'battery_voltage': self.voltage,  # Frontend expects battery_voltage (in hundredths)
            'voltage': self.voltage,  # Keep original for compatibility
            'timestamp': self.recorded_at.isoformat(),  # Frontend expects timestamp
            'recorded_at': self.recorded_at.isoformat(),  # Keep original for compatibility
        }


@dataclass
class StatusRecord:
    """Camera status historical record."""
    
    id: Optional[int]
    camera_name: str
    status: CameraStatus
    signal_strength: Optional[int]
    temperature: Optional[float]
    recorded_at: datetime
    
    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> 'StatusRecord':
        """Create StatusRecord from database row."""
        return cls(
            id=row['id'],
            camera_name=row['camera_name'],
            status=CameraStatus(row['status']),
            signal_strength=row['signal_strength'],
            temperature=row['temperature'],
            recorded_at=datetime.fromisoformat(row['recorded_at']),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'camera_name': self.camera_name,
            'status': self.status.value,
            'is_online': self.status == CameraStatus.ONLINE,  # Frontend expects boolean is_online
            'signal_strength': self.signal_strength,
            'temperature': self.temperature,
            'timestamp': self.recorded_at.isoformat(),  # Frontend expects timestamp
            'recorded_at': self.recorded_at.isoformat(),  # Keep original for compatibility
        }


@dataclass
class MediaDownloadRecord:
    """Media download historical record."""
    
    id: Optional[int]
    camera_name: str
    sync_name: str
    media_type: str
    media_id: str
    file_path: str
    file_size_bytes: Optional[int]
    created_at: Optional[datetime]
    downloaded_at: datetime
    deleted_at: Optional[datetime]
    
    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> 'MediaDownloadRecord':
        """Create MediaDownloadRecord from database row."""
        return cls(
            id=row['id'],
            camera_name=row['camera_name'],
            sync_name=row['sync_name'],
            media_type=row['media_type'],
            media_id=row['media_id'],
            file_path=row['file_path'],
            file_size_bytes=row['file_size_bytes'],
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            downloaded_at=datetime.fromisoformat(row['downloaded_at']),
            deleted_at=datetime.fromisoformat(row['deleted_at']) if row['deleted_at'] else None,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'camera_name': self.camera_name,
            'sync_name': self.sync_name,
            'media_type': self.media_type,
            'media_id': self.media_id,
            'file_path': self.file_path,
            'file_size_bytes': self.file_size_bytes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'downloaded_at': self.downloaded_at.isoformat(),
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
        }


@dataclass
class ScheduleExecutionLog:
    """Schedule execution log record."""
    
    id: Optional[int]
    rule_id: int
    target_type: str
    target_name: str
    action: str
    executed_at: datetime
    success: bool
    error_message: Optional[str]
    duration_ms: Optional[int]
    
    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> 'ScheduleExecutionLog':
        """Create ScheduleExecutionLog from database row."""
        return cls(
            id=row['id'],
            rule_id=row['rule_id'],
            target_type=row['target_type'],
            target_name=row['target_name'],
            action=row['action'],
            executed_at=datetime.fromisoformat(row['executed_at']),
            success=bool(row['success']),
            error_message=row['error_message'],
            duration_ms=row['duration_ms'],
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'target_type': self.target_type,
            'target_name': self.target_name,
            'action': self.action,
            'executed_at': self.executed_at.isoformat(),
            'success': self.success,
            'error_message': self.error_message,
            'duration_ms': self.duration_ms,
        }


@dataclass
class DurationTimer:
    """Represents a duration timer for auto-reverting temporary actions."""
    
    id: Optional[int]
    target_type: ScheduleTarget
    target_name: str
    action: ScheduleAction
    expires_at: datetime
    created_at: datetime
    
    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> 'DurationTimer':
        """Create DurationTimer from database row."""
        return cls(
            id=row['id'],
            target_type=ScheduleTarget(row['target_type']),
            target_name=row['target_name'],
            action=ScheduleAction(row['action']),
            expires_at=datetime.fromisoformat(row['expires_at']),
            created_at=datetime.fromisoformat(row['created_at']),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'target_type': self.target_type.value,
            'target_name': self.target_name,
            'action': self.action.value,
            'expires_at': self.expires_at.isoformat(),
            'created_at': self.created_at.isoformat(),
        }


def initialize_database(db_path: Path) -> None:
    """
    Initialize database with schema.
    
    Args:
        db_path: Path to SQLite database file
        
    Raises:
        sqlite3.Error: If database initialization fails
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        
        # Execute schema
        cursor.executescript(SCHEMA_SQL)
        
        # Insert schema version if not exists
        cursor.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,)
        )
        
        conn.commit()
    finally:
        conn.close()
