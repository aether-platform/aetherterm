"""
Workspace Management Service

Handles server-side workspace, tab, and pane management.
All terminal sessions are created and managed through this service.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4

from aetherterm.agentserver.domain.entities.terminals.asyncio_terminal import AsyncioTerminal
from aetherterm.agentserver.domain.services.workspace_token_service import get_workspace_token_service

log = logging.getLogger(__name__)


class WorkspaceManagementService:
    """Manages workspaces, tabs, and panes on the server."""
    
    def __init__(self):
        # In-memory storage for workspaces
        # In production, this should be persisted to a database
        self._workspaces: Dict[str, Dict[str, Any]] = {}
        self._token_service = get_workspace_token_service()
    
    def create_workspace(self, workspace_token: str, name: str) -> Dict[str, Any]:
        """Create a new workspace."""
        workspace_id = f"workspace_{int(datetime.now().timestamp() * 1000)}"
        
        workspace = {
            "id": workspace_id,
            "name": name,
            "lastAccessed": datetime.now().isoformat(),
            "tabs": [],
            "isActive": True,
            "layout": {
                "type": "tabs",
                "configuration": {}
            }
        }
        
        # Store workspace associated with token
        if workspace_token not in self._workspaces:
            self._workspaces[workspace_token] = {}
        
        self._workspaces[workspace_token][workspace_id] = workspace
        
        log.info(f"Created workspace {workspace_id} for token {workspace_token[:8]}...")
        return workspace
    
    def get_workspace(self, workspace_token: str, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific workspace."""
        if workspace_token in self._workspaces:
            workspace = self._workspaces[workspace_token].get(workspace_id)
            if workspace:
                # Update last accessed
                workspace["lastAccessed"] = datetime.now().isoformat()
                return workspace
        return None
    
    def list_workspaces(self, workspace_token: str) -> List[Dict[str, Any]]:
        """List all workspaces for a token."""
        if workspace_token in self._workspaces:
            return list(self._workspaces[workspace_token].values())
        return []
    
    def create_tab(
        self, 
        workspace_token: str, 
        workspace_id: str, 
        title: str, 
        tab_type: str = "terminal",
        sub_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a new tab in a workspace."""
        workspace = self.get_workspace(workspace_token, workspace_id)
        if not workspace:
            log.error(f"Workspace {workspace_id} not found")
            return None
        
        tab_id = f"tab-{int(datetime.now().timestamp() * 1000)}"
        
        # Create pane for terminal tabs
        panes = []
        if tab_type == "terminal":
            pane_id = f"pane-{int(datetime.now().timestamp() * 1000)}-{uuid4().hex[:9]}"
            pane = {
                "id": pane_id,
                "title": title,
                "type": "terminal",
                "subType": sub_type or "pure",
                "sessionId": None,  # Will be set when terminal is created
                "isActive": True,
                "lastActivity": datetime.now().isoformat(),
                "status": "disconnected",
                "position": {
                    "x": 0,
                    "y": 0,
                    "width": 100,
                    "height": 100
                }
            }
            panes.append(pane)
        
        tab = {
            "id": tab_id,
            "title": title,
            "type": tab_type,
            "subType": sub_type,
            "isActive": True,
            "panes": panes,
            "layout": "single",
            "lastActivity": datetime.now().isoformat()
        }
        
        # Deactivate other tabs
        for existing_tab in workspace["tabs"]:
            existing_tab["isActive"] = False
        
        workspace["tabs"].append(tab)
        
        log.info(f"Created tab {tab_id} in workspace {workspace_id}")
        return tab
    
    def get_tab(self, workspace_token: str, workspace_id: str, tab_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific tab from a workspace."""
        workspace = self.get_workspace(workspace_token, workspace_id)
        if workspace:
            for tab in workspace["tabs"]:
                if tab["id"] == tab_id:
                    return tab
        return None
    
    def create_pane(
        self,
        workspace_token: str,
        workspace_id: str,
        tab_id: str,
        title: str,
        pane_type: str = "terminal",
        sub_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a new pane in a tab."""
        tab = self.get_tab(workspace_token, workspace_id, tab_id)
        if not tab:
            log.error(f"Tab {tab_id} not found in workspace {workspace_id}")
            return None
        
        pane_id = f"pane-{int(datetime.now().timestamp() * 1000)}-{uuid4().hex[:9]}"
        
        pane = {
            "id": pane_id,
            "title": title,
            "type": pane_type,
            "subType": sub_type or "pure",
            "sessionId": None,  # Will be set when terminal is created
            "isActive": False,
            "lastActivity": datetime.now().isoformat(),
            "status": "disconnected",
            "position": {
                "x": 0,
                "y": 0,
                "width": 50,  # Default to half width for split
                "height": 100
            }
        }
        
        # Adjust existing pane positions for split
        if len(tab["panes"]) == 1:
            tab["panes"][0]["position"]["width"] = 50
            pane["position"]["x"] = 50
        
        tab["panes"].append(pane)
        tab["layout"] = "horizontal" if len(tab["panes"]) > 1 else "single"
        
        log.info(f"Created pane {pane_id} in tab {tab_id}")
        return pane
    
    def update_pane_session(
        self,
        workspace_token: str,
        workspace_id: str,
        tab_id: str,
        pane_id: str,
        session_id: str
    ) -> bool:
        """Update the session ID for a pane."""
        tab = self.get_tab(workspace_token, workspace_id, tab_id)
        if tab:
            for pane in tab["panes"]:
                if pane["id"] == pane_id:
                    pane["sessionId"] = session_id
                    pane["status"] = "connected"
                    pane["lastActivity"] = datetime.now().isoformat()
                    log.info(f"Updated pane {pane_id} with session {session_id}")
                    return True
        return False
    
    def get_workspace_for_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Find the workspace that contains a specific session."""
        for token_workspaces in self._workspaces.values():
            for workspace in token_workspaces.values():
                for tab in workspace.get("tabs", []):
                    for pane in tab.get("panes", []):
                        if pane.get("sessionId") == session_id:
                            return workspace
        return None
    
    def cleanup_closed_sessions(self):
        """Clean up references to closed terminal sessions."""
        for token_workspaces in self._workspaces.values():
            for workspace in token_workspaces.values():
                for tab in workspace.get("tabs", []):
                    for pane in tab.get("panes", []):
                        session_id = pane.get("sessionId")
                        if session_id:
                            terminal = AsyncioTerminal.sessions.get(session_id)
                            if not terminal or terminal.closed:
                                pane["sessionId"] = None
                                pane["status"] = "disconnected"


# Global instance
_workspace_service: Optional[WorkspaceManagementService] = None


def get_workspace_management_service() -> WorkspaceManagementService:
    """Get the global workspace management service instance."""
    global _workspace_service
    if _workspace_service is None:
        _workspace_service = WorkspaceManagementService()
    return _workspace_service