#!/usr/bin/env python3
"""Test tab persistence in workspace management service."""

import socketio
import asyncio
import json
import time

# Create a Socket.IO client
sio = socketio.AsyncClient()

# Store workspace token
workspace_token = None
workspace_id = None
socket_id = None


@sio.on("connect")
async def on_connect():
    global socket_id
    socket_id = sio.get_sid()
    print(f"Connected with socket ID: {socket_id}")

    # Set workspace token
    await sio.emit("set_workspace_token", {"token": "test-token-123"})
    print("Set workspace token")


@sio.on("workspace_token_set")
async def on_workspace_token_set(data):
    print(f"Workspace token set: {data}")

    # List workspaces
    await sio.emit("workspace_list", {})


@sio.on("workspace_list_data")
async def on_workspace_list(data):
    global workspace_id
    print(f"Workspace list: {json.dumps(data, indent=2)}")

    if data["workspaces"]:
        # Use first workspace
        workspace_id = data["workspaces"][0]["id"]
        print(f"Using workspace: {workspace_id}")

        # Get workspace details
        await sio.emit("workspace_get", {"workspaceId": workspace_id})
    else:
        # Create new workspace
        await sio.emit("workspace_create", {"name": "Test Workspace"})


@sio.on("workspace_created")
async def on_workspace_created(data):
    global workspace_id
    print(f"Workspace created: {json.dumps(data, indent=2)}")
    workspace_id = data["workspace"]["id"]

    # Create a tab
    await create_tab()


@sio.on("workspace_data")
async def on_workspace_data(data):
    print(f"Workspace data: {json.dumps(data, indent=2)}")

    if data["workspace"]:
        tabs = data["workspace"].get("tabs", [])
        print(f"Found {len(tabs)} tabs")

        if not tabs:
            # Create a tab
            await create_tab()
        else:
            print("Tabs already exist - persistence is working!")

            # Update workspace to test update functionality
            await update_workspace(data["workspace"])


async def create_tab():
    print(f"Creating tab in workspace {workspace_id}")
    await sio.emit(
        "tab_create",
        {
            "workspaceId": workspace_id,
            "title": f"Test Tab {int(time.time())}",
            "type": "terminal",
            "subType": "pure",
        },
    )


@sio.on("tab_created")
async def on_tab_created(data):
    print(f"Tab created: {json.dumps(data, indent=2)}")

    # Update workspace to save the tab
    await sio.emit(
        "workspace_update",
        {
            "workspaceId": workspace_id,
            "workspaceData": {"name": "Test Workspace Updated", "tabs": [data["tab"]]},
        },
    )


async def update_workspace(workspace):
    print("Updating workspace...")
    await sio.emit(
        "workspace_update",
        {
            "workspaceId": workspace_id,
            "workspaceData": {"name": f"Updated at {int(time.time())}", "tabs": workspace["tabs"]},
        },
    )


@sio.on("workspace_updated")
async def on_workspace_updated(data):
    print(f"Workspace updated: {json.dumps(data, indent=2)}")

    # Disconnect and reconnect to test persistence
    print("Disconnecting to test persistence...")
    await sio.disconnect()

    # Wait a bit
    await asyncio.sleep(2)

    # Reconnect
    print("Reconnecting...")
    await sio.connect("ws://localhost:57575")


@sio.on("workspace_error")
async def on_error(data):
    print(f"Error: {data}")


@sio.on("disconnect")
async def on_disconnect():
    print("Disconnected")


async def main():
    # Connect to the server
    await sio.connect("ws://localhost:57575")

    # Keep the client running
    await asyncio.sleep(30)

    # Disconnect
    await sio.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
