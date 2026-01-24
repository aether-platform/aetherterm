#!/usr/bin/env python3
"""
Test script to verify that closed sessions display CLOSED message.
"""

import asyncio
import sys
import time

import logging
import socketio

log = logging.getLogger(__name__)


async def test_closed_session():
    """Test connecting to a closed session."""

    # Create first client to establish a session
    sio1 = socketio.AsyncClient()
    session_id = "test-session-123"

    # Testing closed session handling

    try:
        # Connect first client
        await sio1.connect("http://localhost:57575")
        # First client connected

        # Create terminal session
        await sio1.emit("create_terminal", {"session": session_id, "user": "", "path": ""})

        # Wait for terminal to be ready
        await asyncio.sleep(2)
        # Terminal session created

        # Disconnect first client (this should close the session)
        await sio1.disconnect()
        # First client disconnected

        # Wait a moment for cleanup
        await asyncio.sleep(1)

        # Now try to connect second client to the same session
        sio2 = socketio.AsyncClient()

        @sio2.event
        async def terminal_closed(data):
            if data.get("reason") == "session_already_closed":
                # Second client received 'session_already_closed' message
                is_owner = data.get("is_owner", "unknown")
                # Session ownership detected as: {is_owner}
                # Test PASSED: Closed session properly detected
            else:
                log.error(f"Unexpected terminal_closed reason: {data.get('reason')}")
            await sio2.disconnect()

        @sio2.event
        async def terminal_ready(data):
            log.error("Test FAILED: Terminal should not be ready for closed session")
            await sio2.disconnect()

        await sio2.connect("http://localhost:57575")
        # Second client connected

        # Try to connect to the closed session
        await sio2.emit("create_terminal", {"session": session_id, "user": "", "path": ""})

        # Wait for response
        await asyncio.sleep(3)

        await sio2.disconnect()

    except Exception as e:
        log.error(f"Test failed with error: {e}")
        return False

    return True


if __name__ == "__main__":
    # Make sure server is running on localhost:57575
    # Starting test in 3 seconds...
    time.sleep(3)

    try:
        result = asyncio.run(test_closed_session())
        if result:
            log.info("All tests completed")
        else:
            log.error("Some tests failed")
            sys.exit(1)
    except KeyboardInterrupt:
        log.info("Test interrupted by user")
    except Exception as e:
        log.error(f"Test failed: {e}")
        sys.exit(1)
