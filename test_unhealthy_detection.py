#!/usr/bin/env python3
"""
Test that health check correctly detects when Blink initialization fails
"""

import json
import time
import sys

# Simulate what happens when Blink fails to initialize
health_data = {
    "healthy": False,
    "timestamp": time.time(),
    "message": "Blink initialization failed at startup",
    "consecutive_errors": 0,
    "error": "Blink authentication failed - service not available"
}

# Write the unhealthy status
with open("/tmp/myblink_health.json", "w") as f:
    json.dump(health_data, f, indent=2)

print("Created health file with unhealthy status:")
print(json.dumps(health_data, indent=2))

# Run healthcheck
import subprocess
result = subprocess.run(
    ["python3", "/workspaces/myblink/healthcheck.py"],
    capture_output=True,
    text=True
)

print("\nHealthcheck output:")
print(result.stdout)

if result.returncode == 1:
    print("✅ PASS: Healthcheck correctly detected unhealthy status (exit code 1)")
    sys.exit(0)
else:
    print(f"❌ FAIL: Healthcheck should return exit code 1, but got {result.returncode}")
    sys.exit(1)
