#!/usr/bin/env python3
"""
Test script to verify owner detection functionality with X-REMOTE-USER header.
"""

import asyncio
import logging
import os
import sys
import time

import socketio

log = logging.getLogger(__name__)


async def test_owner_detection():
    """Test owner detection with different user scenarios."""

    log.info("Testing owner detection functionality...")

    # Test 1: Same user (owner)
    log.info("\n=== Test 1: Same User (Owner) ===")
    await test_same_user_scenario()

    # Test 2: Different user (not owner)
    log.info("\n=== Test 2: Different User (Not Owner) ===")
    await test_different_user_scenario()


async def test_same_user_scenario():
    """Test scenario where the same user tries to reconnect to their closed session."""

    # Set X-REMOTE-USER header for first client
    os.environ["HTTP_X_REMOTE_USER"] = "testuser1"

    sio1 = socketio.AsyncClient()
    session_id = "owner-test-session-1"

    try:
        # Connect first client
        await sio1.connect("http://localhost:57575", headers={"X-Remote-User": "testuser1"})
        log.info("✓ First client (testuser1) connected")

        # Create terminal session
        await sio1.emit("create_terminal", {"session": session_id, "user": "", "path": ""})

        await asyncio.sleep(2)
        log.info("✓ Terminal session created by testuser1")

        # Disconnect first client
        await sio1.disconnect()
        log.info("✓ First client disconnected")

        await asyncio.sleep(1)

        # Reconnect as same user
        sio2 = socketio.AsyncClient()

        @sio2.event
        async def terminal_closed(data):
            if data.get("reason") == "session_already_closed":
                is_owner = data.get("is_owner", "unknown")
                log.info(f"✓ Owner detection result: {is_owner}")
                if is_owner:
                    log.info("✓ Test PASSED: Same user correctly identified as owner")
                else:
                    log.info("✗ Test FAILED: Same user should be identified as owner")
            await sio2.disconnect()

        await sio2.connect("http://localhost:57575", headers={"X-Remote-User": "testuser1"})
        log.info("✓ Second client (same user) connected")

        await sio2.emit("create_terminal", {"session": session_id, "user": "", "path": ""})

        await asyncio.sleep(2)
        await sio2.disconnect()

    except Exception as e:
        log.info(f"✗ Test failed: {e}")


async def test_different_user_scenario():
    """Test scenario where a different user tries to connect to someone else's closed session."""

    sio1 = socketio.AsyncClient()
    session_id = "owner-test-session-2"

    try:
        # Connect first client as user1
        await sio1.connect("http://localhost:57575", headers={"X-Remote-User": "testuser1"})
        log.info("✓ First client (testuser1) connected")

        # Create terminal session
        await sio1.emit("create_terminal", {"session": session_id, "user": "", "path": ""})

        await asyncio.sleep(2)
        log.info("✓ Terminal session created by testuser1")

        # Disconnect first client
        await sio1.disconnect()
        log.info("✓ First client disconnected")

        await asyncio.sleep(1)

        # Connect as different user
        sio2 = socketio.AsyncClient()

        @sio2.event
        async def terminal_closed(data):
            if data.get("reason") == "session_already_closed":
                is_owner = data.get("is_owner", "unknown")
                log.info(f"✓ Owner detection result: {is_owner}")
                if not is_owner:
                    log.info("✓ Test PASSED: Different user correctly identified as non-owner")
                else:
                    log.info("✗ Test FAILED: Different user should not be identified as owner")
            await sio2.disconnect()

        await sio2.connect("http://localhost:57575", headers={"X-Remote-User": "testuser2"})
        log.info("✓ Second client (different user) connected")

        await sio2.emit("create_terminal", {"session": session_id, "user": "", "path": ""})

        await asyncio.sleep(2)
        await sio2.disconnect()

    except Exception as e:
        log.info(f"✗ Test failed: {e}")


if __name__ == "__main__":
    log.info("Make sure Butterfly server is running on localhost:57575")
    log.info("This test will verify X-REMOTE-USER based owner detection")
    log.info("Starting test in 3 seconds...")
    time.sleep(3)

    try:
        asyncio.run(test_owner_detection())
        log.info("\n✓ Owner detection tests completed")
    except KeyboardInterrupt:
        log.info("\nTest interrupted by user")
    except Exception as e:
        log.info(f"\nTest failed: {e}")
        sys.exit(1)
