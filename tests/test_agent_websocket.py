import asyncio
import json
import logging

import websockets

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test_agent")


async def test_agent_flow():
    uri = "ws://localhost:57575/ws/agent/test-agent-001"
    async with websockets.connect(uri) as websocket:
        log.info("Connected to AgentServer")

        # 1. Create a PTY session
        pty_id = "test-pty-1"
        await websocket.send(json.dumps({"type": "pty_create", "payload": {"pty_id": pty_id}}))
        log.info(f"Sent pty_create for {pty_id}")
        await asyncio.sleep(1)

        # 2. Start observing the PTY
        await websocket.send(json.dumps({"type": "observe_pty", "payload": {"pty_id": pty_id}}))
        log.info(f"Sent observe_pty for {pty_id}")

        # 3. Execute a command
        cmd = "echo 'Hello from LLM Agent!'; uname -a"
        await websocket.send(
            json.dumps({"type": "command_execute", "payload": {"pty_id": pty_id, "command": cmd}})
        )
        log.info(f"Sent command_execute: {cmd}")

        # 4. Listen for output
        log.info("Waiting for output...")
        try:
            while True:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                msg = json.loads(response)
                log.info(f"Received from server: {msg}")
                if msg.get("type") == "terminal_output" and "Hello" in msg.get("data", ""):
                    log.info("SUCCESS: Received expected terminal output!")
                    break
        except asyncio.TimeoutError:
            log.error("FAILED: Timeout waiting for output")

        # 5. List sessions
        await websocket.send(json.dumps({"type": "list_sessions"}))
        response = await websocket.recv()
        log.info(f"Session list: {json.loads(response)}")


if __name__ == "__main__":
    asyncio.run(test_agent_flow())
