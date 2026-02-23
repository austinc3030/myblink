#!/usr/bin/env python3
"""
Debug script for testing Blink Live Stream functionality.

This script:
1. Loads credentials from data/config.yaml (checks multiple locations)
2. Authenticates with Blink
3. Finds an online camera
4. Starts a live stream
5. Validates the stream is receiving data
"""

import asyncio
import logging
import sys
import yaml
import json
from pathlib import Path
from datetime import datetime
from aiohttp import ClientSession

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent / 'app'))

# Import from the correct blinkpy module structure
from blinkpy.blinkpy.blinkpy import Blink
from blinkpy.blinkpy.auth import Auth

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress some noisy loggers
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


class LiveStreamDebugger:
    """Debug helper for testing live stream functionality."""
    
    def __init__(self):
        self.blink = None
        self.session = None
        self.config = None
        self.credentials = None
        
    async def load_config(self, config_path: str = None):
        """Load configuration from YAML file."""
        # Try multiple possible config locations
        possible_paths = [
            config_path,
            "/data/config.yaml",
            "data/config.yaml",
            "/workspaces/myblink/data/config.yaml",
            str(Path(__file__).parent / "data" / "config.yaml")
        ]
        
        config_file = None
        for path in possible_paths:
            if path and Path(path).exists():
                config_file = Path(path)
                break
        
        if not config_file:
            logger.error(f"Config file not found. Tried: {[str(p) for p in possible_paths if p]}")
            return False
        
        logger.info(f"Loading configuration from {config_file}")
        
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Extract credentials
        username = self.config.get('blink_username')
        password = self.config.get('blink_password')
        cached_creds = self.config.get('blink_cached_credentials')
        
        if not username or not password:
            logger.error("Missing blink_username or blink_password in config")
            return False
        
        self.credentials = {
            'username': username,
            'password': password
        }
        
        # Parse cached credentials if available
        if cached_creds:
            try:
                self.credentials['cached'] = json.loads(cached_creds)
                logger.info("Found cached credentials")
            except json.JSONDecodeError:
                logger.warning("Failed to parse cached credentials")
        
        logger.info(f"Loaded credentials for user: {username}")
        return True
    
    async def authenticate(self):
        """Authenticate with Blink servers."""
        logger.info("Authenticating with Blink...")
        
        self.session = ClientSession()
        self.blink = Blink(session=self.session)
        
        # Use cached credentials if available
        if 'cached' in self.credentials:
            logger.info("Using cached credentials")
            self.blink.auth = Auth(self.credentials['cached'], no_prompt=True)
        else:
            logger.info("Using username/password (may require 2FA)")
            self.blink.auth = Auth({
                'username': self.credentials['username'],
                'password': self.credentials['password']
            }, no_prompt=True)
        
        # Start blink
        success = await self.blink.start()
        
        if not success:
            logger.error("Failed to authenticate with Blink")
            return False
        
        logger.info(f"✓ Authentication successful!")
        logger.info(f"  Account ID: {self.blink.account_id}")
        logger.info(f"  Region: {self.blink.auth.region_id}")
        
        return True
    
    async def list_cameras(self):
        """List all available cameras."""
        if not self.blink.cameras:
            logger.warning("No cameras found")
            return []
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Available Cameras ({len(self.blink.cameras)}):")
        logger.info(f"{'='*60}")
        
        cameras = []
        for name, camera in self.blink.cameras.items():
            # Get attributes from the camera
            attrs = camera.attributes
            battery = attrs.get('battery', 'N/A')
            armed = camera.arm
            motion_enabled = camera.motion_enabled
            camera_type = camera.camera_type
            sync_name = camera.sync.name if camera.sync else 'Unknown'
            
            logger.info(f"\n  Camera: {name}")
            logger.info(f"    Armed: {armed}")
            logger.info(f"    Motion Enabled: {motion_enabled}")
            logger.info(f"    Battery: {battery}")
            logger.info(f"    Type: {camera_type}")
            logger.info(f"    Network: {sync_name}")
            
            # Consider camera online if it has motion_enabled set (not None)
            is_online = motion_enabled is not None
            logger.info(f"    Available: {is_online}")
            
            cameras.append({
                'name': name,
                'camera': camera,
                'online': is_online,
                'armed': armed
            })
        
        return cameras
    
    async def find_online_camera(self, camera_name: str = None):
        """Find an available camera to test with."""
        cameras = await self.list_cameras()
        
        if not cameras:
            logger.error("No cameras available")
            return None
        
        # If specific camera requested, find it
        if camera_name:
            for cam_info in cameras:
                if cam_info['name'].lower() == camera_name.lower():
                    logger.info(f"\n✓ Found requested camera: {cam_info['name']}")
                    return cam_info['camera']
            logger.warning(f"Requested camera '{camera_name}' not found, using first available")
        
        # Find first online/available camera
        for cam_info in cameras:
            if cam_info['online']:
                logger.info(f"\n✓ Found available camera: {cam_info['name']}")
                return cam_info['camera']
        
        # If no explicitly online cameras, just use the first one
        logger.warning("No cameras explicitly marked as available, trying first camera...")
        return cameras[0]['camera']
    
    async def test_live_stream(self, camera):
        """Test live stream functionality for a camera."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing Live Stream: {camera.name}")
        logger.info(f"{'='*60}")
        
        try:
            # Request live stream
            logger.info("\n[1/5] Requesting live stream from Blink servers...")
            stream = await camera.init_livestream()
            
            if not stream:
                logger.error("✗ Failed to request live stream")
                return False
            
            logger.info(f"✓ Live stream requested successfully")
            logger.info(f"  Stream object: {stream}")
            logger.info(f"  Command ID: {stream.command_id if hasattr(stream, 'command_id') else 'N/A'}")
            
            # Start the stream server
            logger.info("\n[2/5] Starting local stream server...")
            server = await stream.start(host='127.0.0.1', port=0)
            
            if not server:
                logger.error("✗ Failed to start stream server")
                return False
            
            logger.info(f"✓ Stream server started")
            logger.info(f"  URL: {stream.url}")
            logger.info(f"  Is serving: {stream.is_serving}")
            
            # Start feeding data
            logger.info("\n[3/5] Starting stream feed (wait for camera + authentication + data relay)...")
            logger.info("  Note: This may take 10-30 seconds for camera to reach live view stage")
            feed_task = asyncio.create_task(stream.feed())
            
            # Give it time to wait for camera readiness (up to 30s), connect and authenticate
            # The feed() now waits for camera to reach 'lv' or 'vs' stage before connecting
            await asyncio.sleep(35)
            
            if feed_task.done():
                # Check if it failed
                try:
                    feed_task.result()
                except Exception as e:
                    logger.error(f"✗ Feed task failed: {e}")
                    return False
            
            logger.info("✓ Stream feed started")
            
            # Check if feed task failed early
            if feed_task.done():
                try:
                    feed_task.result()
                    logger.warning("Feed task completed early (no error but also no stream)")
                except Exception as e:
                    logger.error(f"✗ Feed task failed: {e}")
                    return False
            
            # Check if server is still serving
            if not stream.is_serving:
                logger.error("✗ Server stopped serving (stream may have failed)")
                return False
            
            # Connect as a client to consume the stream
            logger.info("\n[4/5] Connecting as client to consume stream data...")
            
            # Extract host and port from stream URL
            try:
                sockname = stream.socket.getsockname()
            except (IndexError, AttributeError) as e:
                logger.error(f"✗ Failed to get server socket (server may be closed): {e}")
                return False
            stream_host = sockname[0]
            stream_port = sockname[1]
            logger.info(f"  Connecting to {stream_host}:{stream_port}")
            
            try:
                client_reader, client_writer = await asyncio.open_connection(stream_host, stream_port)
                logger.info("✓ Client connected successfully")
                
                # Monitor for incoming data
                logger.info("\n[5/5] Monitoring for incoming stream data...")
                logger.info("  Reading data for 20 seconds...")
                
                total_bytes = 0
                chunks_received = 0
                start_time = asyncio.get_event_loop().time()
                
                async def read_stream():
                    nonlocal total_bytes, chunks_received
                    try:
                        while True:
                            # Try to read data with timeout
                            try:
                                data = await asyncio.wait_for(client_reader.read(4096), timeout=2.0)
                                if not data:
                                    logger.info("  Stream ended (no more data)")
                                    break
                                
                                chunks_received += 1
                                total_bytes += len(data)
                                
                                if chunks_received <= 5 or chunks_received % 10 == 0:
                                    logger.info(f"  Chunk {chunks_received}: {len(data)} bytes (total: {total_bytes} bytes)")
                                    if chunks_received <= 3:
                                        # Show first 32 bytes of first few chunks
                                        preview = data[:32].hex() if len(data) >= 32 else data.hex()
                                        logger.info(f"    First bytes: {preview}")
                                        
                            except asyncio.TimeoutError:
                                # No data for 2 seconds, but continue waiting
                                elapsed = asyncio.get_event_loop().time() - start_time
                                if elapsed > 20:
                                    logger.info(f"  Timeout reached after {elapsed:.1f}s")
                                    break
                                continue
                    except Exception as e:
                        logger.warning(f"  Read error: {e}")
                
                # Read for 20 seconds
                try:
                    await asyncio.wait_for(read_stream(), timeout=20.0)
                except asyncio.TimeoutError:
                    logger.info("  20-second monitoring period complete")
                
                # Final report
                logger.info(f"\n  Final statistics:")
                logger.info(f"    Total chunks: {chunks_received}")
                logger.info(f"    Total bytes: {total_bytes}")
                
                # Close client connection
                client_writer.close()
                await client_writer.wait_closed()
                logger.info("  Client disconnected")
                
                # Determine success
                if total_bytes > 0:
                    logger.info("✓ Successfully received stream data!")
                    success = True
                elif chunks_received > 0:
                    logger.warning("⚠ Received chunks but 0 bytes (unexpected)")
                    success = False
                else:
                    logger.warning("⚠ No data received (camera may still be waking up)")
                    success = False
                    
            except Exception as e:
                logger.error(f"✗ Failed to connect as client: {e}")
                success = False
            
            # Cleanup
            logger.info("\n[Cleanup] Stopping stream...")
            feed_task.cancel()
            try:
                await feed_task
            except asyncio.CancelledError:
                pass
            
            # Stop the stream (not async)
            stream.stop()
            
            # Wait for server to close
            if server:
                await server.wait_closed()
            
            logger.info("✓ Stream stopped and cleaned up")
            
            return success
            
        except Exception as e:
            logger.error(f"\n✗ Exception during live stream test: {e}", exc_info=True)
            return False
    
    async def run(self):
        """Run the complete debug sequence."""
        logger.info("\n" + "="*60)
        logger.info("Blink Live Stream Debug Script")
        logger.info("="*60)
        
        try:
            # Load config
            if not await self.load_config():
                return 1
            
            # Authenticate
            if not await self.authenticate():
                return 1
            
            # Find camera - using "Barn Driveway Left" for faster response
            camera = await self.find_online_camera("Barn Driveway Left")
            if not camera:
                logger.error("Camera not found")
                return 1
            
            # Test live stream
            success = await self.test_live_stream(camera)
            
            # Summary
            logger.info("\n" + "="*60)
            logger.info("Test Summary")
            logger.info("="*60)
            if success:
                logger.info("✓ Live stream test PASSED")
                logger.info("  The stream successfully started and received data")
                return 0
            else:
                logger.error("✗ Live stream test FAILED")
                logger.error("  The stream did not work as expected")
                logger.info("\nPossible reasons:")
                logger.info("  1. Camera is currently in use by Blink app or another client")
                logger.info("  2. Recent live view session still active (wait 30s)")
                logger.info("  3. Camera is busy or temporarily unavailable")
                logger.info("  4. Too many concurrent live view requests")
                logger.info("\nTroubleshooting:")
                logger.info("  - Close Blink app on all devices")
                logger.info("  - Wait 30-60 seconds between live view attempts")
                logger.info("  - Try a different camera")
                logger.info("  - Check if camera is actually online and responding")
                return 1
            
        except Exception as e:
            logger.error(f"\n✗ Fatal error: {e}", exc_info=True)
            return 1
        
        finally:
            # Cleanup - close Blink and session properly
            if self.blink and hasattr(self.blink, 'auth') and self.blink.auth:
                # Close any open streams or connections in Blink
                pass
            
            if self.session and not self.session.closed:
                await self.session.close()
                # Give the session a moment to fully close all connections
                await asyncio.sleep(0.25)
                logger.info("\nSession closed")
            else:
                logger.info("\nSession already closed")


async def main():
    """Main entry point."""
    debugger = LiveStreamDebugger()
    exit_code = await debugger.run()
    return exit_code


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
