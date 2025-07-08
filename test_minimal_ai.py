#!/usr/bin/env python3
"""
Minimal test to check AI service
"""

import asyncio
import socketio
import json
import os
import sys

sys.path.append("src")


async def test_minimal():
    print("Testing AI service directly...")

    # Test DI container first
    print("\n1. Testing DI container:")
    print(f"AI_PROVIDER env: {os.getenv('AI_PROVIDER', 'NOT SET')}")
    print(f"LMSTUDIO_URL env: {os.getenv('LMSTUDIO_URL', 'NOT SET')}")

    from aetherterm.agentserver.infrastructure.config.di_container import get_container

    container = get_container()
    ai_service = container.infrastructure.ai_service()

    print(f"AI Provider: {ai_service.provider}")
    print(f"AI Model: {ai_service.model}")
    print(f"LMStudio URL: {ai_service.lmstudio_url}")

    available = await ai_service.is_available()
    print(f"AI Available: {available}")

    print("\n2. Testing socket connection:")
    sio = socketio.AsyncClient(logger=True, engineio_logger=True)

    responses = []

    @sio.on("connect")
    async def on_connect():
        print("✅ Socket connected")
        await asyncio.sleep(0.5)
        print("📤 Sending ai_get_info...")
        await sio.emit("ai_get_info", {})

    @sio.on("ai_info_response")
    async def on_ai_info_response(data):
        print("✅ Got ai_info_response:")
        print(json.dumps(data, indent=2))
        responses.append(data)

    @sio.on("*")
    async def catch_all(event, data):
        print(f"📨 Event '{event}': {data}")

    try:
        await sio.connect("http://localhost:57575", wait_timeout=5)
        await asyncio.sleep(3)
        await sio.disconnect()

        if responses:
            print("\n✅ Test passed! Got response.")
        else:
            print("\n❌ Test failed! No response received.")

    except Exception as e:
        print(f"❌ Connection error: {e}")


if __name__ == "__main__":
    # Set environment variables for test
    os.environ["AI_PROVIDER"] = "lmstudio"
    os.environ["LMSTUDIO_URL"] = "http://192.168.210.218:1234"

    asyncio.run(test_minimal())
