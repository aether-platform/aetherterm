"""
インメモリターミナルリポジトリ実装

TerminalRepositoryPort の実装。
AsyncioTerminal のクラスレベル辞書をラップします。
"""

import logging
from typing import Any, List, Optional, Set

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

    def add_client_to_session(self, session_id: str, client_sid: str) -> bool:
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal and hasattr(terminal, "client_sids"):
            terminal.client_sids.add(client_sid)
            return True
        return False

    def remove_client_from_session(self, session_id: str, client_sid: str) -> int:
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal and hasattr(terminal, "client_sids"):
            terminal.client_sids.discard(client_sid)
            return len(terminal.client_sids)
        return 0

    def get_all_sessions_for_client(self, client_sid: str) -> List[str]:
        result = []
        for session_id, terminal in AsyncioTerminal.sessions.items():
            if hasattr(terminal, "client_sids") and client_sid in terminal.client_sids:
                result.append(session_id)
        return result

    async def write_to_session(self, session_id: str, data: str) -> bool:
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal:
            await terminal.write(data)
            return True
        return False

    async def resize_session(self, session_id: str, cols: int, rows: int) -> bool:
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal:
            await terminal.resize(cols, rows)
            return True
        return False

    async def close_session(self, session_id: str) -> None:
        terminal = AsyncioTerminal.sessions.get(session_id)
        if terminal:
            await terminal.close()

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
