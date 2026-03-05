"""OpenHandsエージェント実装

OpenHandsとの統合を提供し、コード生成、編集、デバッグなどの
高度な開発タスクを実行します。
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

import aiohttp

from .base import (
    AgentCapability,
    AgentInterface,
    AgentResult,
    AgentTask,
    InterventionType,
    TaskStatus,
    UserIntervention,
)

logger = logging.getLogger(__name__)


class OpenHandsAgent(AgentInterface):
    """OpenHandsエージェント

    OpenHandsサービスと通信し、高度な開発タスクを実行します。
    WebSocket/HTTPベースの通信を使用し、リアルタイムの進捗更新と
    ユーザー介入をサポートします。
    """

    CAPABILITIES = [
        AgentCapability.CODE_GENERATION,
        AgentCapability.CODE_EDITING,
        AgentCapability.CODE_REVIEW,
        AgentCapability.DEBUGGING,
        AgentCapability.TESTING,
        AgentCapability.DOCUMENTATION,
    ]

    def __init__(self, agent_id: str = "openhands", endpoint: str = "http://localhost:3000"):
        super().__init__(agent_id, self.CAPABILITIES)
        self.endpoint = endpoint
        self.ws_endpoint = endpoint.replace("http://", "ws://").replace("https://", "wss://")
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_connection: Optional[aiohttp.ClientWebSocketResponse] = None
        self._intervention_responses: Dict[UUID, asyncio.Event] = {}
        self._intervention_results: Dict[UUID, Any] = {}
        self._connected = False

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """OpenHandsエージェントを初期化"""
        try:
            # 設定を更新
            self.endpoint = config.get("endpoint", self.endpoint)
            self.ws_endpoint = self.endpoint.replace("http://", "ws://").replace(
                "https://", "wss://"
            )

            # HTTPセッションを作成
            self._session = aiohttp.ClientSession()

            # WebSocket接続を確立
            await self._connect_websocket()

            logger.info(f"OpenHandsエージェントを初期化しました: {self.endpoint}")
            return True

        except Exception as e:
            logger.error(f"OpenHandsエージェントの初期化に失敗しました: {e}")
            return False

    async def shutdown(self) -> None:
        """OpenHandsエージェントをシャットダウン"""
        try:
            # WebSocket接続を閉じる
            if self._ws_connection and not self._ws_connection.closed:
                await self._ws_connection.close()

            # HTTPセッションを閉じる
            if self._session and not self._session.closed:
                await self._session.close()

            self._connected = False
            logger.info("OpenHandsエージェントをシャットダウンしました")

        except Exception as e:
            logger.error(f"OpenHandsエージェントのシャットダウン中にエラー: {e}")

    async def execute_task(self, task: AgentTask) -> AgentResult:
        """タスクを実行"""
        result = AgentResult(task_id=task.id)
        start_time = datetime.utcnow()

        try:
            # タスクを開始
            task.status = TaskStatus.RUNNING
            task.started_at = start_time
            self._running_tasks[task.id] = task

            # OpenHandsにタスクを送信
            response = await self._submit_task_to_openhands(task)

            if not response.get("success"):
                raise Exception(response.get("error", "Unknown error"))

            # タスク実行を監視
            openhands_task_id = response.get("task_id")
            final_result = await self._monitor_task_execution(task, openhands_task_id)

            # 結果を構築
            result.success = final_result.get("success", False)
            result.output = final_result.get("output")
            result.logs = final_result.get("logs", [])
            result.artifacts = final_result.get("artifacts", {})

            # タスクを完了
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()

        except asyncio.CancelledError:
            # タスクがキャンセルされた
            task.status = TaskStatus.CANCELLED
            result.success = False
            result.error = "Task was cancelled"
            raise

        except Exception as e:
            # エラーが発生
            task.status = TaskStatus.FAILED
            result.success = False
            result.error = str(e)
            logger.error(f"タスク実行中にエラー: {e}")

        finally:
            # クリーンアップ
            if task.id in self._running_tasks:
                del self._running_tasks[task.id]

            # 実行時間を記録
            result.execution_time_seconds = (datetime.utcnow() - start_time).total_seconds()

        return result

    async def cancel_task(self, task_id: UUID) -> bool:
        """実行中のタスクをキャンセル"""
        try:
            if task_id not in self._running_tasks:
                return False

            # OpenHandsにキャンセル要求を送信
            async with self._session.post(
                f"{self.endpoint}/api/tasks/{task_id}/cancel"
            ) as response:
                if response.status == 200:
                    task = self._running_tasks.get(task_id)
                    if task:
                        task.status = TaskStatus.CANCELLED
                    return True

            return False

        except Exception as e:
            logger.error(f"タスクキャンセル中にエラー: {e}")
            return False

    async def get_task_status(self, task_id: UUID) -> Optional[TaskStatus]:
        """タスクの現在の状態を取得"""
        task = self._running_tasks.get(task_id)
        return task.status if task else None

    async def get_task_progress(self, task_id: UUID) -> Optional[float]:
        """タスクの進捗を取得"""
        try:
            # OpenHandsから進捗を取得
            async with self._session.get(
                f"{self.endpoint}/api/tasks/{task_id}/progress"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("progress", 0.0)

            return None

        except Exception as e:
            logger.error(f"進捗取得中にエラー: {e}")
            return None

    async def _connect_websocket(self) -> None:
        """WebSocket接続を確立"""
        try:
            self._ws_connection = await self._session.ws_connect(f"{self.ws_endpoint}/ws")
            self._connected = True

            # メッセージ受信タスクを開始
            asyncio.create_task(self._handle_websocket_messages())

        except Exception as e:
            logger.error(f"WebSocket接続に失敗: {e}")
            self._connected = False
            raise

    async def _handle_websocket_messages(self) -> None:
        """WebSocketメッセージを処理"""
        try:
            async for msg in self._ws_connection:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._process_websocket_message(data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocketエラー: {self._ws_connection.exception()}")

        except Exception as e:
            logger.error(f"WebSocketメッセージ処理中にエラー: {e}")
        finally:
            self._connected = False

    async def _process_websocket_message(self, data: Dict[str, Any]) -> None:
        """WebSocketメッセージを処理"""
        msg_type = data.get("type")

        if msg_type == "progress":
            # 進捗更新
            task_id = UUID(data.get("task_id"))
            progress = data.get("progress", 0.0)
            message = data.get("message", "")
            await self.report_progress(task_id, progress, message)

        elif msg_type == "intervention_required":
            # ユーザー介入が必要
            task_id = UUID(data.get("task_id"))
            intervention_data = data.get("intervention")
            await self._handle_intervention_request(task_id, intervention_data)

        elif msg_type == "log":
            # ログメッセージ
            task_id = UUID(data.get("task_id"))
            log_message = data.get("message")
            # ログを記録（実装は省略）

    async def _submit_task_to_openhands(self, task: AgentTask) -> Dict[str, Any]:
        """OpenHandsにタスクを送信"""
        payload = {
            "task_id": str(task.id),
            "type": task.type,
            "description": task.description,
            "context": task.context,
            "capabilities": [cap.value for cap in task.capabilities_required],
            "priority": task.priority,
            "timeout": task.timeout_seconds,
            "allow_intervention": task.allow_user_intervention,
        }

        async with self._session.post(f"{self.endpoint}/api/tasks", json=payload) as response:
            if response.status == 200:
                return await response.json()
            error_text = await response.text()
            raise Exception(f"Failed to submit task: {error_text}")

    async def _monitor_task_execution(
        self, task: AgentTask, openhands_task_id: str
    ) -> Dict[str, Any]:
        """タスク実行を監視"""
        while task.status == TaskStatus.RUNNING:
            try:
                # タスク状態を確認
                async with self._session.get(
                    f"{self.endpoint}/api/tasks/{openhands_task_id}"
                ) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data.get("status") == "completed":
                            return data.get("result", {})
                        if data.get("status") == "failed":
                            raise Exception(data.get("error", "Task failed"))

                # 短時間待機
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"タスク監視中にエラー: {e}")
                raise

        return {}

    async def _handle_intervention_request(
        self, task_id: UUID, intervention_data: Dict[str, Any]
    ) -> None:
        """介入要求を処理"""
        intervention = UserIntervention(
            type=InterventionType(intervention_data.get("type", "approval")),
            message=intervention_data.get("message", ""),
            options=intervention_data.get("options", []),
            context=intervention_data.get("context", {}),
            timeout_seconds=intervention_data.get("timeout"),
        )

        # ユーザー介入を要求
        response = await self.request_user_intervention(task_id, intervention)

        # OpenHandsに応答を送信
        await self._send_intervention_response(task_id, intervention.id, response)

    async def _send_intervention_response(
        self, task_id: UUID, intervention_id: UUID, response: Any
    ) -> None:
        """介入応答をOpenHandsに送信"""
        payload = {
            "task_id": str(task_id),
            "intervention_id": str(intervention_id),
            "response": response,
        }

        if self._ws_connection and not self._ws_connection.closed:
            await self._ws_connection.send_json(
                {"type": "intervention_response", "payload": payload}
            )

    async def _wait_for_intervention_response(self, intervention: UserIntervention) -> Any:
        """介入応答を待つ"""
        # イベントを作成
        event = asyncio.Event()
        self._intervention_responses[intervention.id] = event

        try:
            # タイムアウト付きで待機
            if intervention.timeout_seconds:
                await asyncio.wait_for(event.wait(), intervention.timeout_seconds)
            else:
                await event.wait()

            # 応答を取得
            return self._intervention_results.get(intervention.id)

        except asyncio.TimeoutError:
            logger.warning(f"介入応答がタイムアウトしました: {intervention.id}")
            return None

        finally:
            # クリーンアップ
            self._intervention_responses.pop(intervention.id, None)
            self._intervention_results.pop(intervention.id, None)

    def resolve_intervention(self, intervention_id: UUID, response: Any) -> None:
        """介入を解決（外部から呼び出される）"""
        event = self._intervention_responses.get(intervention_id)
        if event:
            self._intervention_results[intervention_id] = response
            event.set()
