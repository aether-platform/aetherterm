"""
Terminal Handler - Endpoint Layer

Simplified WebSocket handler that delegates to domain services.
This handler only deals with socket communication, not business logic.
"""

import logging
from typing import Dict, Any, Optional

from aetherterm.agentserver.domain.services.terminal_session_service import TerminalSessionService
from aetherterm.agentserver.domain.services.workspace_token_service import get_workspace_token_service

log = logging.getLogger(__name__)


class TerminalHandler:
    """Handles terminal-related WebSocket events."""
    
    def __init__(self, sio_instance, terminal_service: TerminalSessionService):
        self.sio = sio_instance
        self.terminal_service = terminal_service
        self.token_service = get_workspace_token_service()
    
    async def handle_create_terminal(self, sid: str, data: Dict[str, Any]) -> None:
        """Handle terminal creation request."""
        try:
            # Extract parameters
            session_id = data.get("session", f"terminal_{sid}")
            user_name = data.get("user", "")
            path = data.get("path", "~")
            rows = data.get("rows", 24)
            cols = data.get("cols", 80)
            
            # Check for existing session from same workspace
            existing_session_id = await self._find_existing_session(sid, session_id)
            if existing_session_id:
                session_id = existing_session_id
            
            # Check if session already exists
            existing_session = await self.terminal_service.get_session(session_id)
            if existing_session:
                # Add client to existing session
                self.terminal_service.add_client(session_id, sid)
                
                # Send buffer content
                buffer_content = self.terminal_service.get_buffer_content(session_id)
                if buffer_content:
                    await self.sio.emit(
                        "terminal_output",
                        {"session": session_id, "data": buffer_content},
                        room=sid
                    )
                
                await self.sio.emit(
                    "terminal_ready",
                    {"session": session_id, "status": "resumed"},
                    room=sid
                )
                return
            
            # Create new session
            session = await self.terminal_service.create_session(
                session_id=session_id,
                user_name=user_name,
                path=path,
                rows=rows,
                cols=cols
            )
            
            # Add client
            self.terminal_service.add_client(session_id, sid)
            
            # Set callbacks
            self.terminal_service.set_output_callback(
                session_id,
                lambda sid, data: self._handle_output(sid, session_id, data)
            )
            
            self.terminal_service.set_close_callback(
                session_id,
                lambda sid: self._handle_close(sid, session_id)
            )
            
            # Notify client
            await self.sio.emit(
                "terminal_ready",
                {"session": session_id, "status": "created"},
                room=sid
            )
            
        except Exception as e:
            log.error(f"Error creating terminal: {e}")
            await self.sio.emit(
                "terminal_error",
                {"error": str(e)},
                room=sid
            )
    
    async def handle_terminal_input(self, sid: str, data: Dict[str, Any]) -> None:
        """Handle terminal input."""
        try:
            session_id = data.get("session")
            input_data = data.get("data", "")
            
            if not session_id:
                return
            
            # Write to terminal
            success = await self.terminal_service.write_to_session(session_id, input_data)
            
            if not success:
                await self.sio.emit(
                    "terminal_error",
                    {"error": "Session not found or closed"},
                    room=sid
                )
                
        except Exception as e:
            log.error(f"Error handling terminal input: {e}")
    
    async def handle_terminal_resize(self, sid: str, data: Dict[str, Any]) -> None:
        """Handle terminal resize."""
        try:
            session_id = data.get("session")
            rows = data.get("rows", 24)
            cols = data.get("cols", 80)
            
            if not session_id:
                return
            
            # Resize terminal
            await self.terminal_service.resize_session(session_id, rows, cols)
            
        except Exception as e:
            log.error(f"Error resizing terminal: {e}")
    
    async def handle_disconnect(self, sid: str) -> None:
        """Handle client disconnect."""
        try:
            # Remove client from all sessions
            for session_id, session in self.terminal_service.get_all_sessions().items():
                if sid in session.client_sids:
                    self.terminal_service.remove_client(session_id, sid)
                    
                    # If no clients remain, schedule session closure
                    if not session.client_sids:
                        # TODO: Implement delayed closure
                        pass
            
        except Exception as e:
            log.error(f"Error handling disconnect: {e}")
    
    async def _find_existing_session(self, sid: str, requested_session_id: str) -> Optional[str]:
        """Find existing session from same workspace token."""
        workspace_token = self.token_service.get_token_for_socket(sid)
        if not workspace_token:
            return None
        
        # Get other sockets with same token
        token_sockets = self.token_service.get_sockets_for_token(workspace_token)
        token_sockets.discard(sid)
        
        # Check their sessions
        for other_sid in token_sockets:
            for session_id, session in self.terminal_service.get_all_sessions().items():
                if other_sid in session.client_sids and not session.closed:
                    # Found a session from same workspace
                    return session_id
        
        return None
    
    async def _handle_output(self, sid: str, session_id: str, data: str) -> None:
        """Handle terminal output."""
        session = await self.terminal_service.get_session(session_id)
        if not session:
            return
        
        # Broadcast to all clients
        for client_sid in session.client_sids:
            await self.sio.emit(
                "terminal_output",
                {"session": session_id, "data": data},
                room=client_sid
            )
    
    async def _handle_close(self, sid: str, session_id: str) -> None:
        """Handle terminal close."""
        session = await self.terminal_service.get_session(session_id)
        if not session:
            return
        
        # Notify all clients
        for client_sid in session.client_sids:
            await self.sio.emit(
                "terminal_closed",
                {"session": session_id},
                room=client_sid
            )