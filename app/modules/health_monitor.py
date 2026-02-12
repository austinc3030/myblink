"""
Health monitoring for MyBlink application.

Manages health status tracking and persistence for external monitoring.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from .models import HealthStatus, HealthData, AppConfig


class HealthMonitor:
    """
    Manages application health status.
    
    Tracks consecutive errors and persists health status to file
    for external monitoring systems (e.g., Docker healthcheck).
    """
    
    def __init__(self, config: AppConfig, logger: Optional[logging.Logger] = None):
        """
        Initialize health monitor.
        
        Args:
            config: Application configuration
            logger: Logger instance (creates new one if not provided)
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.consecutive_errors = 0
    
    def update_status(
        self,
        status: HealthStatus,
        message: str,
        error: Optional[Exception] = None
    ) -> None:
        """
        Update health status file for external monitoring.
        
        Args:
            status: Current health status
            message: Human-readable status message
            error: Optional exception that caused status change
        """
        try:
            # Update consecutive error counter
            if status == HealthStatus.HEALTHY:
                self.consecutive_errors = 0
            elif status == HealthStatus.UNHEALTHY:
                self.consecutive_errors += 1
            
            health_data = HealthData(
                status=status,
                timestamp=time.time(),
                message=message,
                consecutive_errors=self.consecutive_errors,
                error=str(error) if error else None
            )
            
            # Ensure directory exists
            health_file = Path(self.config.health_file)
            health_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(health_file, 'w') as f:
                json.dump(health_data.to_dict(), f, indent=2)
            
            self.logger.debug(f"Health status updated: {status.value} - {message}")
            
        except Exception as e:
            self.logger.error(f"Failed to update health status: {e}")
    
    def is_healthy(self) -> bool:
        """Check if consecutive errors exceed threshold."""
        return self.consecutive_errors < self.config.max_consecutive_errors
    
    def get_consecutive_errors(self) -> int:
        """Get current consecutive error count."""
        return self.consecutive_errors
    
    def reset_errors(self) -> None:
        """Reset consecutive error counter."""
        self.consecutive_errors = 0
