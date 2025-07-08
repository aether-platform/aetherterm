#!/usr/bin/env python3
"""
Test script to connect to socket and test AI info
"""

import asyncio
import socketio
import json


async def test_socket_ai():
    print("Connecting to socket server...")

    sio = socketio.AsyncClient()

    @sio.on("connect")
    async def on_connect():
        print("Connected to server")
        # Request AI info
        await sio.emit("ai_get_info", {})
        print("ai_get_info event sent")

    @sio.on("ai_info_response")
    async def on_ai_info_response(data):
        print("Received ai_info_response:")
        print(json.dumps(data, indent=2))
        await sio.disconnect()

    @sio.on("disconnect")
    async def on_disconnect():
        print("Disconnected from server")

    @sio.on("error")
    async def on_error(data):
        print(f"Error: {data}")

    try:
        await sio.connect("http://localhost:57575")
        await sio.wait()
    except Exception as e:
        print(f"Failed to connect: {e}")


if __name__ == "__main__":
    asyncio.run(test_socket_ai())
