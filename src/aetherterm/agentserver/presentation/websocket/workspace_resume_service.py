"""
Workspace Resume Service

This module contains the refactored workspace resumption logic, broken down into smaller,
more manageable functions for better maintainability and testing.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal

log = logging.getLogger(__name__)
class WorkspaceResumeService:
    """Service for handling workspace resumption with proper separation of concerns."""

    def __init__(self, sio_instance):
        self.sio_instance = sio_instance

    def validate_resume_request(
        self, data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Validate workspace resume request data."""
        workspace_id = data.get("workspaceId")
        tabs = data.get("tabs", [])

        if not workspace_id:
            return False, "workspaceId required for workspace resume", {}

        request_data = {
            "workspace_id": workspace_id,
            "tabs": tabs,
        }

        return True, None, request_data

    async def process_workspace_tabs(
        self, workspace_id: str, tabs: List[Dict[str, Any]], sid: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process all tabs in the workspace."""
        resumed_tabs = []
        created_tabs = []

        for tab_data in tabs:
            tab_id = tab_data.get("id")
            tab_title = tab_data.get("title", "Tab")
            tab_layout = tab_data.get("layout", "single")
            panes = tab_data.get("panes", [])

            if not tab_id:
                log.warning(f"Tab data missing id, skipping: {tab_data}")
                continue

            log.info(f"Processing tab {tab_id} with {len(panes)} panes")

            # Process panes in this tab
            resumed_panes, created_panes = await self.process_tab_panes(tab_data, tabs, sid)

            # Create tab result
            tab_result = {
                "tabId": tab_id,
                "title": tab_title,
                "layout": tab_layout,
                "panes": resumed_panes + created_panes,
                "status": "processed",
            }

            if resumed_panes:
                resumed_tabs.append(tab_result)
            if created_panes:
                created_tabs.append(tab_result)

        return resumed_tabs, created_tabs

    async def process_tab_panes(
        self, tab_data: Dict[str, Any], tabs: List[Dict[str, Any]], sid: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process all panes in a single tab."""
        panes = tab_data.get("panes", [])
        resumed_panes = []
        created_panes = []

        for pane_data in panes:
            pane_id = pane_data.get("id")
            session_id = pane_data.get("sessionId")
            pane_type = pane_data.get("type", "terminal")
            sub_type = pane_data.get("subType", "pure")
            pane_title = pane_data.get("title", "Terminal")
            position = pane_data.get("position", {"x": 0, "y": 0, "width": 100, "height": 100})

            if not pane_id:
                log.warning(f"Pane data missing id, skipping: {pane_data}")
                continue

            log.info(f"Processing pane {pane_id} with session {session_id}")

            # Check for existing session
            existing_session = await self.check_existing_session(session_id, sid, pane_id)
            if existing_session:
                resumed_panes.append(existing_session)
                continue

            # Create new session
            new_session = await self.create_new_session(pane_data, tab_data, tabs, sid)
            if new_session:
                created_panes.append(new_session)

        return resumed_panes, created_panes

    async def check_existing_session(
        self, session_id: str, sid: str, pane_id: str
    ) -> Optional[Dict[str, Any]]:
        """Check if session exists and can be resumed."""
        if not session_id or session_id not in AsyncioTerminal.sessions:
            log.info(f"Session {session_id} not found for pane {pane_id}, will create new")
            return None

        existing_terminal = AsyncioTerminal.sessions[session_id]
        if existing_terminal.closed:
            log.info(
                f"Session {session_id} exists but is closed for pane {pane_id}, will create new"
            )
            return None

        log.info(f"Resuming existing active terminal session {session_id} for pane {pane_id}")

        # Add client to existing terminal
        existing_terminal.client_sids.add(sid)

        # Update terminal metadata for future lookups
        # This will be set by the calling function with proper indices
        log.info(f"Terminal {session_id} exists, client should reconnect when ready")

        return {
            "paneId": pane_id,
            "sessionId": session_id,
            "status": "resumed",
            "type": "terminal",  # Could be extracted from pane_data if needed
            "subType": "pure",  # Could be extracted from pane_data if needed
            "title": "Terminal",  # Could be extracted from pane_data if needed
            "position": {"x": 0, "y": 0, "width": 100, "height": 100},  # Default
        }

    async def create_new_session(
        self,
        pane_data: Dict[str, Any],
        tab_data: Dict[str, Any],
        tabs: List[Dict[str, Any]],
        sid: str,
    ) -> Optional[Dict[str, Any]]:
        """Create a new terminal session for a pane."""
        try:
            # Extract indices for metadata
            tab_index = tabs.index(tab_data)
            pane_index = tab_data.get("panes", []).index(pane_data)

            # Set creation context for the terminal
            AsyncioTerminal._temp_creation_context = {
                "tab_index": tab_index,
                "pane_index": pane_index,
            }

            pane_id = pane_data.get("id")
            pane_type = pane_data.get("type", "terminal")
            sub_type = pane_data.get("subType", "pure")
            pane_title = pane_data.get("title", "Terminal")
            position = pane_data.get("position", {"x": 0, "y": 0, "width": 100, "height": 100})

            # Create terminal session via create_terminal
            from .terminal_creation_service import create_terminal_with_service

            terminal_data = {
                "paneId": pane_id,
                "tabId": tab_data.get("id"),
                "subType": sub_type,
                "path": pane_data.get("path", ""),
                "user": pane_data.get("user", ""),
            }

            # Call terminal creation service
            await create_terminal_with_service(
                sid=sid,
                data=terminal_data,
                sio_instance=self.sio_instance,
                config_login=False,
                config_pam_profile="",
                config_uri_root_path="",
            )

            # Find the newly created session
            # This is a bit hacky but necessary to get the session ID
            # The terminal creation service should ideally return the session ID
            new_session_id = None
            for session_id, terminal in AsyncioTerminal.sessions.items():
                if (
                    hasattr(terminal, "tab_index")
                    and hasattr(terminal, "pane_index")
                    and terminal.tab_index == tab_index
                    and terminal.pane_index == pane_index
                ):
                    new_session_id = session_id
                    break

            if not new_session_id:
                log.error(f"Failed to find newly created session for pane {pane_id}")
                return None

            log.info(f"Created new terminal session {new_session_id} for pane {pane_id}")

            return {
                "paneId": pane_id,
                "sessionId": new_session_id,
                "status": "created",
                "type": pane_type,
                "subType": sub_type,
                "title": pane_title,
                "position": position,
            }

        except Exception as e:
            log.error(f"Error creating new session for pane {pane_data.get('id')}: {e}")
            return None
        finally:
            # Clear creation context
            AsyncioTerminal._temp_creation_context = None

    async def send_workspace_resume_response(
        self,
        sid: str,
        workspace_id: str,
        resumed_tabs: List[Dict[str, Any]],
        created_tabs: List[Dict[str, Any]],
    ) -> None:
        """Send workspace resume response to client."""
        try:
            response_data = {
                "workspaceId": workspace_id,
                "resumedTabs": resumed_tabs,
                "createdTabs": created_tabs,
                "status": "completed",
                "totalTabs": len(resumed_tabs) + len(created_tabs),
            }

            await self.sio_instance.emit("workspace_resumed", response_data, room=sid)

            log.info(
                f"Workspace {workspace_id} resume complete: "
                f"{len(resumed_tabs)} resumed, {len(created_tabs)} created tabs"
            )

        except Exception as e:
            log.error(f"Error sending workspace resume response: {e}")

    async def handle_resume_error(self, sid: str, error_message: str) -> None:
        """Handle workspace resume errors and notify client."""
        try:
            await self.sio_instance.emit(
                "workspace_error",
                {"error": error_message},
                room=sid,
            )
            log.error(f"Workspace resume error for client {sid}: {error_message}")

        except Exception as e:
            log.error(f"Error handling resume error: {e}")
async def resume_workspace_with_service(sid: str, data: Dict[str, Any], sio_instance) -> None:
    """
    Main entry point for workspace resumption using the service.
    This replaces the original monolithic resume_workspace function.
    """
    service = WorkspaceResumeService(sio_instance)

    try:
        # Step 1: Validate request
        is_valid, error_msg, request_data = service.validate_resume_request(data)
        if not is_valid:
            await service.handle_resume_error(sid, error_msg)
            return

        workspace_id = request_data["workspace_id"]
        tabs = request_data["tabs"]

        log.info(
            f"Resume workspace request for workspace {workspace_id} with {len(tabs)} tabs from client {sid}"
        )

        # Step 2: Process workspace tabs
        resumed_tabs, created_tabs = await service.process_workspace_tabs(workspace_id, tabs, sid)

        # Step 3: Send response
        await service.send_workspace_resume_response(sid, workspace_id, resumed_tabs, created_tabs)

    except Exception as e:
        error_msg = f"Unexpected error in workspace resumption: {str(e)}"
        log.error(error_msg)
        await service.handle_resume_error(sid, error_msg)
