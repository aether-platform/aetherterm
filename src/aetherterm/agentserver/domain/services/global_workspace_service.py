"""
Global Workspace Service

Manages a single shared workspace for all users.
All users (including Viewers) connect to the same workspace.
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from uuid import uuid4
from pathlib import Path

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal

log = logging.getLogger(__name__)


class GlobalWorkspaceService:
    """Manages a single global workspace shared by all users."""

    # Configuration constants
    MAX_TABS = 20  # Maximum tabs in the global workspace
    MAX_PANES_PER_TAB = 4  # Maximum panes per tab

    # Default workspace ID
    GLOBAL_WORKSPACE_ID = "global_workspace"
    
    # Persistence file path
    WORKSPACE_FILE = Path.home() / ".aetherterm" / "global_workspace.json"

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

        # Try to restore workspace from existing sessions
        self._restore_from_sessions()

        log.info("Global workspace service initialized")

    def _restore_from_sessions(self):
        """Restore workspace structure from existing terminal sessions."""
        try:
            # Check if there are any existing sessions in AsyncioTerminal
            existing_sessions = list(AsyncioTerminal.sessions.keys())
            if not existing_sessions:
                log.info("No existing sessions to restore")
                return

            log.info(f"Found {len(existing_sessions)} existing sessions to restore")

            # Group sessions by their tab/pane structure
            # Session IDs are in format: aether_pane_<pane_id> or similar
            tab_groups = {}
            
            for session_id in existing_sessions:
                # Extract tab information from session ID
                # Expected formats: aether_pane_XXX, aether_tab_XXX, terminal_pane_XXX
                parts = session_id.split('_')
                if len(parts) >= 3:
                    # Try to extract tab ID from session metadata
                    terminal = AsyncioTerminal.sessions.get(session_id)
                    if terminal and hasattr(terminal, 'tab_index'):
                        tab_index = terminal.tab_index
                        if tab_index not in tab_groups:
                            tab_groups[tab_index] = []
                        tab_groups[tab_index].append({
                            'session_id': session_id,
                            'pane_index': getattr(terminal, 'pane_index', 0)
                        })

            # Create tabs from grouped sessions
            for tab_index, sessions in sorted(tab_groups.items()):
                tab_id = f"tab_{tab_index + 1:03d}"
                tab = {
                    "id": tab_id,
                    "title": f"Terminal {tab_index + 1}",
                    "type": "terminal",
                    "subType": "pure",
                    "isActive": tab_index == 0,
                    "panes": [],
                    "layout": "single",
                    "lastActivity": datetime.now().isoformat(),
                }

                # Create panes for each session
                for session_info in sorted(sessions, key=lambda x: x['pane_index']):
                    pane_id = f"pane_{session_info['pane_index'] + 1:03d}"
                    pane = {
                        "id": pane_id,
                        "type": "terminal",
                        "title": "Terminal",
                        "isActive": session_info['pane_index'] == 0,
                        "sessionId": session_info['session_id'],
                    }
                    tab["panes"].append(pane)

                self._workspace["tabs"].append(tab)
                log.info(f"Restored tab {tab_id} with {len(tab['panes'])} panes")

            if self._workspace["tabs"]:
                self._workspace["activeTabId"] = self._workspace["tabs"][0]["id"]
                log.info(f"Restored {len(self._workspace['tabs'])} tabs from existing sessions")

        except Exception as e:
            log.error(f"Error restoring workspace from sessions: {e}", exc_info=True)

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

    def close_tab(self, tab_id: str) -> bool:
        """Close a tab and remove it from the workspace."""
        try:
            # Find and remove the tab
            tab_index = None
            for i, tab in enumerate(self._workspace["tabs"]):
                if tab["id"] == tab_id:
                    tab_index = i
                    break
            
            if tab_index is None:
                log.warning(f"Tab {tab_id} not found for closure")
                return False
            
            # Remove the tab
            removed_tab = self._workspace["tabs"].pop(tab_index)
            log.info(f"Removed tab {tab_id} from workspace")
            
            # If this was the active tab, set a new active tab
            if self._workspace.get("activeTabId") == tab_id:
                if self._workspace["tabs"]:
                    # Set the first remaining tab as active
                    self._workspace["activeTabId"] = self._workspace["tabs"][0]["id"]
                    log.info(f"Set new active tab: {self._workspace['activeTabId']}")
                else:
                    # No tabs left
                    self._workspace["activeTabId"] = None
                    log.info("No tabs remaining, cleared activeTabId")
            
            # Update timestamp
            self._workspace["lastAccessed"] = datetime.now().isoformat()
            
            return True
            
        except Exception as e:
            log.error(f"Error closing tab {tab_id}: {e}", exc_info=True)
            return False


# Singleton instance
_global_workspace_service = None


def get_global_workspace_service() -> GlobalWorkspaceService:
    """Get the singleton global workspace service instance."""
    global _global_workspace_service
    if _global_workspace_service is None:
        _global_workspace_service = GlobalWorkspaceService()
    return _global_workspace_service
