"""
Schedule execution engine for MyBlink automated rules.

Runs as a background service to execute scheduled camera/sync actions
based on rules stored in the database.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from .db_models import ScheduleAction, ScheduledRule, ScheduleTarget
from .history_manager import HistoryManager


class ScheduleExecutor:
    """
    Executes scheduled rules for automated camera/sync operations.
    
    Runs in background, checking for due rules and executing them.
    """
    
    def __init__(
        self,
        history_manager: HistoryManager,
        blink_handler: any,  # BlinkHandler
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize schedule executor.
        
        Args:
            history_manager: HistoryManager for database access
            blink_handler: BlinkHandler for camera/sync operations
            logger: Logger instance
        """
        self.history_manager = history_manager
        self.blink_handler = blink_handler
        self.logger = logger or logging.getLogger(__name__)
        
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        self.check_interval = 60  # Check every 60 seconds
    
    async def start(self) -> None:
        """Start the schedule executor."""
        if self.is_running:
            self.logger.warning("Schedule executor already running")
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._run_loop())
        self.logger.info("Schedule executor started")
    
    async def stop(self) -> None:
        """Stop the schedule executor."""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Schedule executor stopped")
    
    async def _run_loop(self) -> None:
        """Main execution loop."""
        while self.is_running:
            try:
                # Check and execute scheduled rules
                await self._check_and_execute_rules()
                
                # Check and execute expired duration timers
                await self._check_and_execute_timers()
            except Exception as e:
                self.logger.error(f"Error in schedule executor loop: {e}", exc_info=True)
            
            # Sleep before next check
            await asyncio.sleep(self.check_interval)
    
    async def _check_and_execute_rules(self) -> None:
        """Check for due rules and execute them."""
        now = datetime.now()
        
        # Get rules that are due for execution
        due_rules = self.history_manager.get_rules_due_for_execution(now)
        
        if not due_rules:
            return
        
        self.logger.info(f"Found {len(due_rules)} rule(s) due for execution")
        
        for rule in due_rules:
            try:
                # Check if rule should run at this time
                if not self._should_run_now(rule, now):
                    # Calculate next run time and update
                    next_run = self._calculate_next_run(rule, now)
                    self.history_manager.mark_rule_executed(rule.id, next_run)
                    continue
                
                # Execute the rule
                await self._execute_rule(rule)
                
                # Calculate and set next run time
                next_run = self._calculate_next_run(rule, now)
                self.history_manager.mark_rule_executed(rule.id, next_run)
                
                self.logger.info(
                    f"Executed rule {rule.id}: {rule.action.value} {rule.target_type.value} '{rule.target_name}'. "
                    f"Next run: {next_run}"
                )
                
            except Exception as e:
                self.logger.error(f"Error executing rule {rule.id}: {e}", exc_info=True)
    
    def _should_run_now(self, rule: ScheduledRule, now: datetime) -> bool:
        """
        Check if rule should run at current time based on restrictions.
        
        Args:
            rule: Scheduled rule
            now: Current datetime
            
        Returns:
            True if rule should run now
        """
        # Check day of week restriction
        if rule.days_of_week:
            current_weekday = now.weekday()  # 0=Monday, 6=Sunday
            if current_weekday not in rule.days_of_week:
                return False
        
        # Check time window restriction
        if rule.start_time or rule.end_time:
            current_time = now.strftime("%H:%M")
            
            if rule.start_time and rule.end_time:
                # Handle time ranges that span midnight
                if rule.start_time <= rule.end_time:
                    # Normal range (e.g., 09:00 - 17:00)
                    if not (rule.start_time <= current_time <= rule.end_time):
                        return False
                else:
                    # Overnight range (e.g., 22:00 - 06:00)
                    if not (current_time >= rule.start_time or current_time <= rule.end_time):
                        return False
            elif rule.start_time:
                # Only start time specified
                if current_time < rule.start_time:
                    return False
            elif rule.end_time:
                # Only end time specified
                if current_time > rule.end_time:
                    return False
        
        # Check start minute restriction
        if rule.start_minute is not None:
            if now.minute != rule.start_minute:
                return False
        
        return True
    
    def _calculate_next_run(self, rule: ScheduledRule, now: datetime) -> Optional[datetime]:
        """
        Calculate next run time for a rule.
        
        Args:
            rule: Scheduled rule
            now: Current datetime
            
        Returns:
            Next run datetime, or None for one-time rules
        """
        # If no interval, it's a one-time rule
        if rule.interval_hours is None and rule.interval_minutes is None:
            return None
        
        # Calculate interval in minutes
        interval_minutes = (rule.interval_hours or 0) * 60 + (rule.interval_minutes or 0)
        
        if interval_minutes <= 0:
            return None
        
        # Calculate next run time
        next_run = now + timedelta(minutes=interval_minutes)
        
        # If start_minute is specified, adjust to that minute of the hour
        if rule.start_minute is not None:
            # Find next occurrence of the start minute
            next_run = next_run.replace(minute=rule.start_minute, second=0, microsecond=0)
            
            # If we've passed it this hour, move to next interval
            if next_run <= now:
                next_run += timedelta(minutes=interval_minutes)
        else:
            # No start_minute restriction, just add the interval
            next_run = next_run.replace(second=0, microsecond=0)
        
        return next_run
    
    async def _execute_rule(self, rule: ScheduledRule) -> None:
        """
        Execute a scheduled rule.
        
        Args:
            rule: Rule to execute
        """
        import time
        
        self.logger.info(
            f"Executing rule: {rule.action.value} {rule.target_type.value} '{rule.target_name}'"
        )
        
        start_time = time.time()
        success = False
        error_message = None
        
        try:
            # Determine which action to perform
            if rule.target_type == ScheduleTarget.CAMERA:
                await self._execute_camera_action(rule)
            else:  # SYNC
                await self._execute_sync_action(rule)
            
            success = True
            self.logger.info(f"Successfully executed rule {rule.id}")
            
        except Exception as e:
            success = False
            error_message = str(e)
            self.logger.error(f"Failed to execute rule {rule.id}: {e}", exc_info=True)
        
        finally:
            # Log the execution
            duration_ms = int((time.time() - start_time) * 1000)
            try:
                self.history_manager.log_schedule_execution(
                    rule_id=rule.id,
                    target_type=rule.target_type.value,
                    target_name=rule.target_name,
                    action=rule.action.value,
                    success=success,
                    error_message=error_message,
                    duration_ms=duration_ms,
                )
            except Exception as log_error:
                self.logger.error(f"Failed to log execution: {log_error}")
    
    async def _execute_camera_action(self, rule: ScheduledRule) -> None:
        """Execute an action on a camera."""
        camera = self.blink_handler._find_camera_in_blink(rule.target_name)
        
        if not camera:
            self.logger.warning(f"Camera '{rule.target_name}' not found for rule {rule.id}")
            return
        
        if rule.action == ScheduleAction.SNOOZE:
            # Enable snooze (motion detection off)
            await self.blink_handler.set_camera_motion_detect(rule.target_name, enable=False)
        elif rule.action == ScheduleAction.ARM:
            # Enable arm (motion detection on)
            await self.blink_handler.set_camera_motion_detect(rule.target_name, enable=True)
        elif rule.action == ScheduleAction.THUMBNAIL:
            # Capture new thumbnail
            await self.blink_handler.capture_thumbnail(rule.target_name)
    
    async def _execute_sync_action(self, rule: ScheduledRule) -> None:
        """Execute an action on a sync module."""
        sync = self.blink_handler._find_sync_in_blink(rule.target_name)
        
        if not sync:
            self.logger.warning(f"Sync '{rule.target_name}' not found for rule {rule.id}")
            return
        
        if rule.action == ScheduleAction.SNOOZE:
            # Disable entire sync module
            await self.blink_handler.set_sync_arm(rule.target_name, enable=False)
        elif rule.action == ScheduleAction.ARM:
            # Enable entire sync module
            await self.blink_handler.set_sync_arm(rule.target_name, enable=True)
        # Note: THUMBNAIL action doesn't make sense for sync modules
    
    async def _check_and_execute_timers(self) -> None:
        """Check for expired duration timers and revert their actions."""
        expired_timers = self.history_manager.get_expired_timers()
        
        if not expired_timers:
            return
        
        self.logger.info(f"Found {len(expired_timers)} expired timer(s) to process")
        
        for timer in expired_timers:
            try:
                await self._revert_timer_action(timer)
                
                # Delete the processed timer
                self.history_manager.delete_duration_timer(timer.id)
                
                self.logger.info(
                    f"Reverted timer {timer.id}: {timer.action.value} {timer.target_type.value} '{timer.target_name}'"
                )
            except Exception as e:
                self.logger.error(f"Error reverting timer {timer.id}: {e}", exc_info=True)
                # Delete the timer anyway to prevent repeated failures
                self.history_manager.delete_duration_timer(timer.id)
    
    async def _revert_timer_action(self, timer) -> None:
        """
        Revert the action of an expired duration timer.
        
        Args:
            timer: DurationTimer to revert
        """
        from .db_models import ScheduleAction, ScheduleTarget
        
        self.logger.info(
            f"Reverting {timer.action.value} for {timer.target_type.value} '{timer.target_name}'"
        )
        
        if timer.target_type == ScheduleTarget.CAMERA:
            # Revert camera action
            if timer.action == ScheduleAction.SNOOZE:
                # Un-snooze camera by disarming and re-arming the sync
                await self.blink_handler.unsnooze_camera(timer.target_name)
            elif timer.action == ScheduleAction.ARM:
                # Disarm camera
                await self.blink_handler.set_camera_motion_detect(timer.target_name, enable=False)
        else:  # SYNC
            # Revert sync action
            if timer.action == ScheduleAction.SNOOZE:
                # Un-snooze sync by disarming and re-arming
                await self.blink_handler.unsnooze_sync(timer.target_name)
            elif timer.action == ScheduleAction.ARM:
                # Disarm sync
                await self.blink_handler.set_sync_arm(timer.target_name, enable=False)
    
    async def execute_rule_now(self, rule_id: int) -> bool:
        """
        Manually execute a specific rule immediately.
        
        Args:
            rule_id: ID of rule to execute
            
        Returns:
            True if executed successfully
        """
        rule = self.history_manager.get_scheduled_rule(rule_id)
        
        if not rule:
            self.logger.error(f"Rule {rule_id} not found")
            return False
        
        try:
            await self._execute_rule(rule)
            
            # Update last run time (don't change next_run_at for manual execution)
            self.history_manager.mark_rule_executed(rule_id, rule.next_run_at)
            
            return True
        except Exception as e:
            self.logger.error(f"Error manually executing rule {rule_id}: {e}", exc_info=True)
            return False
