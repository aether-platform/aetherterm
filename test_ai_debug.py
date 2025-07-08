#!/usr/bin/env python3
"""
Debug AI service connection issue
"""

import asyncio
import socketio
import json


async def test_ai_debug():
    print("Starting AI debug test...")

    sio = socketio.AsyncClient()

    @sio.on("connect")
    async def on_connect():
        print("✅ Connected to server")
        print("📤 Sending ai_get_info event...")
        await sio.emit("ai_get_info", {})

    @sio.on("ai_info_response")
    async def on_ai_info_response(data):
        print("✅ Received ai_info_response:")
        print(json.dumps(data, indent=2))
        await sio.disconnect()

    @sio.on("ai_info")
    async def on_ai_info(data):
        print("⚠️  Received ai_info (wrong event name):")
        print(json.dumps(data, indent=2))
        await sio.disconnect()

    @sio.on("error")
    async def on_error(data):
        print(f"❌ Error: {data}")
        await sio.disconnect()

    @sio.on("disconnect")
    async def on_disconnect():
        print("🔌 Disconnected from server")

    try:
        await sio.connect("http://localhost:57575", wait_timeout=10)
        # Wait for response
        await asyncio.sleep(5)
        if sio.connected:
            print("⏱️  Timeout - no response received")
            await sio.disconnect()
    except Exception as e:
        print(f"❌ Failed to connect: {e}")


if __name__ == "__main__":
    asyncio.run(test_ai_debug())
