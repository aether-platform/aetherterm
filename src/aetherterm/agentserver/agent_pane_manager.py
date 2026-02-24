"""エージェントペーン管理

エージェント用のペーン（ターミナルセッション）を管理し、
エージェント間のメッセージルーティングを行います。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from ..common.agent_protocol import (
    AgentMessage,
    PaneConfig,
    PaneType,
)
from .state_manager import PaneState, SessionState

logger = logging.getLogger(__name__)

# Type alias for broadcast function: (session_id, message) -> None
BroadcastFn = Callable[[str, Optional[str]], None]


@dataclass
class AgentPane:
    """エージェントペーン"""

    pane_id: str = field(default_factory=lambda: f"pane_{uuid4().hex[:8]}")
    parent_session_id: str = ""
    agent_id: str = ""
    agent_type: str = ""
    pane_type: PaneType = PaneType.AGENT
    title: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    terminal_id: Optional[str] = None
    socket_id: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pane_id": self.pane_id,
            "parent_session_id": self.parent_session_id,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "pane_type": self.pane_type.value,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "terminal_id": self.terminal_id,
            "status": self.status,
            "metadata": self.metadata,
        }


class AgentPaneManager:
    """エージェントペーンマネージャー

    Session -> Paneの階層構造を管理し、3つのモード（code-server, Tmux, AIチャット）
    およびObservableな状態管理を提供します。
    """

    def __init__(self, broadcast_fn: Optional[BroadcastFn] = None):
        self._sessions: Dict[str, SessionState] = {}
        self._panes: Dict[str, PaneState] = {}  # mapping pane_id to state
        self._pane_to_session: Dict[str, str] = {}  # pane_id -> session_id
        self._agent_to_pane: Dict[str, str] = {}  # agent_id -> pane_id
        self._socket_to_pane: Dict[str, str] = {}  # socket_id -> pane_id
        self._message_router: Optional[MessageRouter] = None
        self._terminal_manager = None
        self._broadcast_fn: Optional[BroadcastFn] = broadcast_fn

        # コールバック
        self._pane_created_callbacks: List[Callable[[PaneState], None]] = []
        self._session_created_callbacks: List[Callable[[SessionState], None]] = []

    def set_terminal_manager(self, terminal_manager: Any) -> None:
        """ターミナルマネージャーを設定"""
        self._terminal_manager = terminal_manager

    def set_message_router(self, router: "MessageRouter") -> None:
        """メッセージルーターを設定"""
        self._message_router = router

    async def get_or_create_session(self, session_id: str) -> SessionState:
        """セッションを取得または作成"""
        if session_id not in self._sessions:
            session = SessionState(session_id)
            session.set_sync_callback(self._on_state_sync)
            self._sessions[session_id] = session
            logger.info(f"セッションを作成しました: {session_id}")
            for cb in self._session_created_callbacks:
                await self._execute_callback(cb, session)
        return self._sessions[session_id]

    async def create_agent_pane(
        self, parent_session_id: str, agent_type: str, config: PaneConfig, mode: str = "terminal"
    ) -> PaneState:
        """新しいエージェントペーンを作成し、セッションに紐付けます。"""
        session = await self.get_or_create_session(parent_session_id)

        pane_id = f"pane_{uuid4().hex[:8]}"
        pane = PaneState(pane_id, mode=mode)
        pane.title = config.title or f"{agent_type} Agent"
        pane.set_sync_callback(self._on_state_sync)

        # セッションに追加
        session.add_pane(pane)
        self._panes[pane_id] = pane
        self._pane_to_session[pane_id] = parent_session_id

        agent_id = f"{agent_type}_{pane_id}"
        self._agent_to_pane[agent_id] = pane_id

        # ターミナルセッション作成
        if self._terminal_manager and config.pane_type in [PaneType.AGENT, PaneType.TERMINAL]:
            terminal_config = {
                "rows": config.size.get("rows", 24),
                "cols": config.size.get("cols", 80),
                "title": pane.title,
                "agent_id": agent_id,
            }
            terminal_id = await self._create_terminal_session(terminal_config)
            # PaneStateにterminal_idを保持させたい場合は拡張が必要だが、
            # 現在はObservable Stateの同期を優先
            pane.id = pane_id  # Ensure ID is set

        for callback in self._pane_created_callbacks:
            await self._execute_callback(callback, pane)

        logger.info(f"ペーンを作成しました: {pane_id} (Session: {parent_session_id}, Mode: {mode})")
        return pane

    def _on_state_sync(self, target_id: str, data: Dict[str, Any]):
        """状態変更をWebSocketでブロードキャスト"""
        if self._broadcast_fn:
            # 状態同期メッセージを送信 (Observableな遷移)
            asyncio.create_task(self._broadcast_fn(target_id, {"type": "state_sync", "data": data}))

    async def destroy_pane(self, pane_id: str) -> bool:
        """ペーンを破棄します。"""
        pane = self._panes.get(pane_id)
        if not pane:
            return False

        # セッションから削除
        session_id = self._pane_to_session.get(pane_id)
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            if pane_id in session.panes:
                del session.panes[pane_id]

        # 登録を解除
        self._panes.pop(pane_id, None)
        self._pane_to_session.pop(pane_id, None)
        self._agent_to_pane = {k: v for k, v in self._agent_to_pane.items() if v != pane_id}
        if pane.socket_id:
            self._socket_to_pane.pop(pane.socket_id, None)

        logger.info(f"ペーンを破棄しました: {pane_id}")
        return True

    async def route_message(self, from_pane: str, to_pane: str, message: AgentMessage) -> bool:
        """ペーン間のメッセージをルーティング

        Args:
            from_pane: 送信元ペーンID
            to_pane: 送信先ペーンID
            message: メッセージ

        Returns:
            bool: ルーティングが成功した場合True
        """
        if self._message_router:
            return await self._message_router.route(from_pane, to_pane, message)

        logger.warning("メッセージルーターが設定されていません")
        return False

    async def broadcast_to_agents(
        self, message: AgentMessage, agent_types: Optional[List[str]] = None
    ) -> int:
        """エージェントにブロードキャスト

        Args:
            message: メッセージ
            agent_types: 対象エージェントタイプ（Noneの場合は全エージェント）

        Returns:
            int: 送信したエージェント数
        """
        count = 0

        for pane in self._panes.values():
            if pane.status != "active":
                continue

            if agent_types and pane.agent_type not in agent_types:
                continue

            if await self.route_message("system", pane.pane_id, message):
                count += 1

        return count

    def get_pane(self, pane_id: str) -> Optional[AgentPane]:
        """ペーンを取得"""
        return self._panes.get(pane_id)

    def get_pane_by_agent(self, agent_id: str) -> Optional[AgentPane]:
        """エージェントIDからペーンを取得"""
        pane_id = self._agent_to_pane.get(agent_id)
        return self._panes.get(pane_id) if pane_id else None

    def get_pane_by_socket(self, socket_id: str) -> Optional[AgentPane]:
        """ソケットIDからペーンを取得"""
        pane_id = self._socket_to_pane.get(socket_id)
        return self._panes.get(pane_id) if pane_id else None

    def list_panes(
        self,
        parent_session_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[PaneState]:
        """ペーンの一覧を取得します。"""
        if parent_session_id and parent_session_id in self._sessions:
            panes = list(self._sessions[parent_session_id].panes.values())
        else:
            panes = list(self._panes.values())
        return panes

    def list_sessions(self) -> List[SessionState]:
        """セッションの一覧を取得します。"""
        return list(self._sessions.values())

    def update_socket_mapping(self, pane_id: str, socket_id: str) -> None:
        """ソケットIDマッピングを更新"""
        pane = self._panes.get(pane_id)
        if pane:
            # 古いマッピングを削除
            if pane.socket_id:
                self._socket_to_pane.pop(pane.socket_id, None)

            # 新しいマッピングを設定
            pane.socket_id = socket_id
            self._socket_to_pane[socket_id] = pane_id

    def register_pane_created_callback(self, callback: Callable[[AgentPane], None]) -> None:
        """ペーン作成コールバックを登録"""
        if callback not in self._pane_created_callbacks:
            self._pane_created_callbacks.append(callback)

    def unregister_pane_created_callback(self, callback: Callable[[AgentPane], None]) -> None:
        """ペーン作成コールバックを解除"""
        if callback in self._pane_created_callbacks:
            self._pane_created_callbacks.remove(callback)

    def register_pane_destroyed_callback(self, callback: Callable[[str], None]) -> None:
        """ペーン破棄コールバックを登録"""
        if callback not in self._pane_destroyed_callbacks:
            self._pane_destroyed_callbacks.append(callback)

    def unregister_pane_destroyed_callback(self, callback: Callable[[str], None]) -> None:
        """ペーン破棄コールバックを解除"""
        if callback in self._pane_destroyed_callbacks:
            self._pane_destroyed_callbacks.remove(callback)

    def set_broadcast_fn(self, broadcast_fn: BroadcastFn) -> None:
        """外部からbroadcast関数を注入"""
        self._broadcast_fn = broadcast_fn

    async def _create_terminal_session(self, config: Dict[str, Any]) -> str:
        """AsyncioTerminalを作成して実ターミナルセッションを返す"""
        from aetherterm.agentserver import utils
        from aetherterm.agentserver.terminals.asyncio_terminal import AsyncioTerminal

        terminal_id = f"term_{uuid4().hex[:8]}"

        try:
            terminal_user = None
            try:
                terminal_user = utils.User()
            except Exception:
                pass

            broadcast = self._broadcast_fn or (lambda s, m: None)

            terminal_instance = AsyncioTerminal(
                user=terminal_user,
                path="",
                session=terminal_id,
                socket=None,
                uri="",
                render_string=None,
                broadcast=lambda s, m: broadcast(s, m),
                login=False,
                pam_profile="",
            )

            await terminal_instance.start_pty()
            logger.info(f"実ターミナルセッションを作成しました: {terminal_id}")
        except Exception as e:
            logger.error(f"ターミナルセッション作成に失敗: {e}")
            raise

        return terminal_id

    async def _destroy_terminal_session(self, terminal_id: str) -> None:
        """AsyncioTerminal.close()を呼び出してセッションを破棄"""
        from aetherterm.agentserver.terminals.asyncio_terminal import AsyncioTerminal

        terminal = AsyncioTerminal.sessions.get(terminal_id)
        if terminal and not terminal.closed:
            await terminal.close()
            logger.info(f"ターミナルセッションを破棄しました: {terminal_id}")
        else:
            logger.warning(f"ターミナルセッション {terminal_id} が見つからないか既にクローズ済み")

    async def _start_agent(self, pane: AgentPane) -> None:
        """エージェントを起動"""
        logger.info(f"エージェントを起動します: {pane.agent_id}")

        # エージェント起動コマンドを送信
        if pane.terminal_id and self._terminal_manager:
            # エージェントタイプに応じたコマンドを実行
            if pane.agent_type == "openhands":
                command = "openhands-agent --pane-mode"
            else:
                command = f"{pane.agent_type}-agent"

            # ターミナルにコマンドを送信
            # 実際の実装はAgentServerとの統合時に行う
            logger.debug(f"エージェント起動コマンド: {command}")

    async def _stop_agent(self, pane: AgentPane) -> None:
        """エージェントを停止"""
        logger.info(f"エージェントを停止します: {pane.agent_id}")
        pane.status = "stopped"

    async def _execute_callback(self, callback: Callable, *args) -> None:
        """コールバックを実行（同期/非同期対応）"""
        if asyncio.iscoroutinefunction(callback):
            await callback(*args)
        else:
            callback(*args)


class MessageRouter:
    """メッセージルーター

    エージェント間のメッセージをルーティングします。
    """

    def __init__(self, pane_manager: AgentPaneManager):
        self.pane_manager = pane_manager
        self._routes: Dict[str, List[str]] = {}  # from_pane -> [to_panes]
        self._handlers: Dict[str, Callable[[AgentMessage], None]] = {}

    async def route(self, from_pane: str, to_pane: str, message: AgentMessage) -> bool:
        """メッセージをルーティング

        Args:
            from_pane: 送信元ペーンID
            to_pane: 送信先ペーンID
            message: メッセージ

        Returns:
            bool: ルーティングが成功した場合True
        """
        # 送信先ペーンを確認
        target_pane = self.pane_manager.get_pane(to_pane)
        if not target_pane:
            # エージェントIDで検索
            target_pane = self.pane_manager.get_pane_by_agent(to_pane)
            if not target_pane:
                logger.warning(f"送信先ペーンが見つかりません: {to_pane}")
                return False

        # メッセージを配信
        handler = self._handlers.get(target_pane.pane_id)
        if handler:
            try:
                await self._execute_handler(handler, message)
                return True
            except Exception as e:
                logger.error(f"メッセージハンドラー実行中にエラー: {e}")
                return False

        # デフォルトの配信方法（WebSocket経由など）
        # 実際の実装はAgentServerとの統合時に行う
        logger.debug(f"メッセージをルーティング: {from_pane} -> {to_pane}")
        return True

    def register_handler(self, pane_id: str, handler: Callable[[AgentMessage], None]) -> None:
        """メッセージハンドラーを登録"""
        self._handlers[pane_id] = handler

    def unregister_handler(self, pane_id: str) -> None:
        """メッセージハンドラーを解除"""
        self._handlers.pop(pane_id, None)

    async def _execute_handler(
        self, handler: Callable[[AgentMessage], None], message: AgentMessage
    ) -> None:
        """ハンドラーを実行（同期/非同期対応）"""
        if asyncio.iscoroutinefunction(handler):
            await handler(message)
        else:
            handler(message)
