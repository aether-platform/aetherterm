"""
Workspace Token Service

Manages workspace tokens for cross-window session sharing
"""

import logging
from typing import Dict, Set, Optional
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


class WorkspaceTokenService:
    """Service for managing workspace tokens and socket associations"""
    
    def __init__(self):
        # Map workspace token to set of socket IDs
        self._token_to_sockets: Dict[str, Set[str]] = {}
        
        # Map socket ID to workspace token
        self._socket_to_token: Dict[str, str] = {}
        
        # Map workspace token to user information
        self._token_info: Dict[str, Dict] = {}
        
        log.info("WorkspaceTokenService initialized")
    
    def register_socket(self, sid: str, token: str) -> None:
        """Register a socket with a workspace token"""
        if not token:
            log.warning(f"Socket {sid} connected without workspace token")
            return
            
        # Remove any previous token association
        if sid in self._socket_to_token:
            old_token = self._socket_to_token[sid]
            if old_token in self._token_to_sockets:
                self._token_to_sockets[old_token].discard(sid)
        
        # Register new association
        self._socket_to_token[sid] = token
        
        if token not in self._token_to_sockets:
            self._token_to_sockets[token] = set()
            self._token_info[token] = {
                'created_at': datetime.now(),
                'last_activity': datetime.now()
            }
        
        self._token_to_sockets[token].add(sid)
        self._token_info[token]['last_activity'] = datetime.now()
        
        log.info(f"Socket {sid} registered with workspace token {token}")
        log.info(f"Token {token} now has {len(self._token_to_sockets[token])} connected sockets")
    
    def unregister_socket(self, sid: str) -> Optional[str]:
        """Unregister a socket and return its token"""
        token = self._socket_to_token.get(sid)
        
        if token:
            del self._socket_to_token[sid]
            
            if token in self._token_to_sockets:
                self._token_to_sockets[token].discard(sid)
                
                # Clean up empty token entries
                if not self._token_to_sockets[token]:
                    del self._token_to_sockets[token]
                    del self._token_info[token]
                    log.info(f"Workspace token {token} removed (no more connections)")
                else:
                    log.info(f"Socket {sid} unregistered from token {token}, {len(self._token_to_sockets[token])} sockets remaining")
        
        return token
    
    def get_token_for_socket(self, sid: str) -> Optional[str]:
        """Get the workspace token for a socket ID"""
        return self._socket_to_token.get(sid)
    
    def get_sockets_for_token(self, token: str) -> Set[str]:
        """Get all socket IDs associated with a token"""
        return self._token_to_sockets.get(token, set()).copy()
    
    def is_same_workspace(self, sid1: str, sid2: str) -> bool:
        """Check if two sockets belong to the same workspace"""
        token1 = self._socket_to_token.get(sid1)
        token2 = self._socket_to_token.get(sid2)
        
        return token1 is not None and token1 == token2
    
    def get_primary_socket(self, token: str) -> Optional[str]:
        """Get the primary (oldest) socket for a workspace token"""
        sockets = self._token_to_sockets.get(token)
        
        if sockets:
            # Return the first socket (oldest connection)
            return next(iter(sockets))
        
        return None
    
    def get_stats(self) -> Dict:
        """Get service statistics"""
        return {
            'total_tokens': len(self._token_to_sockets),
            'total_sockets': len(self._socket_to_token),
            'tokens_with_multiple_sockets': sum(
                1 for sockets in self._token_to_sockets.values() 
                if len(sockets) > 1
            ),
            'active_connections': [
                {
                    'token': token[:8] + '...',  # Show only first 8 chars
                    'socket_count': len(sockets),
                    'last_activity': self._token_info[token]['last_activity'].isoformat()
                }
                for token, sockets in self._token_to_sockets.items()
            ]
        }
    
    def cleanup_old_tokens(self, max_age_hours: int = 24) -> int:
        """Clean up tokens that haven't been active for a while"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        tokens_to_remove = []
        
        for token, info in self._token_info.items():
            if info['last_activity'] < cutoff_time and not self._token_to_sockets.get(token):
                tokens_to_remove.append(token)
        
        for token in tokens_to_remove:
            if token in self._token_to_sockets:
                del self._token_to_sockets[token]
            if token in self._token_info:
                del self._token_info[token]
        
        if tokens_to_remove:
            log.info(f"Cleaned up {len(tokens_to_remove)} inactive workspace tokens")
        
        return len(tokens_to_remove)


# Global instance
_token_service_instance = None


def get_workspace_token_service() -> WorkspaceTokenService:
    """Get the global workspace token service instance"""
    global _token_service_instance
    if _token_service_instance is None:
        _token_service_instance = WorkspaceTokenService()
    return _token_service_instance