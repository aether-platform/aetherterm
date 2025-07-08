#!/usr/bin/env python3
"""
Test script to verify session restoration with workspace tokens
"""

import asyncio
import socketio
import uuid
import time

async def test_session_restoration():
    # Create a workspace token that will be shared between connections
    workspace_token = f"test_workspace_{uuid.uuid4().hex[:8]}"
    
    print(f"Testing with workspace token: {workspace_token}")
    
    # First connection - create a session
    sio1 = socketio.AsyncClient()
    
    @sio1.on('connect')
    async def on_connect1():
        print("First client connected")
    
    @sio1.on('terminal_output')
    async def on_output1(data):
        session_id = data.get('session')
        output = data.get('data', '')
        print(f"Client 1 output from {session_id}: {repr(output[:50])}")
    
    terminal_created = False
    
    @sio1.on('terminal_ready')
    async def on_ready1(data):
        nonlocal terminal_created
        session_id = data.get('session')
        print(f"Client 1: Terminal ready - {session_id}")
        terminal_created = True
    
    @sio1.on('workspace_resumed')
    async def on_resumed1(data):
        print(f"Client 1: Workspace resumed - {data}")
    
    # Connect with workspace token
    await sio1.connect('http://localhost:57575', auth={'workspaceToken': workspace_token})
    await asyncio.sleep(0.5)
    
    # Create a terminal
    print("\n--- Creating initial terminal ---")
    await sio1.emit('create_terminal', {
        'session': 'test_session_1',
        'cols': 80,
        'rows': 24,
        'user': '',
        'path': ''
    })
    
    await asyncio.sleep(2)
    
    if not terminal_created:
        print("❌ ERROR: Terminal was not created!")
        await sio1.disconnect()
        return False
    
    # Send some test commands
    print("\n--- Sending test commands ---")
    await sio1.emit('terminal_input', {
        'session': 'test_session_1',
        'data': 'echo "Hello from first connection"\n'
    })
    
    await asyncio.sleep(1)
    
    await sio1.emit('terminal_input', {
        'session': 'test_session_1',
        'data': 'date\n'
    })
    
    await asyncio.sleep(1)
    
    # Disconnect first client
    print("\n--- Disconnecting first client ---")
    await sio1.disconnect()
    await asyncio.sleep(2)
    
    # Second connection - try to restore the session
    print("\n--- Connecting second client with same workspace token ---")
    sio2 = socketio.AsyncClient()
    
    session_restored = False
    
    @sio2.on('connect')
    async def on_connect2():
        print("Second client connected")
    
    @sio2.on('terminal_output')
    async def on_output2(data):
        nonlocal session_restored
        session_id = data.get('session')
        output = data.get('data', '')
        if 'Hello from first connection' in output:
            session_restored = True
            print(f"✅ Client 2: Session restored! Found previous output in {session_id}")
        else:
            print(f"Client 2 output from {session_id}: {repr(output[:50])}")
    
    @sio2.on('workspace_resumed')
    async def on_resumed2(data):
        print(f"Client 2: Workspace resumed response:")
        print(f"  - Status: {data.get('status')}")
        print(f"  - Resumed tabs: {len(data.get('resumedTabs', []))}")
        print(f"  - Created tabs: {len(data.get('createdTabs', []))}")
        
        for tab in data.get('resumedTabs', []):
            print(f"  - Tab {tab.get('tabId')}: {len(tab.get('panes', []))} panes")
            for pane in tab.get('panes', []):
                print(f"    - Pane {pane.get('paneId')}: session {pane.get('sessionId')}")
    
    # Connect with same workspace token
    await sio2.connect('http://localhost:57575', auth={'workspaceToken': workspace_token})
    await asyncio.sleep(0.5)
    
    # Try to resume workspace
    print("\n--- Attempting to resume workspace ---")
    await sio2.emit('resume_workspace', {
        'workspaceId': 'test_workspace',
        'tabs': [{
            'id': 'tab_1',
            'title': 'Terminal 1',
            'layout': 'single',
            'panes': [{
                'id': 'pane_1',
                'sessionId': 'test_session_1',
                'type': 'terminal',
                'subType': 'pure',
                'title': 'Terminal',
                'position': {'x': 0, 'y': 0, 'width': 100, 'height': 100}
            }]
        }]
    })
    
    await asyncio.sleep(2)
    
    # Also test reconnect_session directly
    print("\n--- Testing reconnect_session ---")
    
    @sio2.on('terminal_ready')
    async def on_ready2(data):
        print(f"Client 2: Terminal ready - {data}")
    
    await sio2.emit('reconnect_session', {'session': 'test_session_1'})
    
    await asyncio.sleep(2)
    
    # Verify session was restored
    if session_restored:
        print("\n✅ SUCCESS: Session was properly restored with history!")
    else:
        print("\n❌ FAILED: Session was not restored or history was lost")
    
    # Cleanup
    await sio2.disconnect()
    
    return session_restored


if __name__ == '__main__':
    success = asyncio.run(test_session_restoration())
    exit(0 if success else 1)