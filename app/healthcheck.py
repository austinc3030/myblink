#!/usr/bin/env python3
"""
Health check script for myblink Docker container.
Validates that the application is running properly and hasn't encountered critical errors.
"""

import json
import sys
import time
import os

HEALTH_FILE = "/tmp/myblink_health.json"
HEALTH_TIMEOUT = 300  # 5 minutes - must match myblink.py setting
MAX_CONSECUTIVE_ERRORS = 3  # Must match myblink.py setting

def check_health():
    """
    Check if the application is healthy based on the health status file.
    Returns exit code 0 for healthy, 1 for unhealthy.
    """
    
    # Check if health file exists
    if not os.path.exists(HEALTH_FILE):
        print(f"UNHEALTHY: Health status file not found at {HEALTH_FILE}")
        return 1
    
    try:
        # Read health status
        with open(HEALTH_FILE, "r") as f:
            health_data = json.load(f)
        
        # Check if explicitly marked as unhealthy
        if not health_data.get("healthy", False):
            message = health_data.get("message", "Unknown reason")
            error = health_data.get("error")
            print(f"UNHEALTHY: {message}")
            if error:
                print(f"  Error: {error}")
            return 1
        
        # Check if too many consecutive errors
        consecutive_errors = health_data.get("consecutive_errors", 0)
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            print(f"UNHEALTHY: Too many consecutive errors ({consecutive_errors})")
            return 1
        
        # Check timestamp to ensure app is updating health status
        timestamp = health_data.get("timestamp", 0)
        current_time = time.time()
        time_since_update = current_time - timestamp
        
        if time_since_update > HEALTH_TIMEOUT:
            print(f"UNHEALTHY: Health status not updated in {int(time_since_update)} seconds")
            print(f"  Last update: {time.ctime(timestamp)}")
            return 1
        
        # All checks passed
        message = health_data.get("message", "Running")
        print(f"HEALTHY: {message} (updated {int(time_since_update)}s ago)")
        return 0
        
    except json.JSONDecodeError as e:
        print(f"UNHEALTHY: Failed to parse health status file: {e}")
        return 1
    except Exception as e:
        print(f"UNHEALTHY: Error checking health status: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(check_health())
