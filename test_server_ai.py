#!/usr/bin/env python3
"""
Test what AI provider the running server is actually using
"""

import asyncio
import socketio
import json


async def test_server():
    print("Testing running server's AI configuration...")

    sio = socketio.AsyncClient()
    responses = []

    @sio.on("connect")
    async def on_connect():
        print("✅ Connected to server")
        await sio.emit("ai_get_info", {})

    @sio.on("ai_info_response")
    async def on_ai_info_response(data):
        print("\n📨 Server AI Info Response:")
        print(json.dumps(data, indent=2))
        responses.append(data)

    @sio.on("error")
    async def on_error(data):
        print(f"❌ Error: {data}")

    try:
        await sio.connect("http://localhost:57575")
        await asyncio.sleep(2)
        await sio.disconnect()

        if responses:
            info = responses[0]
            print(f"\n🔍 Analysis:")
            print(f"Provider: {info.get('provider')} (expected: lmstudio)")
            print(f"Available: {info.get('available')}")
            print(f"Status: {info.get('status')}")

            if info.get("provider") != "lmstudio":
                print("\n⚠️  Server is NOT using LMStudio provider!")
                print("This means environment variables are not being applied correctly.")
            else:
                print("\n✅ Server is correctly using LMStudio provider!")

    except Exception as e:
        print(f"❌ Connection error: {e}")


if __name__ == "__main__":
    asyncio.run(test_server())
