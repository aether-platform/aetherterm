"""セッション管理サービス

ターミナルセッションの管理、セッションIDの追跡、
セッション間の独立性確保、およびAetherTermサーバーとの連携を行います。
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import socketio

from ..config import SessionConfig
from ..domain.models import WrapperSession
from ..utils import AsyncTimer, generate_session_id, safe_read_file, safe_write_file

logger = logging.getLogger(__name__)


class SessionService:
    """セッション管理サービス

    ローカルセッション管理に加えて、AetherTermサーバーとの連携により
    WebSocketを通じてセッション情報を同期し、フロントエンドから
    セッション状態を確認できるようにします。
    """

    def __init__(
        self,
        config: SessionConfig,
        aetherterm_server_url: str = "http://localhost:57575",
        sync_callback: Optional[Callable] = None,
    ):
        self.config = config
        self._sessions: Dict[str, WrapperSession] = {}
        self._pid_to_session: Dict[int, str] = {}
        self._cleanup_timer: Optional[AsyncTimer] = None
        self._persistence_path = Path("/tmp/aetherterm_sessions.json")

        # AetherTermサーバーとの連携設定
        self.aetherterm_server_url = aetherterm_server_url
        self.sync_callback = sync_callback
        self._socket_client: Optional[socketio.AsyncClient] = None
        self._sync_enabled = False
        self._sync_timer: Optional[AsyncTimer] = None

        # 永続化が有効な場合は既存セッションを復元
        if self.config.enable_persistence:
            self._load_sessions()

    async def start(self) -> None:
        """セッション管理を開始"""
        logger.info("セッション管理を開始します")

        # クリーンアップタイマーを開始
        if self._cleanup_timer is None:
            self._cleanup_timer = AsyncTimer(
                interval=self.config.cleanup_interval, callback=self._cleanup_expired_sessions
            )
            await self._cleanup_timer.start()

        # AetherTermサーバーとの連携を開始
        await self._start_aetherterm_sync()

    async def stop(self) -> None:
        """セッション管理を停止"""
        logger.info("セッション管理を停止します")

        # AetherTermサーバーとの連携を停止
        await self._stop_aetherterm_sync()

        # クリーンアップタイマーを停止
        if self._cleanup_timer is not None:
            await self._cleanup_timer.stop()
            self._cleanup_timer = None

        # 同期タイマーを停止
        if self._sync_timer is not None:
            await self._sync_timer.stop()
            self._sync_timer = None

        # セッション情報を永続化
        if self.config.enable_persistence:
            self._save_sessions()

    def create_session(self, pid: int, **kwargs) -> str:
        """新しいセッションを作成

        Args:
            pid: プロセスID
            **kwargs: 追加のセッション情報

        Returns:
            str: セッションID

        Raises:
            RuntimeError: 最大セッション数に達している場合
        """
        if len(self._sessions) >= self.config.max_sessions:
            raise RuntimeError(f"最大セッション数に達しています: {self.config.max_sessions}")

        session_id = generate_session_id()
        now = datetime.now()

        # 環境変数を取得
        environment = dict(os.environ)

        session_info = WrapperSession(
            wrapper_id=session_id,
            aetherterm_session_id=kwargs.get("aetherterm_session_id", ""),
            wrapper_pid=os.getpid(),
            shell_pid=pid,
            created_at=now,
            last_activity=now,
            terminal_size=kwargs.get("terminal_size", (24, 80)),
            environment=environment,
            metadata=kwargs.get("metadata", {}),
        )

        self._sessions[session_id] = session_info
        self._pid_to_session[pid] = session_id

        logger.info(f"新しいセッションを作成しました: {session_id} (PID: {pid})")

        # 永続化
        if self.config.enable_persistence:
            self._save_sessions()

        # AetherTermサーバーに同期
        asyncio.create_task(self._sync_session_to_aetherterm(session_info, "created"))

        return session_id

    def get_session(self, session_id: str) -> Optional[WrapperSession]:
        """セッション情報を取得

        Args:
            session_id: セッションID

        Returns:
            Optional[WrapperSession]: セッション情報（存在しない場合はNone）
        """
        session = self._sessions.get(session_id)
        if session:
            session.update_activity()
        return session

    def get_session_by_pid(self, pid: int) -> Optional[WrapperSession]:
        """PIDからセッション情報を取得

        Args:
            pid: プロセスID

        Returns:
            Optional[WrapperSession]: セッション情報（存在しない場合はNone）
        """
        session_id = self._pid_to_session.get(pid)
        if session_id:
            return self.get_session(session_id)
        return None

    def update_session(self, session_id: str, **kwargs) -> bool:
        """セッション情報を更新

        Args:
            session_id: セッションID
            **kwargs: 更新する情報

        Returns:
            bool: 更新に成功した場合True
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        # 更新可能な属性
        if "terminal_size" in kwargs:
            session.terminal_size = kwargs["terminal_size"]

        if "metadata" in kwargs:
            session.metadata.update(kwargs["metadata"])

        if "status" in kwargs:
            session.status = kwargs["status"]

        session.update_activity()

        # 永続化
        if self.config.enable_persistence:
            self._save_sessions()

        # AetherTermサーバーに同期
        asyncio.create_task(self._sync_session_to_aetherterm(session, "updated"))

        return True

    def remove_session(self, session_id: str) -> bool:
        """セッションを削除

        Args:
            session_id: セッションID

        Returns:
            bool: 削除に成功した場合True
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        # セッション状態を更新してから削除
        session.status = "closed"

        # AetherTermサーバーに同期（削除前に通知）
        asyncio.create_task(self._sync_session_to_aetherterm(session, "closed"))

        # マッピングから削除
        self._pid_to_session.pop(session.shell_pid, None)
        self._sessions.pop(session_id, None)

        logger.info(f"セッションを削除しました: {session_id}")

        # 永続化
        if self.config.enable_persistence:
            self._save_sessions()

        return True

    def list_sessions(self) -> List[WrapperSession]:
        """全セッションのリストを取得

        Returns:
            List[WrapperSession]: セッション情報のリスト
        """
        return list(self._sessions.values())

    def get_active_sessions(self) -> List[WrapperSession]:
        """アクティブなセッションのリストを取得

        Returns:
            List[WrapperSession]: アクティブなセッション情報のリスト
        """
        active_sessions = []
        for session in self._sessions.values():
            if not session.is_expired(self.config.session_timeout):
                active_sessions.append(session)
        return active_sessions

    def get_session_count(self) -> int:
        """現在のセッション数を取得"""
        return len(self._sessions)

    async def _cleanup_expired_sessions(self) -> None:
        """期限切れセッションのクリーンアップ"""
        expired_sessions = []

        for session_id, session in self._sessions.items():
            if session.is_expired(self.config.session_timeout):
                expired_sessions.append(session_id)

        if expired_sessions:
            logger.info(f"期限切れセッションをクリーンアップします: {len(expired_sessions)}個")

            for session_id in expired_sessions:
                self.remove_session(session_id)

    def _save_sessions(self) -> None:
        """セッション情報を永続化"""
        try:
            sessions_data = {
                session_id: session.to_dict() for session_id, session in self._sessions.items()
            }

            content = json.dumps(sessions_data, indent=2, ensure_ascii=False)

            if not safe_write_file(self._persistence_path, content):
                logger.error("セッション情報の永続化に失敗しました")

        except Exception as e:
            logger.error(f"セッション情報の永続化でエラーが発生しました: {e}")

    def _load_sessions(self) -> None:
        """永続化されたセッション情報を復元"""
        try:
            content = safe_read_file(self._persistence_path)
            if not content:
                return

            sessions_data = json.loads(content)

            for session_id, session_dict in sessions_data.items():
                try:
                    session = WrapperSession.from_dict(session_dict)

                    # プロセスがまだ実行中かチェック
                    from ..utils import is_process_running

                    if is_process_running(session.shell_pid):
                        self._sessions[session_id] = session
                        self._pid_to_session[session.shell_pid] = session_id
                        logger.debug(f"セッションを復元しました: {session_id}")
                    else:
                        logger.debug(
                            f"プロセスが終了しているためセッションをスキップ: {session_id}"
                        )

                except Exception as e:
                    logger.warning(f"セッション {session_id} の復元に失敗しました: {e}")

            logger.info(f"セッション情報を復元しました: {len(self._sessions)}個")

        except Exception as e:
            logger.error(f"セッション情報の復元でエラーが発生しました: {e}")

    def get_session_stats(self) -> Dict[str, Any]:
        """セッション統計情報を取得"""
        active_sessions = self.get_active_sessions()

        return {
            "total_sessions": len(self._sessions),
            "active_sessions": len(active_sessions),
            "max_sessions": self.config.max_sessions,
            "session_timeout": self.config.session_timeout,
            "oldest_session": min((s.created_at for s in self._sessions.values()), default=None),
            "newest_session": max((s.created_at for s in self._sessions.values()), default=None),
        }

    async def _start_aetherterm_sync(self) -> None:
        """AetherTermサーバーとの同期を開始"""
        try:
            self._socket_client = socketio.AsyncClient(
                reconnection=True,
                reconnection_attempts=5,
                reconnection_delay=1,
                reconnection_delay_max=5,
            )

            # イベントハンドラーを登録
            @self._socket_client.event
            async def connect():
                logger.info("AetherTermサーバーに接続しました")
                self._sync_enabled = True
                # 既存セッションを同期
                await self._sync_all_sessions()

            @self._socket_client.event
            async def disconnect():
                logger.warning("AetherTermサーバーから切断されました")
                self._sync_enabled = False

            @self._socket_client.event
            async def wrapper_session_sync_response(data):
                logger.debug(f"セッション同期レスポンス: {data}")

            # サーバーに接続
            await self._socket_client.connect(self.aetherterm_server_url)

            # 定期同期タイマーを開始
            if self._sync_timer is None:
                self._sync_timer = AsyncTimer(
                    interval=30,  # 30秒ごとに同期
                    callback=self._periodic_sync,
                )
                await self._sync_timer.start()

        except Exception as e:
            logger.error(f"AetherTermサーバーとの同期開始に失敗しました: {e}")
            self._sync_enabled = False

    async def _stop_aetherterm_sync(self) -> None:
        """AetherTermサーバーとの同期を停止"""
        try:
            if self._socket_client and self._socket_client.connected:
                await self._socket_client.disconnect()
            self._sync_enabled = False
            logger.info("AetherTermサーバーとの同期を停止しました")
        except Exception as e:
            logger.error(f"AetherTermサーバーとの同期停止に失敗しました: {e}")

    async def _sync_session_to_aetherterm(self, session: WrapperSession, action: str) -> None:
        """セッション情報をAetherTermサーバーに同期"""
        if not self._sync_enabled or not self._socket_client:
            return

        try:
            sync_data = {
                "action": action,  # created, updated, closed
                "session": session.to_dict(),
                "timestamp": datetime.now().isoformat(),
                "wrapper_info": {
                    "pid": os.getpid(),
                    "hostname": os.uname().nodename,
                },
            }

            await self._socket_client.emit("wrapper_session_sync", sync_data)
            logger.debug(f"セッション同期送信: {session.session_id} ({action})")

        except Exception as e:
            logger.error(f"セッション同期に失敗しました: {e}")

    async def _sync_all_sessions(self) -> None:
        """全セッションをAetherTermサーバーに同期"""
        if not self._sync_enabled:
            return

        try:
            sessions_data = {
                "action": "bulk_sync",
                "sessions": [session.to_dict() for session in self._sessions.values()],
                "timestamp": datetime.now().isoformat(),
                "wrapper_info": {
                    "pid": os.getpid(),
                    "hostname": os.uname().nodename,
                },
            }

            await self._socket_client.emit("wrapper_session_sync", sessions_data)
            logger.info(f"全セッション同期完了: {len(self._sessions)}個")

        except Exception as e:
            logger.error(f"全セッション同期に失敗しました: {e}")

    async def _periodic_sync(self) -> None:
        """定期的なセッション同期"""
        if self._sync_enabled:
            await self._sync_all_sessions()

    def enable_aetherterm_sync(self, server_url: str = None) -> None:
        """AetherTermサーバーとの同期を有効化"""
        if server_url:
            self.aetherterm_server_url = server_url

        if not self._sync_enabled:
            asyncio.create_task(self._start_aetherterm_sync())

    def disable_aetherterm_sync(self) -> None:
        """AetherTermサーバーとの同期を無効化"""
        if self._sync_enabled:
            asyncio.create_task(self._stop_aetherterm_sync())

    def get_sync_status(self) -> Dict[str, Any]:
        """同期状態を取得"""
        return {
            "sync_enabled": self._sync_enabled,
            "server_url": self.aetherterm_server_url,
            "connected": self._socket_client.connected if self._socket_client else False,
            "last_sync": datetime.now().isoformat() if self._sync_enabled else None,
        }
