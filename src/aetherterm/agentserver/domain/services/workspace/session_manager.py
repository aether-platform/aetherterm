"""
Session Manager - Application Service Component

Focused service for session lifecycle and state management.
"""

import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from uuid import uuid4

log = logging.getLogger("aetherterm.services.session_manager")


class SessionManager:
    """
    Focused session management service.

    Handles:
    - Client session tracking
    - Session authentication and authorization
    - Session state persistence
    - Session cleanup and expiration
    """

    def __init__(self):
        self._sessions = {}  # session_id -> session_data
        self._client_sessions = {}  # client_id -> set of session_ids
        self._session_tokens = {}  # token -> session_id
        self._session_expiry = {}  # session_id -> expiry_time

    async def create_session(
        self,
        client_id: str,
        user_id: Optional[str] = None,
        session_type: str = "terminal",
        metadata: Optional[Dict[str, Any]] = None,
        ttl_hours: int = 24,
    ) -> Dict[str, Any]:
        """Create a new session."""
        try:
            session_id = f"session_{uuid4().hex[:16]}"
            session_token = f"token_{uuid4().hex}"

            # Calculate expiry time
            expiry_time = datetime.utcnow() + timedelta(hours=ttl_hours)

            # Create session data
            session_data = {
                "session_id": session_id,
                "client_id": client_id,
                "user_id": user_id,
                "session_type": session_type,
                "created_at": datetime.utcnow(),
                "last_activity": datetime.utcnow(),
                "expires_at": expiry_time,
                "status": "active",
                "metadata": metadata or {},
                "token": session_token,
            }

            # Store session
            self._sessions[session_id] = session_data
            self._session_tokens[session_token] = session_id
            self._session_expiry[session_id] = expiry_time

            # Track client sessions
            if client_id not in self._client_sessions:
                self._client_sessions[client_id] = set()
            self._client_sessions[client_id].add(session_id)

            log.info(f"Created session {session_id} for client {client_id}")

            return {
                "success": True,
                "session_id": session_id,
                "token": session_token,
                "expires_at": expiry_time.isoformat(),
                "session_data": session_data,
            }

        except Exception as e:
            log.error(f"Failed to create session for client {client_id}: {e}")
            return {"success": False, "error": str(e)}

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data by session ID."""
        try:
            session_data = self._sessions.get(session_id)

            if not session_data:
                return None

            # Check if session is expired
            if await self._is_session_expired(session_id):
                await self.terminate_session(session_id, reason="expired")
                return None

            return session_data

        except Exception as e:
            log.error(f"Failed to get session {session_id}: {e}")
            return None

    async def get_session_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Get session data by authentication token."""
        try:
            session_id = self._session_tokens.get(token)
            if not session_id:
                return None

            return await self.get_session(session_id)

        except Exception as e:
            log.error(f"Failed to get session by token: {e}")
            return None

    async def update_session_activity(self, session_id: str) -> bool:
        """Update session last activity timestamp."""
        try:
            session_data = self._sessions.get(session_id)
            if not session_data:
                return False

            session_data["last_activity"] = datetime.utcnow()
            log.debug(f"Updated activity for session {session_id}")
            return True

        except Exception as e:
            log.error(f"Failed to update session activity {session_id}: {e}")
            return False

    async def extend_session(self, session_id: str, additional_hours: int = 2) -> bool:
        """Extend session expiry time."""
        try:
            session_data = self._sessions.get(session_id)
            if not session_data:
                return False

            new_expiry = session_data["expires_at"] + timedelta(hours=additional_hours)
            session_data["expires_at"] = new_expiry
            self._session_expiry[session_id] = new_expiry

            log.info(f"Extended session {session_id} by {additional_hours} hours")
            return True

        except Exception as e:
            log.error(f"Failed to extend session {session_id}: {e}")
            return False

    async def terminate_session(self, session_id: str, reason: str = "manual") -> bool:
        """Terminate a session."""
        try:
            session_data = self._sessions.get(session_id)
            if not session_data:
                return False

            client_id = session_data["client_id"]
            token = session_data.get("token")

            # Update session status
            session_data["status"] = "terminated"
            session_data["terminated_at"] = datetime.utcnow()
            session_data["termination_reason"] = reason

            # Remove from active tracking
            self._sessions.pop(session_id, None)
            self._session_expiry.pop(session_id, None)

            if token:
                self._session_tokens.pop(token, None)

            # Remove from client sessions
            if client_id in self._client_sessions:
                self._client_sessions[client_id].discard(session_id)
                if not self._client_sessions[client_id]:
                    del self._client_sessions[client_id]

            log.info(f"Terminated session {session_id} (reason: {reason})")
            return True

        except Exception as e:
            log.error(f"Failed to terminate session {session_id}: {e}")
            return False

    async def get_client_sessions(self, client_id: str) -> List[Dict[str, Any]]:
        """Get all sessions for a client."""
        try:
            session_ids = self._client_sessions.get(client_id, set())
            sessions = []

            for session_id in session_ids:
                session_data = await self.get_session(session_id)
                if session_data:
                    sessions.append(session_data)

            return sessions

        except Exception as e:
            log.error(f"Failed to get client sessions for {client_id}: {e}")
            return []

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        try:
            current_time = datetime.utcnow()
            expired_sessions = []

            # Find expired sessions
            for session_id, expiry_time in self._session_expiry.items():
                if current_time > expiry_time:
                    expired_sessions.append(session_id)

            # Terminate expired sessions
            terminated_count = 0
            for session_id in expired_sessions:
                if await self.terminate_session(session_id, reason="expired"):
                    terminated_count += 1

            if terminated_count > 0:
                log.info(f"Cleaned up {terminated_count} expired sessions")

            return terminated_count

        except Exception as e:
            log.error(f"Failed to cleanup expired sessions: {e}")
            return 0

    async def get_session_metrics(self) -> Dict[str, Any]:
        """Get session metrics and statistics."""
        try:
            total_sessions = len(self._sessions)
            active_sessions = len([s for s in self._sessions.values() if s["status"] == "active"])
            total_clients = len(self._client_sessions)

            # Calculate session durations
            durations = []
            for session_data in self._sessions.values():
                if session_data["status"] == "active":
                    duration = (datetime.utcnow() - session_data["created_at"]).total_seconds()
                    durations.append(duration)

            avg_duration = sum(durations) / len(durations) if durations else 0

            # Session types breakdown
            session_types = {}
            for session_data in self._sessions.values():
                session_type = session_data.get("session_type", "unknown")
                session_types[session_type] = session_types.get(session_type, 0) + 1

            return {
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "inactive_sessions": total_sessions - active_sessions,
                "total_clients": total_clients,
                "average_session_duration_seconds": avg_duration,
                "session_types": session_types,
                "sessions_per_client": total_sessions / total_clients if total_clients > 0 else 0,
            }

        except Exception as e:
            log.error(f"Failed to get session metrics: {e}")
            return {}

    async def validate_session(self, session_id: str, client_id: Optional[str] = None) -> bool:
        """Validate session exists and is active."""
        try:
            session_data = await self.get_session(session_id)
            if not session_data:
                return False

            # Check client ownership if specified
            if client_id and session_data["client_id"] != client_id:
                log.warning(f"Session {session_id} does not belong to client {client_id}")
                return False

            return session_data["status"] == "active"

        except Exception as e:
            log.error(f"Failed to validate session {session_id}: {e}")
            return False

    async def transfer_session(self, session_id: str, new_client_id: str) -> bool:
        """Transfer session to a new client."""
        try:
            session_data = self._sessions.get(session_id)
            if not session_data:
                return False

            old_client_id = session_data["client_id"]

            # Update session client
            session_data["client_id"] = new_client_id
            session_data["transferred_at"] = datetime.utcnow()
            session_data["previous_client_id"] = old_client_id

            # Update client session tracking
            if old_client_id in self._client_sessions:
                self._client_sessions[old_client_id].discard(session_id)
                if not self._client_sessions[old_client_id]:
                    del self._client_sessions[old_client_id]

            if new_client_id not in self._client_sessions:
                self._client_sessions[new_client_id] = set()
            self._client_sessions[new_client_id].add(session_id)

            log.info(f"Transferred session {session_id} from {old_client_id} to {new_client_id}")
            return True

        except Exception as e:
            log.error(f"Failed to transfer session {session_id}: {e}")
            return False

    async def _is_session_expired(self, session_id: str) -> bool:
        """Check if session is expired."""
        expiry_time = self._session_expiry.get(session_id)
        if not expiry_time:
            return True

        return datetime.utcnow() > expiry_time

    async def list_all_sessions(self, include_terminated: bool = False) -> List[Dict[str, Any]]:
        """List all sessions with optional filtering."""
        try:
            sessions = []

            for session_data in self._sessions.values():
                if not include_terminated and session_data["status"] != "active":
                    continue

                sessions.append(
                    {
                        "session_id": session_data["session_id"],
                        "client_id": session_data["client_id"],
                        "user_id": session_data.get("user_id"),
                        "session_type": session_data.get("session_type"),
                        "status": session_data["status"],
                        "created_at": session_data["created_at"].isoformat(),
                        "last_activity": session_data["last_activity"].isoformat(),
                        "expires_at": session_data["expires_at"].isoformat(),
                    }
                )

            return sessions

        except Exception as e:
            log.error(f"Failed to list sessions: {e}")
            return []
