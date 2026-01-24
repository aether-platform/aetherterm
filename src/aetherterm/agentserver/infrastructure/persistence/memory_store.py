"""
Memory Store - Infrastructure Layer

Short-term memory storage for agent sessions.
"""

import logging
from typing import Any, Dict, Optional

log = logging.getLogger("aetherterm.infrastructure.memory")
class MemoryStore:
    """Short-term memory storage for agent sessions."""

    def __init__(self):
        self.memory_store: Dict[str, Dict[str, Any]] = {}

    async def store(self, agent_id: str, key: str, value: Any) -> bool:
        """Store value in short-term memory."""
        try:
            if agent_id not in self.memory_store:
                self.memory_store[agent_id] = {}
            self.memory_store[agent_id][key] = value
            return True
        except Exception as e:
            log.error(f"Failed to store memory for {agent_id}: {e}")
            return False

    async def retrieve(self, agent_id: str, key: str) -> Optional[Any]:
        """Retrieve value from short-term memory."""
        try:
            return self.memory_store.get(agent_id, {}).get(key)
        except Exception as e:
            log.error(f"Failed to retrieve memory for {agent_id}: {e}")
            return None

    async def clear_agent_memory(self, agent_id: str):
        """Clear all memory for an agent."""
        if agent_id in self.memory_store:
            del self.memory_store[agent_id]
