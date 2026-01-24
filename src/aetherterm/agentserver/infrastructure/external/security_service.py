"""
Security Service - Infrastructure Layer

Automatic blocking system for security and compliance.
"""

import logging
from typing import Any, Dict, List

log = logging.getLogger("aetherterm.infrastructure.security")
class SecurityService:
    """Automatic blocking system for security and compliance."""

    def __init__(self):
        self.blocked_commands: List[str] = []
        self.blocked_patterns: List[str] = []
        self.sio_instance = None

    def set_socket_io_instance(self, sio):
        """Set Socket.IO instance for notifications."""
        self.sio_instance = sio

    async def check_command(self, command: str, session_id: str) -> Dict[str, Any]:
        """Check if command should be blocked."""
        # Simple pattern matching (extend as needed)
        dangerous_patterns = ["rm -rf /", ":(){ :|:& };:", "sudo dd if="]

        for pattern in dangerous_patterns:
            if pattern in command:
                await self._block_session(session_id, f"Dangerous command detected: {pattern}")
                return {
                    "blocked": True,
                    "reason": f"Command contains dangerous pattern: {pattern}",
                    "block_type": "auto_detected",
                }

        return {"blocked": False}

    async def _block_session(self, session_id: str, reason: str):
        """Block a session and notify."""
        if self.sio_instance:
            await self.sio_instance.emit(
                "session_blocked", {"session_id": session_id, "reason": reason, "timestamp": "now"}
            )
