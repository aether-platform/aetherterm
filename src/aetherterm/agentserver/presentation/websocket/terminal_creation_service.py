"""
Terminal Creation Service

This module contains the refactored terminal creation logic, broken down into smaller,
more manageable functions for better maintainability and testing.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from uuid import uuid4

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal

log = logging.getLogger(__name__)


class TerminalCreationService:
    """Service for handling terminal creation with proper separation of concerns."""

    def __init__(self, sio_instance, config_login: bool = False, config_pam_profile: str = "", config_uri_root_path: str = ""):
        self.sio_instance = sio_instance
        self.config_login = config_login
        self.config_pam_profile = config_pam_profile
        self.config_uri_root_path = config_uri_root_path

    async def validate_user_permissions(self, sid: str) -> bool:
        """Validate if user has permission to create terminals."""
        try:
            from aetherterm.agentserver.domain.services.global_workspace_service import (
                get_global_workspace_service,
            )

            global_service = get_global_workspace_service()

            if not global_service.can_user_modify(sid):
                log.warning(f"User {sid} (Viewer) attempted to create terminal")
                await self.sio_instance.emit(
                    "terminal_error", {"error": "Viewers cannot create terminals"}, room=sid
                )
                return False
            return True
        except Exception as e:
            log.error(f"Error validating user permissions: {e}")
            return False

    def extract_terminal_request_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and validate terminal creation request data."""
        return {
            "session_id": data.get("session", str(uuid4())),
            "user_name": data.get("user", ""),
            "path": data.get("path", ""),
            "launch_mode": data.get("launch_mode", "default"),
            "agent_config": data.get("agent_config", {}),
            "agent_type": data.get("agent_config", {}).get("agent_type"),
            "requester_agent_id": data.get("requester_agent_id"),
            "pane_id": data.get("paneId"),
            "tab_id": data.get("tabId"),
            "is_specific_session_request": "session" in data and data["session"] != "",
        }

    async def check_existing_session(self, session_id: str, sid: str) -> Optional[AsyncioTerminal]:
        """Check if terminal session already exists and handle accordingly."""
        try:
            if session_id in AsyncioTerminal.sessions:
                existing_terminal = AsyncioTerminal.sessions[session_id]
                
                if not existing_terminal.closed:
                    log.info(f"Adding client {sid} to existing terminal session {session_id}")
                    existing_terminal.client_sids.add(sid)
                    
                    await self.sio_instance.emit(
                        "terminal_ready",
                        {"session": session_id, "status": "connected"},
                        room=sid,
                    )
                    return existing_terminal
                else:
                    log.info(f"Existing session {session_id} is closed, creating new one")
                    # Clean up closed session
                    del AsyncioTerminal.sessions[session_id]
            
            return None
        except Exception as e:
            log.error(f"Error checking existing session {session_id}: {e}")
            return None

    def setup_agent_configuration(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Setup agent configuration based on request data."""
        agent_config = {
            "launch_mode": request_data["launch_mode"],
            "agent_type": request_data["agent_type"],
            "requester_agent_id": request_data["requester_agent_id"],
            "auto_start_agent": request_data["launch_mode"] == "agent" and request_data["agent_type"],
        }
        
        # Add agent-specific configuration
        if agent_config["auto_start_agent"]:
            agent_config.update({
                "agent_command_template": self._get_agent_command_template(request_data["agent_type"]),
                "agent_env_vars": self._get_agent_environment_variables(request_data["agent_type"]),
            })
        
        return agent_config

    def _get_agent_command_template(self, agent_type: str) -> str:
        """Get command template for specific agent type."""
        templates = {
            "developer": "python -m aetherterm.agentshell.main --agent-type=developer",
            "reviewer": "python -m aetherterm.agentshell.main --agent-type=reviewer",
            "tester": "python -m aetherterm.agentshell.main --agent-type=tester",
            "architect": "python -m aetherterm.agentshell.main --agent-type=architect",
            "researcher": "python -m aetherterm.agentshell.main --agent-type=researcher",
        }
        return templates.get(agent_type, "bash")

    def _get_agent_environment_variables(self, agent_type: str) -> Dict[str, str]:
        """Get environment variables for specific agent type."""
        base_env = {
            "AETHER_AGENT_TYPE": agent_type,
            "AETHER_AGENT_MODE": "terminal",
        }
        
        # Add agent-specific environment variables
        if agent_type == "developer":
            base_env.update({
                "AETHER_DEV_MODE": "true",
                "AETHER_AUTO_COMPLETE": "true",
            })
        elif agent_type == "tester":
            base_env.update({
                "AETHER_TEST_MODE": "true",
                "AETHER_AUTO_TEST": "true",
            })
        
        return base_env

    async def create_terminal_instance(
        self, 
        session_id: str, 
        sid: str, 
        request_data: Dict[str, Any], 
        agent_config: Dict[str, Any]
    ) -> Tuple[bool, Optional[AsyncioTerminal], Optional[str]]:
        """Create new terminal instance with configuration."""
        try:
            # Determine startup command
            if agent_config["auto_start_agent"]:
                startup_command = agent_config["agent_command_template"]
                env_vars = agent_config["agent_env_vars"]
            else:
                startup_command = None
                env_vars = {}

            # Create terminal instance
            terminal = AsyncioTerminal(
                session_id=session_id,
                client_sids={sid},
                path=request_data["path"],
                user=request_data["user_name"],
                login=self.config_login,
                pam_profile=self.config_pam_profile,
                uri_root_path=self.config_uri_root_path,
                pane_id=request_data["pane_id"],
                tab_id=request_data["tab_id"],
                startup_command=startup_command,
                env_vars=env_vars,
            )

            # Store terminal session
            AsyncioTerminal.sessions[session_id] = terminal
            
            log.info(f"Created terminal session {session_id} for client {sid}")
            return True, terminal, None

        except Exception as e:
            error_msg = f"Failed to create terminal: {str(e)}"
            log.error(error_msg)
            return False, None, error_msg

    async def handle_agent_autostart(self, terminal: AsyncioTerminal, agent_config: Dict[str, Any]) -> None:
        """Handle automatic agent startup after terminal creation."""
        if not agent_config.get("auto_start_agent"):
            return

        try:
            log.info(f"Auto-starting agent {agent_config['agent_type']} for session {terminal.session_id}")
            
            # Agent will be started automatically by the startup_command in the terminal
            # Additional agent-specific initialization can be added here
            
            await self.sio_instance.emit(
                "agent_autostart",
                {
                    "session": terminal.session_id,
                    "agent_type": agent_config["agent_type"],
                    "status": "starting",
                },
                room=terminal.session_id,
            )
            
        except Exception as e:
            log.error(f"Error in agent autostart for session {terminal.session_id}: {e}")

    async def send_terminal_ready_response(self, terminal: AsyncioTerminal, sid: str) -> None:
        """Send terminal ready response to client."""
        try:
            response_data = {
                "session": terminal.session_id,
                "cols": terminal.cols,
                "rows": terminal.rows,
                "status": "ready",
            }
            
            await self.sio_instance.emit("terminal_ready", response_data, room=sid)
            log.info(f"Terminal {terminal.session_id} ready notification sent to client {sid}")
            
        except Exception as e:
            log.error(f"Error sending terminal ready response: {e}")

    async def handle_creation_error(self, sid: str, error_message: str) -> None:
        """Handle terminal creation errors and notify client."""
        try:
            await self.sio_instance.emit(
                "terminal_error",
                {"error": error_message},
                room=sid,
            )
            log.error(f"Terminal creation error for client {sid}: {error_message}")
            
        except Exception as e:
            log.error(f"Error handling creation error: {e}")


async def create_terminal_with_service(
    sid: str,
    data: Dict[str, Any],
    sio_instance,
    config_login: bool = False,
    config_pam_profile: str = "",
    config_uri_root_path: str = "",
) -> None:
    """
    Main entry point for terminal creation using the service.
    This replaces the original monolithic create_terminal function.
    """
    service = TerminalCreationService(
        sio_instance, config_login, config_pam_profile, config_uri_root_path
    )
    
    try:
        # Step 1: Validate user permissions
        if not await service.validate_user_permissions(sid):
            return

        # Step 2: Extract and validate request data
        request_data = service.extract_terminal_request_data(data)
        session_id = request_data["session_id"]

        log.info(f"Creating terminal session {session_id} for client {sid}")

        # Step 3: Check for existing session
        existing_terminal = await service.check_existing_session(session_id, sid)
        if existing_terminal:
            return  # Already handled in check_existing_session

        # Step 4: Setup agent configuration
        agent_config = service.setup_agent_configuration(request_data)

        # Step 5: Create terminal instance
        success, terminal, error_msg = await service.create_terminal_instance(
            session_id, sid, request_data, agent_config
        )

        if not success:
            await service.handle_creation_error(sid, error_msg or "Unknown error")
            return

        # Step 6: Handle agent autostart (if configured)
        await service.handle_agent_autostart(terminal, agent_config)

        # Step 7: Send ready response
        await service.send_terminal_ready_response(terminal, sid)

    except Exception as e:
        error_msg = f"Unexpected error in terminal creation: {str(e)}"
        log.error(error_msg)
        await service.handle_creation_error(sid, error_msg)