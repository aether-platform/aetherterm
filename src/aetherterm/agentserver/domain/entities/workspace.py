"""
Workspace Entity for AetherTerm

Handles workspace persistence and management across devices/sessions
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
import json
import uuid


@dataclass
class WorkspacePane:
    """Represents a pane within a workspace tab"""

    id: str
    title: str
    type: str  # 'terminal', 'ai-agent', 'log-monitor'
    sub_type: Optional[str] = None  # 'pure', 'inventory', 'agent', 'main-agent'
    session_id: Optional[str] = None
    position: Dict[str, float] = field(default_factory=dict)  # x, y, width, height
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "subType": self.sub_type,
            "sessionId": self.session_id,
            "position": self.position,
            "createdAt": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkspacePane":
        return cls(
            id=data["id"],
            title=data["title"],
            type=data["type"],
            sub_type=data.get("subType"),
            session_id=data.get("sessionId"),
            position=data.get("position", {}),
            created_at=datetime.fromisoformat(data["createdAt"])
            if "createdAt" in data
            else datetime.utcnow(),
        )


@dataclass
class WorkspaceTab:
    """Represents a tab within a workspace"""

    id: str
    title: str
    type: str  # 'terminal', 'ai-agent', 'log-monitor'
    sub_type: Optional[str] = None
    is_active: bool = False
    panes: List[WorkspacePane] = field(default_factory=list)
    layout: str = "single"  # 'single', 'horizontal', 'vertical', 'grid'
    last_activity: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "subType": self.sub_type,
            "isActive": self.is_active,
            "panes": [pane.to_dict() for pane in self.panes],
            "layout": self.layout,
            "lastActivity": self.last_activity.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkspaceTab":
        return cls(
            id=data["id"],
            title=data["title"],
            type=data.get("type", "terminal"),
            sub_type=data.get("subType"),
            is_active=data.get("isActive", False),
            panes=[WorkspacePane.from_dict(p) for p in data.get("panes", [])],
            layout=data.get("layout", "single"),
            last_activity=datetime.fromisoformat(data["lastActivity"])
            if "lastActivity" in data
            else datetime.utcnow(),
        )


@dataclass
class Workspace:
    """Represents a user workspace with tabs and panes"""

    id: str = field(default_factory=lambda: f"workspace_{uuid.uuid4().hex[:8]}")
    user_id: str = ""  # User identifier (email, username, etc.)
    name: str = "Default Workspace"
    tabs: List[WorkspaceTab] = field(default_factory=list)
    is_active: bool = True
    layout_type: str = "tabs"  # 'tabs', 'grid', 'mosaic'
    layout_config: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "userId": self.user_id,
            "name": self.name,
            "tabs": [tab.to_dict() for tab in self.tabs],
            "isActive": self.is_active,
            "layout": {"type": self.layout_type, "configuration": self.layout_config},
            "createdAt": self.created_at.isoformat(),
            "lastAccessed": self.last_accessed.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workspace":
        layout = data.get("layout", {})
        return cls(
            id=data["id"],
            user_id=data.get("userId", ""),
            name=data.get("name", "Default Workspace"),
            tabs=[WorkspaceTab.from_dict(t) for t in data.get("tabs", [])],
            is_active=data.get("isActive", True),
            layout_type=layout.get("type", "tabs"),
            layout_config=layout.get("configuration", {}),
            created_at=datetime.fromisoformat(data["createdAt"])
            if "createdAt" in data
            else datetime.utcnow(),
            last_accessed=datetime.fromisoformat(data["lastAccessed"])
            if "lastAccessed" in data
            else datetime.utcnow(),
            metadata=data.get("metadata", {}),
        )

    def to_json(self) -> str:
        """Serialize workspace to JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "Workspace":
        """Deserialize workspace from JSON string"""
        return cls.from_dict(json.loads(json_str))

    def update_last_accessed(self):
        """Update the last accessed timestamp"""
        self.last_accessed = datetime.utcnow()

    def get_active_tab(self) -> Optional[WorkspaceTab]:
        """Get the currently active tab"""
        for tab in self.tabs:
            if tab.is_active:
                return tab
        return None

    def set_active_tab(self, tab_id: str):
        """Set the active tab by ID"""
        for tab in self.tabs:
            tab.is_active = tab.id == tab_id

    def add_tab(self, tab: WorkspaceTab):
        """Add a new tab to the workspace"""
        # Deactivate other tabs if this one is active
        if tab.is_active:
            for existing_tab in self.tabs:
                existing_tab.is_active = False
        self.tabs.append(tab)

    def remove_tab(self, tab_id: str) -> bool:
        """Remove a tab by ID"""
        for i, tab in enumerate(self.tabs):
            if tab.id == tab_id:
                was_active = tab.is_active
                self.tabs.pop(i)

                # If removed tab was active and there are remaining tabs, activate the last one
                if was_active and self.tabs:
                    self.tabs[-1].is_active = True

                return True
        return False

    def find_tab(self, tab_id: str) -> Optional[WorkspaceTab]:
        """Find a tab by ID"""
        for tab in self.tabs:
            if tab.id == tab_id:
                return tab
        return None
