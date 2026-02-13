#!/bin/bash
# Script to rebuild and restart the myblink container

echo "Stopping existing container..."
docker compose down

echo "Rebuilding container with updated files..."
docker compose build --no-cache

echo "Starting container..."
docker compose up -d

echo "Done! Container rebuilt and running."
echo "Remember to hard refresh your browser (Ctrl+Shift+R or Cmd+Shift+R)"
