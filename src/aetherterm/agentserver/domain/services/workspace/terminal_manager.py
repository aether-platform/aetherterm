"""
Terminal Manager - Application Service Component

Focused service for terminal lifecycle management within workspaces.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import uuid4

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
# ValidationService removed - using direct validation instead

log = logging.getLogger("aetherterm.services.terminal_manager")


class TerminalManager:
    """
    Focused terminal lifecycle management service.

    Handles:
    - Terminal creation and initialization
    - Terminal session management
    - Terminal configuration and settings
    - Terminal cleanup and resource management
    """

    def __init__(self):
        self._terminals = {}  # session_id -> terminal instance
        self._terminal_configs = {}  # session_id -> config
        self._terminal_metadata = {}  # session_id -> metadata

    async def create_terminal(
        self,
        session_id: str,
        cols: int = 80,
        rows: int = 24,
        shell: Optional[str] = None,
        working_directory: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create a new terminal session."""
        try:
            # Validate inputs
            if session_id in self._terminals:
                log.warning(f"Terminal session {session_id} already exists")
                return {"success": False, "error": "Session already exists"}

            # Validate terminal dimensions
            if not (10 <= cols <= 300) or not (5 <= rows <= 100):
                return {"success": False, "error": "Invalid terminal dimensions"}

            # Create terminal configuration
            config = {
                "cols": cols,
                "rows": rows,
                "shell": shell or "/bin/bash",
                "working_directory": working_directory or "/",
                "environment": environment or {},
                "created_at": datetime.utcnow(),
                "last_activity": datetime.utcnow(),
            }

            # Create terminal instance
            terminal = AsyncioTerminal(
                cols=cols,
                rows=rows,
                shell=config["shell"],
                cwd=config["working_directory"],
                env=config["environment"],
            )

            # Initialize terminal
            await terminal.initialize()

            # Store terminal and metadata
            self._terminals[session_id] = terminal
            self._terminal_configs[session_id] = config
            self._terminal_metadata[session_id] = {
                "session_id": session_id,
                "status": "active",
                "pid": terminal.process.pid if terminal.process else None,
                "created_at": config["created_at"],
                "last_activity": config["last_activity"],
                "command_count": 0,
                "total_output_bytes": 0,
            }

            log.info(f"Created terminal session {session_id}")

            return {
                "success": True,
                "session_id": session_id,
                "config": config,
                "metadata": self._terminal_metadata[session_id],
            }

        except Exception as e:
            log.error(f"Failed to create terminal {session_id}: {e}")
            return {"success": False, "error": str(e)}

    async def get_terminal(self, session_id: str) -> Optional[AsyncioTerminal]:
        """Get terminal instance by session ID."""
        return self._terminals.get(session_id)

    async def send_input(self, session_id: str, input_data: str) -> bool:
        """Send input to terminal session."""
        try:
            terminal = self._terminals.get(session_id)
            if not terminal:
                log.warning(f"Terminal session {session_id} not found")
                return False

            # Basic input validation
            if not input_data or len(input_data) > 10000:
                log.warning(f"Invalid input rejected for session {session_id}")
                return False

            # Send input to terminal
            await terminal.write(input_data)

            # Update metadata
            if session_id in self._terminal_metadata:
                self._terminal_metadata[session_id]["last_activity"] = datetime.utcnow()
                self._terminal_metadata[session_id]["command_count"] += 1

            return True

        except Exception as e:
            log.error(f"Failed to send input to terminal {session_id}: {e}")
            return False

    async def resize_terminal(self, session_id: str, cols: int, rows: int) -> bool:
        """Resize terminal session."""
        try:
            terminal = self._terminals.get(session_id)
            if not terminal:
                return False

            # Validate dimensions
            if not (10 <= cols <= 300) or not (5 <= rows <= 100):
                log.warning(f"Invalid resize dimensions: {cols}x{rows}")
                return False

            # Resize terminal
            await terminal.resize(cols, rows)

            # Update configuration
            if session_id in self._terminal_configs:
                self._terminal_configs[session_id]["cols"] = cols
                self._terminal_configs[session_id]["rows"] = rows
                self._terminal_configs[session_id]["last_activity"] = datetime.utcnow()

            log.debug(f"Resized terminal {session_id} to {cols}x{rows}")
            return True

        except Exception as e:
            log.error(f"Failed to resize terminal {session_id}: {e}")
            return False

    async def get_terminal_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed status of terminal session."""
        try:
            if session_id not in self._terminals:
                return None

            terminal = self._terminals[session_id]
            config = self._terminal_configs.get(session_id, {})
            metadata = self._terminal_metadata.get(session_id, {})

            status = {
                "session_id": session_id,
                "active": terminal.is_alive() if hasattr(terminal, "is_alive") else True,
                "pid": terminal.process.pid
                if hasattr(terminal, "process") and terminal.process
                else None,
                "dimensions": {"cols": config.get("cols", 80), "rows": config.get("rows", 24)},
                "shell": config.get("shell"),
                "working_directory": config.get("working_directory"),
                "created_at": config.get("created_at"),
                "last_activity": metadata.get("last_activity"),
                "command_count": metadata.get("command_count", 0),
                "total_output_bytes": metadata.get("total_output_bytes", 0),
            }

            return status

        except Exception as e:
            log.error(f"Failed to get terminal status for {session_id}: {e}")
            return None

    async def terminate_terminal(self, session_id: str, force: bool = False) -> bool:
        """Terminate a terminal session."""
        try:
            terminal = self._terminals.get(session_id)
            if not terminal:
                log.warning(f"Terminal session {session_id} not found for termination")
                return False

            # Terminate terminal process
            if hasattr(terminal, "terminate"):
                await terminal.terminate(force=force)
            elif hasattr(terminal, "close"):
                await terminal.close()

            # Clean up stored data
            self._terminals.pop(session_id, None)
            self._terminal_configs.pop(session_id, None)
            self._terminal_metadata.pop(session_id, None)

            log.info(f"Terminated terminal session {session_id}")
            return True

        except Exception as e:
            log.error(f"Failed to terminate terminal {session_id}: {e}")
            return False

    async def list_terminals(self) -> List[Dict[str, Any]]:
        """List all active terminal sessions."""
        try:
            terminals = []

            for session_id in self._terminals.keys():
                status = await self.get_terminal_status(session_id)
                if status:
                    terminals.append(status)

            return terminals

        except Exception as e:
            log.error(f"Failed to list terminals: {e}")
            return []

    async def cleanup_inactive_terminals(self, max_idle_hours: int = 24) -> int:
        """Clean up terminals that have been inactive for too long."""
        try:
            from datetime import timedelta

            cutoff_time = datetime.utcnow() - timedelta(hours=max_idle_hours)
            terminated_count = 0

            # Find inactive terminals
            inactive_sessions = []
            for session_id, metadata in self._terminal_metadata.items():
                last_activity = metadata.get("last_activity")
                if last_activity and last_activity < cutoff_time:
                    inactive_sessions.append(session_id)

            # Terminate inactive terminals
            for session_id in inactive_sessions:
                if await self.terminate_terminal(session_id):
                    terminated_count += 1

            if terminated_count > 0:
                log.info(f"Cleaned up {terminated_count} inactive terminals")

            return terminated_count

        except Exception as e:
            log.error(f"Failed to cleanup inactive terminals: {e}")
            return 0

    async def get_terminal_metrics(self) -> Dict[str, Any]:
        """Get aggregate metrics for all terminals."""
        try:
            total_terminals = len(self._terminals)
            active_terminals = 0
            total_commands = 0
            total_output_bytes = 0

            for metadata in self._terminal_metadata.values():
                if metadata.get("status") == "active":
                    active_terminals += 1
                total_commands += metadata.get("command_count", 0)
                total_output_bytes += metadata.get("total_output_bytes", 0)

            return {
                "total_terminals": total_terminals,
                "active_terminals": active_terminals,
                "inactive_terminals": total_terminals - active_terminals,
                "total_commands_executed": total_commands,
                "total_output_bytes": total_output_bytes,
                "average_commands_per_terminal": total_commands / total_terminals
                if total_terminals > 0
                else 0,
            }

        except Exception as e:
            log.error(f"Failed to get terminal metrics: {e}")
            return {}

    async def export_terminal_config(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Export terminal configuration for backup or migration."""
        try:
            config = self._terminal_configs.get(session_id)
            metadata = self._terminal_metadata.get(session_id)

            if not config:
                return None

            return {
                "session_id": session_id,
                "config": config,
                "metadata": metadata,
                "exported_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            log.error(f"Failed to export terminal config for {session_id}: {e}")
            return None
