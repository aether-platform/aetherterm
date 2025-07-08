"""
Buffer Manager - Infrastructure Layer

Manages terminal output buffers and persistence.
This is infrastructure concern as it deals with data storage.
"""

import os
import time
import logging
from typing import Dict, Optional, Set
from collections import defaultdict

log = logging.getLogger(__name__)


class BufferManager:
    """Manages terminal session buffers at the infrastructure level."""
    
    # Constants
    MAX_BUFFER_SIZE = 500 * 1024  # 500KB
    BUFFER_CLEANUP_INTERVAL = 3600  # 1 hour
    BUFFER_MAX_AGE = 86400  # 24 hours
    
    def __init__(self):
        self._session_buffers: Dict[str, str] = {}
        self._buffer_timestamps: Dict[str, float] = {}
        self._last_cleanup = time.time()
    
    def append_to_buffer(self, session_id: str, data: str) -> None:
        """
        Append data to session buffer.
        
        Args:
            session_id: Session identifier
            data: Data to append
        """
        if session_id not in self._session_buffers:
            self._session_buffers[session_id] = ""
            self._buffer_timestamps[session_id] = time.time()
        
        self._session_buffers[session_id] += data
        
        # Trim buffer if it exceeds max size
        if len(self._session_buffers[session_id]) > self.MAX_BUFFER_SIZE:
            # Keep the last MAX_BUFFER_SIZE bytes
            self._session_buffers[session_id] = self._session_buffers[session_id][-self.MAX_BUFFER_SIZE:]
        
        # Update timestamp
        self._buffer_timestamps[session_id] = time.time()
        
        # Periodic cleanup
        self._cleanup_old_buffers()
    
    def get_buffer(self, session_id: str) -> Optional[str]:
        """
        Get buffer content for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Buffer content or None if not found
        """
        return self._session_buffers.get(session_id)
    
    def clear_buffer(self, session_id: str) -> None:
        """
        Clear buffer for a session.
        
        Args:
            session_id: Session identifier
        """
        self._session_buffers.pop(session_id, None)
        self._buffer_timestamps.pop(session_id, None)
    
    def get_buffer_size(self, session_id: str) -> int:
        """
        Get buffer size for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Buffer size in bytes
        """
        buffer = self._session_buffers.get(session_id, "")
        return len(buffer)
    
    def _cleanup_old_buffers(self) -> None:
        """Clean up old buffers periodically."""
        current_time = time.time()
        
        # Only run cleanup periodically
        if current_time - self._last_cleanup < self.BUFFER_CLEANUP_INTERVAL:
            return
        
        self._last_cleanup = current_time
        
        # Find and remove old buffers
        sessions_to_remove = []
        for session_id, timestamp in self._buffer_timestamps.items():
            if current_time - timestamp > self.BUFFER_MAX_AGE:
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            self.clear_buffer(session_id)
            log.info(f"Cleaned up old buffer for session {session_id}")
    
    def get_all_sessions(self) -> Set[str]:
        """Get all session IDs with buffers."""
        return set(self._session_buffers.keys())
    
    def get_stats(self) -> Dict:
        """Get buffer manager statistics."""
        total_size = sum(len(buffer) for buffer in self._session_buffers.values())
        return {
            'session_count': len(self._session_buffers),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'oldest_buffer_age': self._get_oldest_buffer_age()
        }
    
    def _get_oldest_buffer_age(self) -> Optional[float]:
        """Get age of oldest buffer in seconds."""
        if not self._buffer_timestamps:
            return None
        
        oldest_timestamp = min(self._buffer_timestamps.values())
        return time.time() - oldest_timestamp