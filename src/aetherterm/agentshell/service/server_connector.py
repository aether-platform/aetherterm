"""
AetherTermサーバーコネクター

AetherTermサーバーとのオプショナルな連携を管理します。
サーバーがない場合でもAI機能は独立して動作します。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import socketio

from ...common.agent_protocol import AgentMessage, MessageType
from ..domain.models import WrapperSession

logger = logging.getLogger(__name__)


class ServerConnector:
    """
    AetherTermサーバーとのオプショナル連携

    サーバーが利用可能な場合のみ接続し、
    セッション情報の同期やフロントエンドとの連携を行います。
    """

    def __init__(
        self,
        server_url: str = "http://localhost:57575",
        auto_connect: bool = True,
        retry_interval: int = 5,
        max_retries: int = 5,
    ):
        self.server_url = server_url
        self.auto_connect = auto_connect
        self.retry_interval = retry_interval
        self.max_retries = max_retries

        self._socket_client: Optional[socketio.AsyncClient] = None
        self._is_connected = False
        self._is_enabled = False
        self._retry_count = 0
        self._reconnect_task: Optional[asyncio.Task] = None
        self._sync_callbacks: List[Callable] = []
        self._message_handlers: Dict[MessageType, List[Callable[[AgentMessage], None]]] = {}
        self.session_id: str = "default"

    async def start(self) -> bool:
        """
        サーバー連携を開始

        Returns:
            bool: 接続に成功した場合True、失敗またはスキップした場合False
        """
        if not self.auto_connect:
            logger.info("サーバー連携は無効化されています")
            return False

        logger.info(f"AetherTermサーバーへの接続を試行します: {self.server_url}")

        try:
            await self._connect()
            if self._is_connected:
                logger.info("AetherTermサーバーとの連携を開始しました")
                self._is_enabled = True
                return True
            logger.warning("AetherTermサーバーへの接続に失敗しました")
            return False
        except Exception as e:
            logger.error(f"サーバー連携の開始に失敗しました: {e}")
            return False

    async def stop(self) -> None:
        """サーバー連携を停止"""
        logger.info("AetherTermサーバーとの連携を停止します")

        self._is_enabled = False

        # 再接続タスクをキャンセル
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        # ソケット接続を切断
        if self._socket_client and self._socket_client.connected:
            await self._socket_client.disconnect()

        self._is_connected = False
        logger.info("AetherTermサーバーとの連携を停止しました")

    async def sync_session(self, session: WrapperSession, action: str) -> bool:
        """
        セッション情報をサーバーに同期

        Args:
            session: セッション情報
            action: アクション（created, updated, closed）

        Returns:
            bool: 同期に成功した場合True
        """
        if not self._is_enabled or not self._is_connected:
            logger.debug("サーバー連携が無効または未接続のため、セッション同期をスキップします")
            return False

        try:
            sync_data = {
                "action": action,
                "session": session.to_dict(),
                "timestamp": datetime.now().isoformat(),
                "wrapper_info": {
                    "pid": session.wrapper_pid,
                    "hostname": session.environment.get("HOSTNAME", "unknown"),
                },
            }

            await self._socket_client.emit("wrapper_session_sync", sync_data)
            logger.debug(f"セッション同期送信: {session.wrapper_id} ({action})")
            return True

        except Exception as e:
            logger.error(f"セッション同期に失敗しました: {e}")
            return False

    async def sync_all_sessions(self, sessions: List[WrapperSession]) -> bool:
        """
        全セッションをサーバーに同期

        Args:
            sessions: セッション情報のリスト

        Returns:
            bool: 同期に成功した場合True
        """
        if not self._is_enabled or not self._is_connected:
            logger.debug("サーバー連携が無効または未接続のため、全セッション同期をスキップします")
            return False

        try:
            sessions_data = {
                "action": "bulk_sync",
                "sessions": [session.to_dict() for session in sessions],
                "timestamp": datetime.now().isoformat(),
                "wrapper_info": {
                    "pid": sessions[0].wrapper_pid if sessions else 0,
                    "hostname": sessions[0].environment.get("HOSTNAME", "unknown")
                    if sessions
                    else "unknown",
                },
            }

            await self._socket_client.emit("wrapper_session_sync", sessions_data)
            logger.info(f"全セッション同期完了: {len(sessions)}個")
            return True

        except Exception as e:
            logger.error(f"全セッション同期に失敗しました: {e}")
            return False

    async def send_ai_notification(
        self, session_id: str, notification_type: str, data: Dict[str, Any]
    ) -> bool:
        """
        AI通知をサーバーに送信

        Args:
            session_id: セッションID
            notification_type: 通知タイプ（error, warning, suggestion）
            data: 通知データ

        Returns:
            bool: 送信に成功した場合True
        """
        if not self._is_enabled or not self._is_connected:
            logger.debug("サーバー連携が無効または未接続のため、AI通知をスキップします")
            return False

        try:
            notification_data = {
                "session_id": session_id,
                "type": notification_type,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }

            await self._socket_client.emit("ai_notification", notification_data)
            logger.debug(f"AI通知送信: {session_id} ({notification_type})")
            return True

        except Exception as e:
            logger.error(f"AI通知の送信に失敗しました: {e}")
            return False

    def register_sync_callback(self, callback: Callable) -> None:
        """同期コールバックを登録"""
        if callback not in self._sync_callbacks:
            self._sync_callbacks.append(callback)

    def unregister_sync_callback(self, callback: Callable) -> None:
        """同期コールバックを解除"""
        if callback in self._sync_callbacks:
            self._sync_callbacks.remove(callback)

    def is_connected(self) -> bool:
        """接続状態を確認"""
        return self._is_connected and self._is_enabled

    def is_enabled(self) -> bool:
        """連携が有効かどうかを確認"""
        return self._is_enabled

    def get_status(self) -> Dict[str, Any]:
        """連携状態を取得"""
        return {
            "enabled": self._is_enabled,
            "connected": self._is_connected,
            "server_url": self.server_url,
            "auto_connect": self.auto_connect,
            "retry_count": self._retry_count,
            "max_retries": self.max_retries,
        }

    async def _connect(self) -> None:
        """サーバーに接続"""
        try:
            self._socket_client = socketio.AsyncClient(
                reconnection=False,  # 手動で再接続を管理
                logger=False,
                engineio_logger=False,
            )

            # イベントハンドラーを登録
            self._setup_event_handlers()

            # 接続試行（タイムアウト付き）
            await asyncio.wait_for(self._socket_client.connect(self.server_url), timeout=10.0)

            self._is_connected = True
            self._retry_count = 0

        except asyncio.TimeoutError:
            logger.warning("AetherTermサーバーへの接続がタイムアウトしました")
            self._is_connected = False
            await self._schedule_reconnect()
        except Exception as e:
            logger.warning(f"AetherTermサーバーへの接続に失敗しました: {e}")
            self._is_connected = False
            await self._schedule_reconnect()

    def _setup_event_handlers(self) -> None:
        """SocketIOイベントハンドラーを設定"""

        @self._socket_client.event
        async def connect():
            logger.info("AetherTermサーバーに接続しました")
            self._is_connected = True
            self._retry_count = 0

            # 同期コールバックを実行
            for callback in self._sync_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback("connected")
                    else:
                        callback("connected")
                except Exception as e:
                    logger.error(f"同期コールバックの実行に失敗しました: {e}")

        @self._socket_client.event
        async def disconnect():
            logger.warning("AetherTermサーバーから切断されました")
            self._is_connected = False

            # 同期コールバックを実行
            for callback in self._sync_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback("disconnected")
                    else:
                        callback("disconnected")
                except Exception as e:
                    logger.error(f"同期コールバックの実行に失敗しました: {e}")

            # 再接続をスケジュール
            if self._is_enabled:
                await self._schedule_reconnect()

        @self._socket_client.event
        async def wrapper_session_sync_response(data):
            logger.debug(f"セッション同期レスポンス: {data}")

        @self._socket_client.event
        async def ai_notification_response(data):
            logger.debug(f"AI通知レスポンス: {data}")

        @self._socket_client.event
        async def server_command(data):
            """サーバーからのコマンド受信"""
            logger.info(f"サーバーコマンド受信: {data}")

            # 同期コールバックを実行
            for callback in self._sync_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback("server_command", data)
                    else:
                        callback("server_command", data)
                except Exception as e:
                    logger.error(f"サーバーコマンドコールバックの実行に失敗しました: {e}")

        @self._socket_client.event
        async def agent_message(data):
            """エージェントメッセージを受信"""
            try:
                message = AgentMessage.from_dict(data)
                await self._handle_agent_message(message)
            except Exception as e:
                logger.error(f"エージェントメッセージの処理に失敗しました: {e}")

    async def _schedule_reconnect(self) -> None:
        """再接続をスケジュール"""
        if self._retry_count >= self.max_retries:
            logger.error("最大再試行回数に達しました。サーバー連携を無効化します。")
            self._is_enabled = False
            return

        if self._reconnect_task and not self._reconnect_task.done():
            return  # 既に再接続タスクが実行中

        self._retry_count += 1
        logger.info(
            f"再接続を{self.retry_interval}秒後にスケジュールします（試行回数: {self._retry_count}/{self.max_retries}）"
        )

        self._reconnect_task = asyncio.create_task(self._reconnect_after_delay())

    async def _reconnect_after_delay(self) -> None:
        """遅延後に再接続"""
        try:
            await asyncio.sleep(self.retry_interval)
            if self._is_enabled:  # まだ有効な場合のみ再接続
                await self._connect()
        except asyncio.CancelledError:
            logger.debug("再接続タスクがキャンセルされました")
        except Exception as e:
            logger.error(f"再接続中にエラーが発生しました: {e}")

    def enable(self) -> None:
        """サーバー連携を有効化"""
        if not self._is_enabled:
            self._is_enabled = True
            self._retry_count = 0
            if self.auto_connect:
                asyncio.create_task(self._connect())

    def disable(self) -> None:
        """サーバー連携を無効化"""
        if self._is_enabled:
            self._is_enabled = False
            asyncio.create_task(self.stop())

    @staticmethod
    def create_connector(
        transport: str = "socketio",
        **kwargs,
    ) -> "ServerConnector":
        """
        ファクトリメソッド: transport指定でコネクターを生成

        Args:
            transport: "socketio" (デフォルト) or "zmq"
            **kwargs: コネクター固有の設定

        Returns:
            ServerConnector or ZMQAgentConnector
        """
        if transport == "zmq":
            from ..zmq_agent_connector import ZMQAgentConnector
            from ...common.zmq.zmq_config import ZMQConfig

            agent_id = kwargs.get("agent_id", "agentshell_default")
            zmq_config = kwargs.get("zmq_config") or ZMQConfig(enabled=True)
            capabilities = kwargs.get("capabilities", [])

            return ZMQAgentConnector(
                agent_id=agent_id,
                zmq_config=zmq_config,
                capabilities=capabilities,
            )
        else:
            return ServerConnector(
                server_url=kwargs.get("server_url", "http://localhost:57575"),
                auto_connect=kwargs.get("auto_connect", True),
                retry_interval=kwargs.get("retry_interval", 5),
                max_retries=kwargs.get("max_retries", 5),
            )

    async def send_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """
        エージェントメッセージを送信
        
        Args:
            message: 送信するメッセージ
            
        Returns:
            Optional[AgentMessage]: 応答メッセージ（同期的な場合）
        """
        if not self.is_connected():
            logger.warning("サーバーに接続されていません。メッセージを送信できません。")
            return None
        
        try:
            # メッセージを送信
            await self._socket_client.emit("agent_message", message.to_dict())
            logger.debug(f"エージェントメッセージを送信しました: {message.message_type}")
            
            # 同期的な応答は現時点では実装しない（非同期通信のため）
            return None
            
        except Exception as e:
            logger.error(f"メッセージ送信中にエラーが発生しました: {e}")
            return None
    
    def register_handler(
        self,
        message_type: MessageType,
        handler: Callable[[AgentMessage], None]
    ) -> None:
        """
        メッセージハンドラーを登録
        
        Args:
            message_type: メッセージタイプ
            handler: ハンドラー関数
        """
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        
        if handler not in self._message_handlers[message_type]:
            self._message_handlers[message_type].append(handler)
            logger.debug(f"メッセージハンドラーを登録しました: {message_type}")
    
    def unregister_handler(
        self,
        message_type: MessageType,
        handler: Callable[[AgentMessage], None]
    ) -> None:
        """
        メッセージハンドラーを解除
        
        Args:
            message_type: メッセージタイプ
            handler: ハンドラー関数
        """
        if message_type in self._message_handlers:
            if handler in self._message_handlers[message_type]:
                self._message_handlers[message_type].remove(handler)
                logger.debug(f"メッセージハンドラーを解除しました: {message_type}")
    
    async def _handle_agent_message(self, message: AgentMessage) -> None:
        """
        受信したエージェントメッセージを処理
        
        Args:
            message: 受信したメッセージ
        """
        handlers = self._message_handlers.get(message.message_type, [])
        
        if not handlers:
            logger.warning(f"未処理のメッセージタイプ: {message.message_type}")
            return
        
        # すべてのハンドラーを実行
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.error(f"メッセージハンドラー実行中にエラー: {e}")
