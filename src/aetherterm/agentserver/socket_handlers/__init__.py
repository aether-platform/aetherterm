"""
Socket.IO event handlers for AetherTerm AgentServer.

This package splits handlers by concern:
- terminal_handlers: Terminal connection, I/O, and lifecycle
- ai_handlers: AI chat and command analysis
- session_handlers: Wrapper session synchronization
- blocker_handlers: Session block/unblock operations
"""

from .ai_handlers import ai_chat_message, ai_get_info, ai_terminal_analysis
from .blocker_handlers import get_block_status, unblock_request
from .helpers import set_sio_instance
from .session_handlers import get_wrapper_sessions, wrapper_session_sync
from .terminal_handlers import (
    broadcast_to_session,
    connect,
    create_terminal,
    disconnect,
    terminal_input,
    terminal_resize,
)

__all__ = [
    "ai_chat_message",
    "ai_get_info",
    "ai_terminal_analysis",
    "broadcast_to_session",
    "connect",
    "create_terminal",
    "disconnect",
    "get_block_status",
    "get_wrapper_sessions",
    "set_sio_instance",
    "terminal_input",
    "terminal_resize",
    "unblock_request",
    "wrapper_session_sync",
]
