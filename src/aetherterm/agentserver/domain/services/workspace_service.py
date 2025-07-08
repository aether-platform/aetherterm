"""
Workspace Service for AetherTerm

Manages workspace persistence in memory for session continuity
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging
import json

from ..entities.workspace import Workspace, WorkspaceTab, WorkspacePane

log = logging.getLogger(__name__)


class WorkspaceService:
    """Service for managing workspaces in memory"""

    def __init__(self):
        # In-memory storage for workspaces
        # Key: user_id, Value: Dict[workspace_id, Workspace]
        self._user_workspaces: Dict[str, Dict[str, Workspace]] = {}

        # Quick lookup for active workspaces
        # Key: user_id, Value: workspace_id
        self._active_workspaces: Dict[str, str] = {}

        log.info("WorkspaceService initialized with in-memory storage")

    def create_workspace(self, user_id: str, name: str = "Default Workspace") -> Workspace:
        """Create a new workspace for a user"""
        workspace = Workspace(user_id=user_id, name=name)

        # Initialize user's workspace dict if not exists
        if user_id not in self._user_workspaces:
            self._user_workspaces[user_id] = {}

        # Store the workspace
        self._user_workspaces[user_id][workspace.id] = workspace

        # Set as active workspace
        self._active_workspaces[user_id] = workspace.id

        log.info(f"Created workspace {workspace.id} for user {user_id}")
        return workspace

    def get_workspace(self, user_id: str, workspace_id: str) -> Optional[Workspace]:
        """Get a specific workspace"""
        if user_id in self._user_workspaces:
            workspace = self._user_workspaces[user_id].get(workspace_id)
            if workspace:
                workspace.update_last_accessed()
                return workspace
        return None

    def get_user_workspaces(self, user_id: str) -> List[Workspace]:
        """Get all workspaces for a user"""
        if user_id in self._user_workspaces:
            return list(self._user_workspaces[user_id].values())
        return []

    def get_active_workspace(self, user_id: str) -> Optional[Workspace]:
        """Get the active workspace for a user"""
        if user_id in self._active_workspaces:
            workspace_id = self._active_workspaces[user_id]
            return self.get_workspace(user_id, workspace_id)

        # If no active workspace, try to get the most recent one
        workspaces = self.get_user_workspaces(user_id)
        if workspaces:
            # Sort by last accessed
            workspaces.sort(key=lambda w: w.last_accessed, reverse=True)
            workspace = workspaces[0]
            self._active_workspaces[user_id] = workspace.id
            return workspace

        return None

    def set_active_workspace(self, user_id: str, workspace_id: str) -> bool:
        """Set the active workspace for a user"""
        workspace = self.get_workspace(user_id, workspace_id)
        if workspace:
            self._active_workspaces[user_id] = workspace_id
            workspace.is_active = True

            # Deactivate other workspaces
            for ws_id, ws in self._user_workspaces.get(user_id, {}).items():
                if ws_id != workspace_id:
                    ws.is_active = False

            log.info(f"Set active workspace to {workspace_id} for user {user_id}")
            return True
        return False

    def update_workspace(
        self, user_id: str, workspace_id: str, workspace_data: Dict
    ) -> Optional[Workspace]:
        """Update a workspace with new data"""
        workspace = self.get_workspace(user_id, workspace_id)
        if workspace:
            # Update workspace from dict
            if "name" in workspace_data:
                workspace.name = workspace_data["name"]

            if "tabs" in workspace_data:
                workspace.tabs = [WorkspaceTab.from_dict(tab) for tab in workspace_data["tabs"]]

            if "layout" in workspace_data:
                layout = workspace_data["layout"]
                workspace.layout_type = layout.get("type", workspace.layout_type)
                workspace.layout_config = layout.get("configuration", workspace.layout_config)

            workspace.update_last_accessed()
            log.info(f"Updated workspace {workspace_id} for user {user_id}")
            return workspace
        return None

    def delete_workspace(self, user_id: str, workspace_id: str) -> bool:
        """Delete a workspace"""
        if user_id in self._user_workspaces and workspace_id in self._user_workspaces[user_id]:
            del self._user_workspaces[user_id][workspace_id]

            # If this was the active workspace, clear it
            if self._active_workspaces.get(user_id) == workspace_id:
                del self._active_workspaces[user_id]

            log.info(f"Deleted workspace {workspace_id} for user {user_id}")
            return True
        return False

    def save_workspace_from_client(self, user_id: str, workspace_data: Dict) -> Optional[Workspace]:
        """Save or update a workspace from client data"""
        workspace_id = workspace_data.get("id")

        if not workspace_id:
            # Create new workspace
            workspace = Workspace.from_dict(workspace_data)
            workspace.user_id = user_id

            if user_id not in self._user_workspaces:
                self._user_workspaces[user_id] = {}

            self._user_workspaces[user_id][workspace.id] = workspace
            log.info(f"Saved new workspace {workspace.id} for user {user_id}")
            return workspace
        else:
            # Update existing workspace
            return self.update_workspace(user_id, workspace_id, workspace_data)

    def get_or_create_default_workspace(self, user_id: str) -> Workspace:
        """Get the active workspace or create a default one"""
        workspace = self.get_active_workspace(user_id)
        if not workspace:
            workspace = self.create_workspace(user_id, "Default Workspace")

            # Add a default terminal tab
            default_tab = WorkspaceTab(
                id=f"tab_{datetime.utcnow().timestamp()}",
                title="Terminal 1",
                type="terminal",
                is_active=True,
            )
            workspace.add_tab(default_tab)

        return workspace

    def export_user_workspaces(self, user_id: str) -> str:
        """Export all user workspaces as JSON"""
        workspaces = self.get_user_workspaces(user_id)
        data = {
            "userId": user_id,
            "workspaces": [ws.to_dict() for ws in workspaces],
            "activeWorkspaceId": self._active_workspaces.get(user_id),
            "exportedAt": datetime.utcnow().isoformat(),
        }
        return json.dumps(data, indent=2)

    def import_user_workspaces(self, user_id: str, json_data: str) -> int:
        """Import workspaces from JSON data"""
        try:
            data = json.loads(json_data)
            imported_count = 0

            # Clear existing workspaces for the user
            self._user_workspaces[user_id] = {}

            # Import workspaces
            for ws_data in data.get("workspaces", []):
                workspace = Workspace.from_dict(ws_data)
                workspace.user_id = user_id
                self._user_workspaces[user_id][workspace.id] = workspace
                imported_count += 1

            # Set active workspace
            active_id = data.get("activeWorkspaceId")
            if active_id and active_id in self._user_workspaces[user_id]:
                self._active_workspaces[user_id] = active_id

            log.info(f"Imported {imported_count} workspaces for user {user_id}")
            return imported_count

        except Exception as e:
            log.error(f"Error importing workspaces: {e}")
            return 0

    def get_stats(self) -> Dict:
        """Get service statistics"""
        total_users = len(self._user_workspaces)
        total_workspaces = sum(len(ws) for ws in self._user_workspaces.values())

        return {
            "totalUsers": total_users,
            "totalWorkspaces": total_workspaces,
            "activeWorkspaces": len(self._active_workspaces),
            "memoryUsage": "in-memory",
        }
