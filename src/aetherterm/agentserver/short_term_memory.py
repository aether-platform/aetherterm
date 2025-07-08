"""
Short-term memory management stub for AetherTerm terminals.
TODO: Implement proper short-term memory functionality.
"""


class ShortTermMemoryManager:
    """Stub implementation of short-term memory manager."""

    def __init__(self, agent_id):
        self.agent_id = agent_id

    async def initialize(self):
        """Initialize memory manager."""
        pass

    async def store(self, key, value):
        """Store a value in memory."""
        pass

    async def retrieve(self, key):
        """Retrieve a value from memory."""
        return None

    async def cleanup(self):
        """Cleanup memory manager."""
        pass
