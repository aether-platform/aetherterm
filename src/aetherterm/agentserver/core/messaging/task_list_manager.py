"""TaskListManager — shared task list for inter-agent coordination.

Provides CRUD operations for a per-session task list that agents can
use to coordinate work (create tasks, claim ownership, update status).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger("aetherterm.messaging.tasks")


@dataclass
class SharedTask:
    """A task in the shared task list."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    subject: str = ""
    description: str = ""
    status: str = "pending"  # pending | in_progress | completed
    owner: Optional[str] = None  # agent_id (pane_id)
    blocked_by: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    active_form: str = ""

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "subject": self.subject,
            "description": self.description,
            "status": self.status,
            "owner": self.owner,
            "blocked_by": self.blocked_by,
            "metadata": self.metadata,
            "active_form": self.active_form,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SharedTask:
        return cls(
            task_id=data.get("task_id", str(uuid.uuid4())[:8]),
            subject=data.get("subject", ""),
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            owner=data.get("owner"),
            blocked_by=data.get("blocked_by", []),
            metadata=data.get("metadata", {}),
            active_form=data.get("active_form", ""),
        )


class TaskListManager:
    """Per-session shared task list with CRUD operations."""

    def __init__(self) -> None:
        self._tasks: Dict[str, SharedTask] = {}
        self._next_id = 1

    def create_task(
        self,
        subject: str,
        description: str = "",
        active_form: str = "",
        **kwargs: Any,
    ) -> SharedTask:
        """Create a new task and return it."""
        task_id = str(self._next_id)
        self._next_id += 1
        task = SharedTask(
            task_id=task_id,
            subject=subject,
            description=description,
            active_form=active_form,
            **kwargs,
        )
        self._tasks[task_id] = task
        log.info(f"Task created: #{task_id} {subject}")
        return task

    def update_task(self, task_id: str, **kwargs: Any) -> Optional[SharedTask]:
        """Update task fields. Returns updated task or None if not found."""
        task = self._tasks.get(task_id)
        if task is None:
            return None

        for key, value in kwargs.items():
            if hasattr(task, key) and value is not None:
                setattr(task, key, value)

        log.info(f"Task updated: #{task_id}")
        return task

    def delete_task(self, task_id: str) -> bool:
        """Delete a task. Returns True if deleted."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            log.info(f"Task deleted: #{task_id}")
            return True
        return False

    def list_tasks(self) -> List[SharedTask]:
        """Return all tasks."""
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> Optional[SharedTask]:
        """Get a specific task by ID."""
        return self._tasks.get(task_id)

    def claim_task(self, task_id: str, agent_id: str) -> Optional[SharedTask]:
        """Claim a task: set owner and status to in_progress."""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task.owner = agent_id
        task.status = "in_progress"
        log.info(f"Task #{task_id} claimed by {agent_id}")
        return task
