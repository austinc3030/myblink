"""
History and scheduling database manager for MyBlink.

Provides high-level interface for:
- Managing scheduled rules (create, update, delete, query)
- Recording battery history
- Recording status changes
- Tracking media downloads
- Querying historical data for analytics
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .db_models import (
    BatteryRecord,
    CameraStatus,
    DurationTimer,
    MediaDownloadRecord,
    ScheduleAction,
    ScheduledRule,
    ScheduleExecutionLog,
    ScheduleTarget,
    StatusRecord,
    initialize_database,
)


class HistoryManager:
    """
    Manages SQLite database for historical data and scheduling.
    
    Thread-safe database operations with context manager for connections.
    """
    
    def __init__(self, db_path: Path, logger: Optional[logging.Logger] = None):
        """
        Initialize history manager.
        
        Args:
            db_path: Path to SQLite database file
            logger: Logger instance
        """
        self.db_path = db_path
        self.logger = logger or logging.getLogger(__name__)
        
        # Ensure database exists and is initialized
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize database if needed."""
        try:
            # Create database file if it doesn't exist
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            initialize_database(self.db_path)
            self.logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # ========== Camera/Sync Reference Management ==========
    
    def upsert_camera(self, camera_name: str, sync_name: str) -> None:
        """Register or update camera reference."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cameras (name, sync_name, last_seen)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    sync_name = excluded.sync_name,
                    last_seen = CURRENT_TIMESTAMP
                """,
                (camera_name, sync_name)
            )
    
    def upsert_sync(self, sync_name: str) -> None:
        """Register or update sync module reference."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO syncs (name, last_seen)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    last_seen = CURRENT_TIMESTAMP
                """,
                (sync_name,)
            )
    
    # ========== Scheduled Rules ==========
    
    def create_scheduled_rule(
        self,
        target_type: ScheduleTarget,
        target_name: str,
        action: ScheduleAction,
        interval_hours: Optional[int] = None,
        interval_minutes: Optional[int] = None,
        start_minute: Optional[int] = None,
        duration_hours: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        days_of_week: Optional[List[int]] = None,
        enabled: bool = True,
    ) -> int:
        """
        Create a new scheduled rule.
        
        Args:
            target_type: Camera or sync
            target_name: Name of camera/sync
            action: Action to perform (snooze, arm, thumbnail)
            interval_hours: Run every N hours
            interval_minutes: Additional minutes offset
            start_minute: Which minute of hour to start (0-59)
            duration_hours: How long to keep action enabled
            start_time: Start time window (HH:MM)
            end_time: End time window (HH:MM)
            days_of_week: List of days (0=Monday, 6=Sunday)
            enabled: Whether rule is active
            
        Returns:
            ID of created rule
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO scheduled_rules (
                    target_type, target_name, action, enabled,
                    interval_hours, interval_minutes, start_minute, duration_hours,
                    start_time, end_time, days_of_week
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_type.value,
                    target_name,
                    action.value,
                    enabled,
                    interval_hours,
                    interval_minutes,
                    start_minute,
                    duration_hours,
                    start_time,
                    end_time,
                    ','.join(map(str, days_of_week)) if days_of_week else None,
                )
            )
            return cursor.lastrowid
    
    def get_scheduled_rule(self, rule_id: int) -> Optional[ScheduledRule]:
        """Get a scheduled rule by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM scheduled_rules WHERE id = ?",
                (rule_id,)
            )
            row = cursor.fetchone()
            return ScheduledRule.from_db_row(row) if row else None
    
    def get_all_scheduled_rules(
        self,
        target_type: Optional[ScheduleTarget] = None,
        target_name: Optional[str] = None,
        action: Optional[ScheduleAction] = None,
        enabled_only: bool = False,
    ) -> List[ScheduledRule]:
        """
        Get scheduled rules with optional filtering.
        
        Args:
            target_type: Filter by target type
            target_name: Filter by target name
            action: Filter by action
            enabled_only: Only return enabled rules
            
        Returns:
            List of matching rules
        """
        query = "SELECT * FROM scheduled_rules WHERE 1=1"
        params = []
        
        if target_type:
            query += " AND target_type = ?"
            params.append(target_type.value)
        
        if target_name:
            query += " AND target_name = ?"
            params.append(target_name)
        
        if action:
            query += " AND action = ?"
            params.append(action.value)
        
        if enabled_only:
            query += " AND enabled = 1"
        
        query += " ORDER BY target_name, action"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [ScheduledRule.from_db_row(row) for row in cursor.fetchall()]
    
    def get_rules_due_for_execution(self, now: Optional[datetime] = None) -> List[ScheduledRule]:
        """
        Get rules that should be executed now.
        
        Args:
            now: Current time (defaults to datetime.now())
            
        Returns:
            List of rules due for execution
        """
        if now is None:
            now = datetime.now()
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM scheduled_rules
                WHERE enabled = 1 
                AND (next_run_at IS NULL OR next_run_at <= ?)
                ORDER BY next_run_at
                """,
                (now.isoformat(),)
            )
            return [ScheduledRule.from_db_row(row) for row in cursor.fetchall()]
    
    def update_scheduled_rule(
        self,
        rule_id: int,
        enabled: Optional[bool] = None,
        interval_hours: Optional[int] = None,
        interval_minutes: Optional[int] = None,
        start_minute: Optional[int] = None,
        duration_hours: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        days_of_week: Optional[List[int]] = None,
    ) -> bool:
        """
        Update an existing scheduled rule.
        
        Args:
            rule_id: ID of rule to update
            enabled: Enable/disable rule
            interval_hours: Update interval hours
            interval_minutes: Update interval minutes
            start_minute: Update start minute
            duration_hours: Update duration
            start_time: Update start time window
            end_time: Update end time window
            days_of_week: Update days of week
            
        Returns:
            True if rule was updated, False if not found
        """
        updates = []
        params = []
        
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(enabled)
        
        if interval_hours is not None:
            updates.append("interval_hours = ?")
            params.append(interval_hours)
        
        if interval_minutes is not None:
            updates.append("interval_minutes = ?")
            params.append(interval_minutes)
        
        if start_minute is not None:
            updates.append("start_minute = ?")
            params.append(start_minute)
        
        if duration_hours is not None:
            updates.append("duration_hours = ?")
            params.append(duration_hours)
        
        if start_time is not None:
            updates.append("start_time = ?")
            params.append(start_time)
        
        if end_time is not None:
            updates.append("end_time = ?")
            params.append(end_time)
        
        if days_of_week is not None:
            updates.append("days_of_week = ?")
            params.append(','.join(map(str, days_of_week)) if days_of_week else None)
        
        if not updates:
            return False
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(rule_id)
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE scheduled_rules SET {', '.join(updates)} WHERE id = ?",
                params
            )
            return cursor.rowcount > 0
    
    def mark_rule_executed(self, rule_id: int, next_run_at: Optional[datetime] = None) -> None:
        """
        Mark a rule as executed and optionally set next run time.
        
        Args:
            rule_id: ID of rule
            next_run_at: When rule should next execute
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE scheduled_rules
                SET last_run_at = CURRENT_TIMESTAMP,
                    next_run_at = ?
                WHERE id = ?
                """,
                (next_run_at.isoformat() if next_run_at else None, rule_id)
            )
    
    def delete_scheduled_rule(self, rule_id: int) -> bool:
        """
        Delete a scheduled rule.
        
        Args:
            rule_id: ID of rule to delete
            
        Returns:
            True if rule was deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM scheduled_rules WHERE id = ?",
                (rule_id,)
            )
            return cursor.rowcount > 0
    
    # ========== Schedule Execution Log ==========
    
    def log_schedule_execution(
        self,
        rule_id: int,
        target_type: str,
        target_name: str,
        action: str,
        success: bool,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> int:
        """
        Log a schedule execution.
        
        Args:
            rule_id: ID of the rule that was executed
            target_type: 'camera' or 'sync'
            target_name: Name of target
            action: Action performed
            success: Whether execution succeeded
            error_message: Error message if failed
            duration_ms: Execution duration in milliseconds
            
        Returns:
            ID of created log entry
        """
        from .db_models import ScheduleExecutionLog
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO schedule_execution_log 
                (rule_id, target_type, target_name, action, success, error_message, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rule_id, target_type, target_name, action, success, error_message, duration_ms)
            )
            return cursor.lastrowid
    
    def get_schedule_execution_log(
        self,
        rule_id: Optional[int] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List['ScheduleExecutionLog']:
        """
        Get schedule execution log entries.
        
        Args:
            rule_id: Filter by rule ID (None for all)
            since: Only entries after this time
            limit: Maximum entries to return
            
        Returns:
            List of execution log entries
        """
        from .db_models import ScheduleExecutionLog
        
        query = "SELECT * FROM schedule_execution_log WHERE 1=1"
        params = []
        
        if rule_id is not None:
            query += " AND rule_id = ?"
            params.append(rule_id)
        
        if since:
            query += " AND executed_at >= ?"
            params.append(since.isoformat())
        
        query += " ORDER BY executed_at DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [ScheduleExecutionLog.from_db_row(row) for row in cursor.fetchall()]
    
    def get_execution_stats(
        self,
        rule_id: Optional[int] = None,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get execution statistics.
        
        Args:
            rule_id: Filter by rule ID (None for all)
            since: Calculate stats from this time
            
        Returns:
            Dictionary with execution statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_executions,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_executions,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed_executions,
                AVG(duration_ms) as avg_duration_ms,
                MAX(executed_at) as last_execution
            FROM schedule_execution_log
            WHERE 1=1
        """
        params = []
        
        if rule_id is not None:
            query += " AND rule_id = ?"
            params.append(rule_id)
        
        if since:
            query += " AND executed_at >= ?"
            params.append(since.isoformat())
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            
            return {
                'total_executions': row['total_executions'] or 0,
                'successful_executions': row['successful_executions'] or 0,
                'failed_executions': row['failed_executions'] or 0,
                'avg_duration_ms': round(row['avg_duration_ms']) if row['avg_duration_ms'] else None,
                'last_execution': row['last_execution'],
                'success_rate': round((row['successful_executions'] or 0) / max(row['total_executions'] or 1, 1) * 100, 1),
            }
    
    # ========== Duration Timers ==========
    
    def create_duration_timer(
        self,
        target_type: ScheduleTarget,
        target_name: str,
        action: ScheduleAction,
        duration_hours: float,
    ) -> int:
        """
        Create or update a duration timer for auto-reverting an action.
        
        Args:
            target_type: Type of target (camera or sync)
            target_name: Name of camera or sync
            action: Action to revert (snooze or arm)
            duration_hours: How many hours until revert
            
        Returns:
            ID of created/updated timer
        """
        expires_at = datetime.now() + timedelta(hours=duration_hours)
        
        query = """
            INSERT INTO duration_timers (target_type, target_name, action, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(target_type, target_name, action) 
            DO UPDATE SET expires_at = excluded.expires_at, created_at = CURRENT_TIMESTAMP
        """
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                query,
                (target_type.value, target_name, action.value, expires_at.isoformat())
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_expired_timers(self) -> List[DurationTimer]:
        """
        Get all timers that have expired and should be processed.
        
        Returns:
            List of expired DurationTimer objects
        """
        query = """
            SELECT * FROM duration_timers
            WHERE expires_at <= ?
            ORDER BY expires_at ASC
        """
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, (datetime.now().isoformat(),))
            return [DurationTimer.from_db_row(row) for row in cursor.fetchall()]
    
    def delete_duration_timer(self, timer_id: int) -> bool:
        """
        Delete a duration timer.
        
        Args:
            timer_id: ID of timer to delete
            
        Returns:
            True if timer was deleted
        """
        query = "DELETE FROM duration_timers WHERE id = ?"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, (timer_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_duration_timers_for_target(
        self,
        target_type: ScheduleTarget,
        target_name: str,
        action: Optional[ScheduleAction] = None,
    ) -> int:
        """
        Delete all duration timers for a specific target.
        
        Args:
            target_type: Type of target (camera or sync)
            target_name: Name of camera or sync
            action: Specific action to delete (None for all actions)
            
        Returns:
            Number of timers deleted
        """
        if action:
            query = "DELETE FROM duration_timers WHERE target_type = ? AND target_name = ? AND action = ?"
            params = (target_type.value, target_name, action.value)
        else:
            query = "DELETE FROM duration_timers WHERE target_type = ? AND target_name = ?"
            params = (target_type.value, target_name)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount
    
    def get_active_timers(
        self,
        target_type: Optional[ScheduleTarget] = None,
        target_name: Optional[str] = None,
    ) -> List[DurationTimer]:
        """
        Get all active (not expired) duration timers.
        
        Args:
            target_type: Filter by target type (optional)
            target_name: Filter by target name (optional)
            
        Returns:
            List of active DurationTimer objects
        """
        query = "SELECT * FROM duration_timers WHERE expires_at > ?"
        params = [datetime.now().isoformat()]
        
        if target_type:
            query += " AND target_type = ?"
            params.append(target_type.value)
        
        if target_name:
            query += " AND target_name = ?"
            params.append(target_name)
        
        query += " ORDER BY expires_at ASC"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [DurationTimer.from_db_row(row) for row in cursor.fetchall()]
    
    # ========== Battery History ==========
    
    def record_battery_level(
        self,
        camera_name: str,
        battery_level: int,
        voltage: Optional[float] = None,
    ) -> int:
        """
        Record battery level for a camera.
        
        Args:
            camera_name: Camera name
            battery_level: Battery percentage (0-100)
            voltage: Battery voltage (optional)
            
        Returns:
            ID of created record
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO battery_history (camera_name, battery_level, voltage)
                VALUES (?, ?, ?)
                """,
                (camera_name, battery_level, voltage)
            )
            return cursor.lastrowid
    
    def get_battery_history(
        self,
        camera_name: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[BatteryRecord]:
        """
        Get battery history records.
        
        Args:
            camera_name: Filter by camera (None for all)
            since: Only records after this time
            limit: Maximum records to return
            
        Returns:
            List of battery records
        """
        query = "SELECT * FROM battery_history WHERE 1=1"
        params = []
        
        if camera_name:
            query += " AND camera_name = ?"
            params.append(camera_name)
        
        if since:
            query += " AND recorded_at >= ?"
            params.append(since.isoformat())
        
        query += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [BatteryRecord.from_db_row(row) for row in cursor.fetchall()]
    
    def get_battery_statistics(
        self,
        camera_name: str,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get battery statistics for a camera.
        
        Args:
            camera_name: Camera name
            since: Calculate stats from this time
            
        Returns:
            Dictionary with min, max, avg battery voltage (in hundredths)
        """
        query = """
            SELECT 
                MIN(voltage) as min_voltage,
                MAX(voltage) as max_voltage,
                AVG(voltage) as avg_voltage,
                COUNT(*) as sample_count
            FROM battery_history
            WHERE camera_name = ? AND voltage IS NOT NULL
        """
        params = [camera_name]
        
        if since:
            query += " AND recorded_at >= ?"
            params.append(since.isoformat())
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            
            return {
                'camera_name': camera_name,
                'min_voltage': int(row['min_voltage']) if row['min_voltage'] else None,
                'max_voltage': int(row['max_voltage']) if row['max_voltage'] else None,
                'average_voltage': int(round(row['avg_voltage'])) if row['avg_voltage'] else None,
                'sample_count': row['sample_count'],
            }
    
    # ========== Status History ==========
    
    def record_status(
        self,
        camera_name: str,
        status: CameraStatus,
        signal_strength: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> int:
        """
        Record camera status.
        
        Args:
            camera_name: Camera name
            status: Online/offline status
            signal_strength: WiFi signal strength
            temperature: Camera temperature
            
        Returns:
            ID of created record
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO status_history (camera_name, status, signal_strength, temperature)
                VALUES (?, ?, ?, ?)
                """,
                (camera_name, status.value, signal_strength, temperature)
            )
            return cursor.lastrowid
    
    def get_status_history(
        self,
        camera_name: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[StatusRecord]:
        """
        Get status history records.
        
        Args:
            camera_name: Filter by camera (None for all)
            since: Only records after this time
            limit: Maximum records to return
            
        Returns:
            List of status records
        """
        query = "SELECT * FROM status_history WHERE 1=1"
        params = []
        
        if camera_name:
            query += " AND camera_name = ?"
            params.append(camera_name)
        
        if since:
            query += " AND recorded_at >= ?"
            params.append(since.isoformat())
        
        query += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [StatusRecord.from_db_row(row) for row in cursor.fetchall()]
    
    def get_uptime_statistics(
        self,
        camera_name: str,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get uptime statistics for a camera.
        
        Args:
            camera_name: Camera name
            since: Calculate stats from this time
            
        Returns:
            Dictionary with uptime percentage and status counts
        """
        query = """
            SELECT 
                status,
                COUNT(*) as count
            FROM status_history
            WHERE camera_name = ?
        """
        params = [camera_name]
        
        if since:
            query += " AND recorded_at >= ?"
            params.append(since.isoformat())
        
        query += " GROUP BY status"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            status_counts = {row['status']: row['count'] for row in rows}
            total = sum(status_counts.values())
            
            online_count = status_counts.get('online', 0)
            uptime_pct = (online_count / total * 100) if total > 0 else 0
            
            return {
                'camera_name': camera_name,
                'uptime_percentage': round(uptime_pct, 2),
                'online_count': online_count,
                'offline_count': status_counts.get('offline', 0),
                'unknown_count': status_counts.get('unknown', 0),
                'total_samples': total,
            }
    
    # ========== Media Download History ==========
    
    def record_media_download(
        self,
        camera_name: str,
        sync_name: str,
        media_type: str,
        media_id: str,
        file_path: str,
        file_size_bytes: Optional[int] = None,
        created_at: Optional[datetime] = None,
    ) -> Optional[int]:
        """
        Record a media download.
        
        Args:
            camera_name: Camera name
            sync_name: Sync module name
            media_type: 'clip' or 'thumbnail'
            media_id: Blink's media ID
            file_path: Local file path
            file_size_bytes: File size
            created_at: When media was created
            
        Returns:
            ID of created record, or None if duplicate
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO media_downloads (
                        camera_name, sync_name, media_type, media_id,
                        file_path, file_size_bytes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        camera_name,
                        sync_name,
                        media_type,
                        media_id,
                        file_path,
                        file_size_bytes,
                        created_at.isoformat() if created_at else None,
                    )
                )
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Duplicate media_id
                return None
    
    def mark_media_deleted(self, media_id: str) -> bool:
        """
        Mark media as deleted (for retention policy tracking).
        
        Args:
            media_id: Media ID
            
        Returns:
            True if record was updated
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE media_downloads SET deleted_at = CURRENT_TIMESTAMP WHERE media_id = ?",
                (media_id,)
            )
            return cursor.rowcount > 0
    
    def get_media_download_history(
        self,
        camera_name: Optional[str] = None,
        media_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[MediaDownloadRecord]:
        """
        Get media download history.
        
        Args:
            camera_name: Filter by camera
            media_type: Filter by type ('clip' or 'thumbnail')
            since: Only records after this time
            limit: Maximum records to return
            
        Returns:
            List of media download records
        """
        query = "SELECT * FROM media_downloads WHERE 1=1"
        params = []
        
        if camera_name:
            query += " AND camera_name = ?"
            params.append(camera_name)
        
        if media_type:
            query += " AND media_type = ?"
            params.append(media_type)
        
        if since:
            query += " AND downloaded_at >= ?"
            params.append(since.isoformat())
        
        query += " ORDER BY downloaded_at DESC LIMIT ?"
        params.append(limit)
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [MediaDownloadRecord.from_db_row(row) for row in cursor.fetchall()]
    
    def get_media_statistics(
        self,
        camera_name: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get media download statistics.
        
        Args:
            camera_name: Filter by camera (None for all)
            since: Calculate stats from this time
            
        Returns:
            Dictionary with download counts and storage usage
        """
        query = """
            SELECT 
                media_type,
                COUNT(*) as count,
                SUM(file_size_bytes) as total_size,
                COUNT(CASE WHEN deleted_at IS NULL THEN 1 END) as active_count,
                SUM(CASE WHEN deleted_at IS NULL THEN file_size_bytes END) as active_size
            FROM media_downloads
            WHERE 1=1
        """
        params = []
        
        if camera_name:
            query += " AND camera_name = ?"
            params.append(camera_name)
        
        if since:
            query += " AND downloaded_at >= ?"
            params.append(since.isoformat())
        
        query += " GROUP BY media_type"
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            stats = {}
            for row in rows:
                stats[row['media_type']] = {
                    'total_downloads': row['count'],
                    'total_size_bytes': row['total_size'] or 0,
                    'active_count': row['active_count'],
                    'active_size_bytes': row['active_size'] or 0,
                }
            
            return stats
    
    # ========== Maintenance ==========
    
    def cleanup_old_records(
        self,
        battery_retention_days: int = 90,
        status_retention_days: int = 90,
        media_retention_days: int = 180,
    ) -> Dict[str, int]:
        """
        Clean up old historical records.
        
        Args:
            battery_retention_days: Keep battery records this many days
            status_retention_days: Keep status records this many days
            media_retention_days: Keep media records this many days
            
        Returns:
            Dictionary with count of deleted records per table
        """
        cutoff_battery = (datetime.now() - timedelta(days=battery_retention_days)).isoformat()
        cutoff_status = (datetime.now() - timedelta(days=status_retention_days)).isoformat()
        cutoff_media = (datetime.now() - timedelta(days=media_retention_days)).isoformat()
        
        deleted = {}
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM battery_history WHERE recorded_at < ?",
                (cutoff_battery,)
            )
            deleted['battery_history'] = cursor.rowcount
            
            cursor = conn.execute(
                "DELETE FROM status_history WHERE recorded_at < ?",
                (cutoff_status,)
            )
            deleted['status_history'] = cursor.rowcount
            
            cursor = conn.execute(
                "DELETE FROM media_downloads WHERE downloaded_at < ? AND deleted_at IS NOT NULL",
                (cutoff_media,)
            )
            deleted['media_downloads'] = cursor.rowcount
        
        return deleted
    
    def vacuum(self) -> None:
        """Optimize database by reclaiming space."""
        with self._get_connection() as conn:
            conn.execute("VACUUM")
