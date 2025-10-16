FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy the startup script
COPY . /app

# Install dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Pip install
RUN pip install --no-cache-dir -r requirements.txt

# Make healthcheck script executable
RUN chmod +x /app/healthcheck.py

# Add healthcheck
# Runs every 30 seconds, starts checking after 60 seconds, 
# allows 10 seconds for the check to complete, 
# marks unhealthy after 3 consecutive failures
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 /app/healthcheck.py || exit 1

# Set entry point
CMD ["./startup.sh"]
