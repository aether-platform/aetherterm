"""
エージェントオーケストレーター

AgentShellからAgentServerへの通信を管理し、
子エージェントの作成、監視、介入処理を調整します。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID, uuid4

from ...common.agent_protocol import (
    AgentMessage,
    InterventionRequest,
    InterventionResponse,
    MessageBuilder,
    MessageType,
    PaneConfig,
    PaneType,
    ProgressUpdate,
    TaskCreateRequest,
)
from ...common.report_models import ActivityType, WorkActivity
from ..agents.base import AgentTask, UserIntervention
from .agent_coordinator import AgentCoordinator, ConflictType, CoordinationStrategy
from .server_connector import ServerConnector
# ZMQAgentConnector is also accepted (duck typing via same interface)

logger = logging.getLogger(__name__)


@dataclass
class ChildAgentHandle:
    """子エージェントのハンドル"""
    agent_id: str
    task_id: UUID
    pane_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "running"
    
    
class AgentOrchestrator:
    """
    エージェントオーケストレーター

    エージェント間の連携を管理し、タスクの委譲、
    進捗監視、ユーザー介入の調整を行います。

    server_connectorはServerConnectorまたはZMQAgentConnectorの
    いずれかを受け取ります（同じインターフェースを実装）。
    """

    def __init__(self, server_connector):
        # ServerConnector or ZMQAgentConnector (duck typing)
        self.server_connector = server_connector
        self._agent_id = f"agentshell_{uuid4().hex[:8]}"
        self._child_agents: Dict[str, ChildAgentHandle] = {}
        self._pending_interventions: Dict[UUID, asyncio.Event] = {}
        self._intervention_responses: Dict[UUID, Any] = {}
        
        # コールバック
        self._progress_callbacks: List[Callable[[str, float, str], None]] = []
        self._intervention_callbacks: List[Callable[[UserIntervention], Any]] = []
        self._completion_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        
        # アクティビティレコーダー
        self._activity_recorder: Optional[Any] = None
        
        # エージェントコーディネーター
        self._coordinator = AgentCoordinator()
        
        # メッセージハンドラーを登録
        self._register_message_handlers()
    
    def set_activity_recorder(self, recorder: Any) -> None:
        """アクティビティレコーダーを設定"""
        self._activity_recorder = recorder
    
    async def create_child_agent(
        self,
        agent_type: str,
        task: AgentTask,
        pane_config: Optional[PaneConfig] = None
    ) -> ChildAgentHandle:
        """
        子エージェントを作成
        
        Args:
            agent_type: エージェントタイプ（例: "openhands"）
            task: 実行するタスク
            pane_config: ペーン設定
            
        Returns:
            ChildAgentHandle: 子エージェントのハンドル
        """
        # デフォルトのペーン設定
        if not pane_config:
            pane_config = PaneConfig(
                pane_type=PaneType.AGENT,
                title=f"{agent_type} - {task.type}",
                size={"rows": 30, "cols": 100},
                agent_config={
                    "agent_type": agent_type,
                    "auto_start": True
                }
            )
        
        # タスク作成リクエスト
        request = TaskCreateRequest(
            task_id=task.id,
            agent_type=agent_type,
            task_type=task.type,
            description=task.description,
            context=task.context,
            pane_config=pane_config,
            timeout_seconds=task.timeout_seconds,
            allow_user_intervention=task.allow_user_intervention
        )
        
        # メッセージを送信
        message = MessageBuilder.create_task(
            from_agent=self._agent_id,
            to_agent="agentserver",
            request=request
        )
        
        response = await self.server_connector.send_message(message)
        
        if response and response.message_type == MessageType.TASK_CREATE:
            # 子エージェントハンドルを作成
            pane_id = response.payload.get("pane_id")
            agent_id = response.payload.get("agent_id", f"{agent_type}_{task.id.hex[:8]}")
            
            handle = ChildAgentHandle(
                agent_id=agent_id,
                task_id=task.id,
                pane_id=pane_id
            )
            
            self._child_agents[agent_id] = handle
            
            # アクティビティを記録
            if self._activity_recorder:
                await self._activity_recorder.record_agent_action(
                    session_id=self.server_connector.session_id,
                    agent_id=agent_id,
                    action="エージェント起動",
                    description=f"{agent_type}エージェントを起動: {task.description}",
                    metadata={
                        "task_id": str(task.id),
                        "pane_id": pane_id
                    }
                )
            
            logger.info(f"子エージェント {agent_id} を作成しました（ペーン: {pane_id}）")
            return handle
        else:
            raise Exception("子エージェントの作成に失敗しました")
    
    async def cancel_child_agent(self, agent_id: str) -> bool:
        """
        子エージェントをキャンセル
        
        Args:
            agent_id: エージェントID
            
        Returns:
            bool: キャンセルが成功した場合True
        """
        handle = self._child_agents.get(agent_id)
        if not handle:
            return False
        
        message = AgentMessage(
            from_agent=self._agent_id,
            to_agent=agent_id,
            message_type=MessageType.TASK_CANCEL,
            payload={"task_id": str(handle.task_id)}
        )
        
        response = await self.server_connector.send_message(message)
        
        if response and response.message_type == MessageType.TASK_CANCEL:
            handle.status = "cancelled"
            return True
        
        return False
    
    async def handle_child_progress(
        self,
        agent_id: str,
        progress: float,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        子エージェントからの進捗を処理
        
        Args:
            agent_id: エージェントID
            progress: 進捗率（0.0-1.0）
            message: 進捗メッセージ
            details: 詳細情報
        """
        # コールバックを呼び出し
        for callback in self._progress_callbacks:
            try:
                await callback(agent_id, progress, message)
            except Exception as e:
                logger.error(f"進捗コールバック実行中にエラー: {e}")
        
        # アクティビティを記録
        if self._activity_recorder:
            await self._activity_recorder.record_agent_action(
                session_id=self.server_connector.session_id,
                agent_id=agent_id,
                action="進捗更新",
                description=f"{message} ({progress*100:.1f}%)",
                metadata={"progress": progress, "details": details or {}}
            )
    
    async def handle_intervention_request(
        self,
        agent_id: str,
        intervention: UserIntervention
    ) -> Any:
        """
        介入要求を処理
        
        Args:
            agent_id: エージェントID
            intervention: 介入要求
            
        Returns:
            Any: ユーザーの応答
        """
        logger.info(f"エージェント {agent_id} からの介入要求: {intervention.message}")
        
        # エージェント間の競合をチェック
        if await self._check_for_conflicts(agent_id, intervention):
            # 競合がある場合は調整
            adjusted_response = await self._coordinate_intervention(agent_id, intervention)
            if adjusted_response is not None:
                return adjusted_response
        
        # イベントを作成
        event = asyncio.Event()
        self._pending_interventions[intervention.id] = event
        
        try:
            # コールバックを呼び出し
            for callback in self._intervention_callbacks:
                try:
                    response = await callback(intervention)
                    if response is not None:
                        self._intervention_responses[intervention.id] = response
                        event.set()
                        break
                except Exception as e:
                    logger.error(f"介入コールバック実行中にエラー: {e}")
            
            # 応答を待つ
            if intervention.timeout_seconds:
                await asyncio.wait_for(event.wait(), intervention.timeout_seconds)
            else:
                await event.wait()
            
            # 応答を取得
            response = self._intervention_responses.get(intervention.id)
            
            # アクティビティを記録
            if self._activity_recorder:
                await self._activity_recorder.record_agent_action(
                    session_id=self.server_connector.session_id,
                    agent_id=agent_id,
                    action="ユーザー介入",
                    description=f"介入要求に応答: {intervention.message}",
                    metadata={
                        "intervention_type": intervention.type,
                        "response": str(response)
                    }
                )
            
            return response
            
        except asyncio.TimeoutError:
            logger.warning(f"介入要求がタイムアウトしました: {intervention.id}")
            return None
            
        finally:
            # クリーンアップ
            self._pending_interventions.pop(intervention.id, None)
            self._intervention_responses.pop(intervention.id, None)
    
    def resolve_intervention(self, intervention_id: UUID, response: Any) -> bool:
        """
        介入を解決（外部から呼び出される）
        
        Args:
            intervention_id: 介入ID
            response: ユーザーの応答
            
        Returns:
            bool: 解決が成功した場合True
        """
        event = self._pending_interventions.get(intervention_id)
        if event:
            self._intervention_responses[intervention_id] = response
            event.set()
            return True
        return False
    
    def register_progress_callback(
        self,
        callback: Callable[[str, float, str], None]
    ) -> None:
        """進捗コールバックを登録"""
        if callback not in self._progress_callbacks:
            self._progress_callbacks.append(callback)
    
    def unregister_progress_callback(
        self,
        callback: Callable[[str, float, str], None]
    ) -> None:
        """進捗コールバックを解除"""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)
    
    def register_intervention_callback(
        self,
        callback: Callable[[UserIntervention], Any]
    ) -> None:
        """介入コールバックを登録"""
        if callback not in self._intervention_callbacks:
            self._intervention_callbacks.append(callback)
    
    def unregister_intervention_callback(
        self,
        callback: Callable[[UserIntervention], Any]
    ) -> None:
        """介入コールバックを解除"""
        if callback in self._intervention_callbacks:
            self._intervention_callbacks.remove(callback)
    
    def register_completion_callback(
        self,
        callback: Callable[[str, Dict[str, Any]], None]
    ) -> None:
        """完了コールバックを登録"""
        if callback not in self._completion_callbacks:
            self._completion_callbacks.append(callback)
    
    def unregister_completion_callback(
        self,
        callback: Callable[[str, Dict[str, Any]], None]
    ) -> None:
        """完了コールバックを解除"""
        if callback in self._completion_callbacks:
            self._completion_callbacks.remove(callback)
    
    def get_child_agents(self) -> Dict[str, ChildAgentHandle]:
        """子エージェントの一覧を取得"""
        return self._child_agents.copy()
    
    def get_child_agent(self, agent_id: str) -> Optional[ChildAgentHandle]:
        """特定の子エージェントを取得"""
        return self._child_agents.get(agent_id)
    
    def _register_message_handlers(self) -> None:
        """メッセージハンドラーを登録"""
        # 進捗更新
        self.server_connector.register_handler(
            MessageType.PROGRESS_UPDATE,
            self._handle_progress_message
        )
        
        # 介入要求
        self.server_connector.register_handler(
            MessageType.INTERVENTION_REQUEST,
            self._handle_intervention_message
        )
        
        # タスク完了
        self.server_connector.register_handler(
            MessageType.TASK_COMPLETE,
            self._handle_task_complete_message
        )
        
        # タスク失敗
        self.server_connector.register_handler(
            MessageType.TASK_FAILED,
            self._handle_task_failed_message
        )
    
    async def _handle_progress_message(self, message: AgentMessage) -> None:
        """進捗更新メッセージを処理"""
        payload = message.payload
        progress = payload.get("progress", 0.0)
        msg = payload.get("message", "")
        details = payload.get("details", {})
        
        await self.handle_child_progress(
            message.from_agent,
            progress,
            msg,
            details
        )
    
    async def _handle_intervention_message(self, message: AgentMessage) -> None:
        """介入要求メッセージを処理"""
        payload = message.payload
        
        intervention = UserIntervention(
            id=UUID(payload["intervention_id"]),
            type=payload["intervention_type"],
            message=payload["message"],
            options=payload.get("options", []),
            context=payload.get("context", {}),
            timeout_seconds=payload.get("timeout_seconds")
        )
        
        response = await self.handle_intervention_request(
            message.from_agent,
            intervention
        )
        
        # 応答を送信
        if response is not None:
            response_msg = InterventionResponse(
                intervention_id=intervention.id,
                task_id=UUID(payload["task_id"]),
                response=response,
                response_time_seconds=(datetime.utcnow() - intervention.created_at).total_seconds()
            )
            
            reply = MessageBuilder.respond_intervention(
                from_agent=self._agent_id,
                to_agent=message.from_agent,
                response=response_msg,
                reply_to=message.message_id
            )
            
            await self.server_connector.send_message(reply)
    
    async def _handle_task_complete_message(self, message: AgentMessage) -> None:
        """タスク完了メッセージを処理"""
        payload = message.payload
        agent_id = message.from_agent
        
        handle = self._child_agents.get(agent_id)
        if handle:
            handle.status = "completed"
        
        # コールバックを呼び出し
        for callback in self._completion_callbacks:
            try:
                await callback(agent_id, payload.get("result", {}))
            except Exception as e:
                logger.error(f"完了コールバック実行中にエラー: {e}")
        
        # アクティビティを記録
        if self._activity_recorder:
            await self._activity_recorder.record_agent_action(
                session_id=self.server_connector.session_id,
                agent_id=agent_id,
                action="タスク完了",
                description="エージェントタスクが正常に完了しました",
                metadata=payload.get("result", {})
            )
    
    async def _handle_task_failed_message(self, message: AgentMessage) -> None:
        """タスク失敗メッセージを処理"""
        payload = message.payload
        agent_id = message.from_agent
        
        handle = self._child_agents.get(agent_id)
        if handle:
            handle.status = "failed"
        
        error = payload.get("error", "Unknown error")
        
        # アクティビティを記録
        if self._activity_recorder:
            await self._activity_recorder.record_agent_action(
                session_id=self.server_connector.session_id,
                agent_id=agent_id,
                action="タスク失敗",
                description=f"エージェントタスクが失敗しました: {error}",
                metadata=payload.get("details", {})
            )
        
        logger.error(f"エージェント {agent_id} のタスクが失敗しました: {error}")
    
    async def create_collaborative_agents(
        self,
        agents: List[Dict[str, Any]],
        shared_goal: str,
        strategy: CoordinationStrategy = CoordinationStrategy.COLLABORATIVE
    ) -> Dict[str, ChildAgentHandle]:
        """
        協調作業を行う複数のエージェントを作成
        
        Args:
            agents: エージェント設定のリスト
            shared_goal: 共通の目標
            strategy: 調整戦略
            
        Returns:
            Dict[str, ChildAgentHandle]: エージェントIDとハンドルのマップ
        """
        handles = {}
        agent_ids = []
        
        # エージェントを作成
        for agent_config in agents:
            task = AgentTask(
                type=agent_config.get("task_type", "general"),
                description=agent_config.get("description", ""),
                capabilities_required=agent_config.get("capabilities", [])
            )
            
            handle = await self.create_child_agent(
                agent_type=agent_config["type"],
                task=task,
                pane_config=agent_config.get("pane_config")
            )
            
            handles[handle.agent_id] = handle
            agent_ids.append(handle.agent_id)
            
            # コーディネーターに登録
            await self._coordinator.register_agent_task(
                agent_id=handle.agent_id,
                task=task,
                resources=agent_config.get("resources", [])
            )
        
        # 協調作業を設定
        assignments = await self._coordinator.coordinate_parallel_work(
            agents=agent_ids,
            shared_goal=shared_goal,
            strategy=strategy
        )
        
        return handles
    
    async def request_inter_agent_collaboration(
        self,
        from_agent: str,
        to_agent: str,
        request_type: str,
        payload: Dict[str, Any]
    ) -> UUID:
        """
        エージェント間の協力を要求
        
        Args:
            from_agent: 要求元エージェント
            to_agent: 要求先エージェント
            request_type: 要求タイプ
            payload: 要求内容
            
        Returns:
            UUID: リクエストID
        """
        return await self._coordinator.request_inter_agent_collaboration(
            from_agent=from_agent,
            to_agent=to_agent,
            request_type=request_type,
            payload=payload
        )
    
    async def _check_for_conflicts(
        self,
        agent_id: str,
        intervention: UserIntervention
    ) -> bool:
        """
        他のエージェントとの競合をチェック
        
        Args:
            agent_id: エージェントID
            intervention: 介入要求
            
        Returns:
            bool: 競合がある場合True
        """
        # ファイル関連の介入かチェック
        if "file" in intervention.message.lower() or "create" in intervention.message.lower():
            # 他のエージェントが同じファイルを処理中か確認
            for other_agent_id, handle in self._child_agents.items():
                if other_agent_id != agent_id and handle.status == "running":
                    # 簡易的な競合検出
                    return True
        
        return False
    
    async def _coordinate_intervention(
        self,
        agent_id: str,
        intervention: UserIntervention
    ) -> Optional[Any]:
        """
        競合する介入を調整
        
        Args:
            agent_id: エージェントID
            intervention: 介入要求
            
        Returns:
            Optional[Any]: 調整された応答
        """
        # 競合するエージェントを特定
        conflicting_agents = []
        for other_agent_id, handle in self._child_agents.items():
            if other_agent_id != agent_id and handle.status == "running":
                conflicting_agents.append(other_agent_id)
        
        if conflicting_agents:
            # コーディネーターで競合を解決
            for other_agent in conflicting_agents:
                resolution = await self._coordinator.detect_and_resolve_conflicts(
                    agent_id,
                    other_agent,
                    {"intervention": intervention.message}
                )
                
                # 解決策に基づいて応答を調整
                if resolution.resolution == "defer":
                    # このエージェントの処理を後回し
                    return "キャンセル"  # 一旦キャンセルして後で再試行
                elif resolution.resolution == "merge":
                    # マージ戦略を適用
                    return "承認"  # 両方承認して後でマージ
        
        return None  # 通常の処理を続行