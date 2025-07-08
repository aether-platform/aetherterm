"""
Global Workspace Service

Manages a single shared workspace for all users.
All users (including Viewers) connect to the same workspace.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from uuid import uuid4

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal

log = logging.getLogger(__name__)


class GlobalWorkspaceService:
    """Manages a single global workspace shared by all users."""

    # Configuration constants
    MAX_TABS = 20  # Maximum tabs in the global workspace
    MAX_PANES_PER_TAB = 4  # Maximum panes per tab

    # Default workspace ID
    GLOBAL_WORKSPACE_ID = "global_workspace"

    def __init__(self):
        # The single global workspace
        self._workspace: Dict[str, Any] = {
            "id": self.GLOBAL_WORKSPACE_ID,
            "name": "Shared Workspace",
            "tabs": [],
            "activeTabId": None,
            "lastAccessed": datetime.now().isoformat(),
            "layout": {"type": "default", "configuration": {}},
        }

        # Track active users/viewers
        self._active_users: Set[str] = set()  # Set of socket IDs

        # Track user permissions (socket_id -> role)
        self._user_roles: Dict[str, str] = {}

        log.info("Global workspace service initialized")

    def get_workspace(self) -> Dict[str, Any]:
        """Get the global workspace."""
        self._workspace["lastAccessed"] = datetime.now().isoformat()
        return self._workspace.copy()

    def update_workspace(self, workspace_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update the global workspace."""
        # Update allowed fields
        if "name" in workspace_data:
            self._workspace["name"] = workspace_data["name"]

        if "tabs" in workspace_data:
            # Validate tab count
            if len(workspace_data["tabs"]) > self.MAX_TABS:
                raise ValueError(f"Maximum tab limit ({self.MAX_TABS}) exceeded")

            # Preserve session IDs when updating tabs
            existing_sessions = {}
            for tab in self._workspace["tabs"]:
                for pane in tab.get("panes", []):
                    if pane.get("sessionId"):
                        existing_sessions[pane["id"]] = pane["sessionId"]

            self._workspace["tabs"] = workspace_data["tabs"]

            # Restore session IDs
            for tab in self._workspace["tabs"]:
                for pane in tab.get("panes", []):
                    if pane["id"] in existing_sessions:
                        pane["sessionId"] = existing_sessions[pane["id"]]

        if "activeTabId" in workspace_data:
            self._workspace["activeTabId"] = workspace_data["activeTabId"]

        if "layout" in workspace_data:
            self._workspace["layout"] = workspace_data["layout"]

        self._workspace["lastAccessed"] = datetime.now().isoformat()

        log.info(f"Updated global workspace")
        return self._workspace.copy()

    def create_tab(
        self, title: str, tab_type: str = "terminal", sub_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a new tab in the global workspace."""
        # Check tab limit
        if len(self._workspace["tabs"]) >= self.MAX_TABS:
            log.warning(f"Tab limit reached ({self.MAX_TABS})")
            return None

        tab_id = f"tab_{uuid4().hex[:8]}"
        tab = {
            "id": tab_id,
            "title": title,
            "type": tab_type,
            "subType": sub_type,
            "isActive": True,
            "panes": [],
            "layout": "single",
            "lastActivity": datetime.now().isoformat(),
        }

        # Deactivate other tabs
        for existing_tab in self._workspace["tabs"]:
            existing_tab["isActive"] = False

        # Create default pane for terminal tabs
        if tab_type == "terminal":
            pane_id = f"pane_{uuid4().hex[:8]}"
            pane = {
                "id": pane_id,
                "type": "terminal",
                "title": "Terminal",
                "isActive": True,
                "sessionId": None,  # Will be set when terminal is created
            }
            tab["panes"].append(pane)

        self._workspace["tabs"].append(tab)
        self._workspace["activeTabId"] = tab_id
        self._workspace["lastAccessed"] = datetime.now().isoformat()

        log.info(f"Created tab {tab_id} in global workspace")
        return tab

    def get_tab(self, tab_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific tab from the global workspace."""
        for tab in self._workspace["tabs"]:
            if tab["id"] == tab_id:
                return tab.copy()
        return None

    def update_pane_session(self, tab_id: str, pane_id: str, session_id: str) -> bool:
        """Update the session ID for a pane."""
        for tab in self._workspace["tabs"]:
            if tab["id"] == tab_id:
                for pane in tab.get("panes", []):
                    if pane["id"] == pane_id:
                        pane["sessionId"] = session_id
                        pane["status"] = "connected"
                        pane["lastActivity"] = datetime.now().isoformat()
                        log.info(f"Updated pane {pane_id} with session {session_id}")
                        return True
        return False

    def add_user(self, socket_id: str, role: str = "User") -> None:
        """Add a user to the active users set."""
        self._active_users.add(socket_id)
        self._user_roles[socket_id] = role
        log.info(f"User {socket_id} ({role}) joined global workspace")

    def remove_user(self, socket_id: str) -> None:
        """Remove a user from the active users set."""
        self._active_users.discard(socket_id)
        self._user_roles.pop(socket_id, None)
        log.info(f"User {socket_id} left global workspace")

    def get_user_count(self) -> int:
        """Get the number of active users."""
        return len(self._active_users)

    def get_user_role(self, socket_id: str) -> Optional[str]:
        """Get the role of a user."""
        return self._user_roles.get(socket_id)

    def can_user_modify(self, socket_id: str) -> bool:
        """Check if a user can modify the workspace."""
        role = self._user_roles.get(socket_id, "User")
        # Viewers cannot modify
        return role != "Viewer"

    def cleanup_closed_sessions(self) -> None:
        """Clean up references to closed terminal sessions."""
        for tab in self._workspace["tabs"]:
            for pane in tab.get("panes", []):
                session_id = pane.get("sessionId")
                if session_id:
                    terminal = AsyncioTerminal.sessions.get(session_id)
                    if not terminal or terminal.closed:
                        pane["sessionId"] = None
                        pane["status"] = "disconnected"
                        log.info(f"Cleaned up closed session {session_id}")


# Singleton instance
_global_workspace_service = None


def get_global_workspace_service() -> GlobalWorkspaceService:
    """Get the singleton global workspace service instance."""
    global _global_workspace_service
    if _global_workspace_service is None:
        _global_workspace_service = GlobalWorkspaceService()
    return _global_workspace_service
