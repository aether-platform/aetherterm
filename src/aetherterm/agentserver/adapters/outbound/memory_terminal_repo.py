"""
インメモリターミナルリポジトリ実装

TerminalRepositoryPort の実装。
AsyncioTerminal のクラスレベル辞書をラップします。
"""

import logging
from typing import Any, Optional, Set

from ...application.ports.terminal_repository import TerminalRepositoryPort
from ...domain.entities import SessionOwner, TerminalSessionInfo
from ...terminals.asyncio_terminal import AsyncioTerminal

logger = logging.getLogger(__name__)


class InMemoryTerminalRepository(TerminalRepositoryPort):
    """AsyncioTerminal のクラスレベル辞書をラップするリポジトリ"""

    def get_session(self, session_id: str) -> Optional[Any]:
        return AsyncioTerminal.sessions.get(session_id)

    def session_exists(self, session_id: str) -> bool:
        return session_id in AsyncioTerminal.sessions

    def is_session_closed(self, session_id: str) -> bool:
        return session_id in AsyncioTerminal.closed_sessions

    def get_session_info(self, session_id: str) -> Optional[TerminalSessionInfo]:
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal is None:
            return None

        owner = self._get_owner(session_id)
        return TerminalSessionInfo(
            session_id=session_id,
            client_sids=set(terminal.client_sids) if hasattr(terminal, "client_sids") else set(),
            is_closed=terminal.closed,
            owner=owner,
            history=terminal.history if hasattr(terminal, "history") else "",
        )

    def get_session_owner(self, session_id: str) -> Optional[SessionOwner]:
        return self._get_owner(session_id)

    def get_client_sids(self, session_id: str) -> Set[str]:
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal and hasattr(terminal, "client_sids"):
            return set(terminal.client_sids)
        return set()

    def get_terminal_context(self, session_id: str) -> Optional[str]:
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal is None:
            return None

        context_parts = []

        if hasattr(terminal, "history") and terminal.history:
            recent_history = (
                terminal.history[-1000:] if len(terminal.history) > 1000 else terminal.history
            )
            context_parts.append(f"Recent terminal output:\n{recent_history}")

        if hasattr(terminal, "path") and terminal.path:
            context_parts.append(f"Current directory: {terminal.path}")

        if hasattr(terminal, "user") and terminal.user:
            context_parts.append(f"User: {terminal.user.name}")

        return "\n\n".join(context_parts) if context_parts else None

    def _get_owner(self, session_id: str) -> Optional[SessionOwner]:
        owner_info = AsyncioTerminal.session_owners.get(session_id)
        if owner_info is None:
            return None

        return SessionOwner(
            remote_addr=owner_info.get("remote_addr"),
            remote_user=owner_info.get("remote_user"),
            user_name=owner_info.get("user_name"),
            created_at=owner_info.get("created_at", 0),
        )
