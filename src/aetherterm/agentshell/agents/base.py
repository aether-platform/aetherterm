"""AIエージェント基本インターフェース

すべてのAIエージェント統合の基底となるインターフェースを定義します。
エージェント間通信、タスク管理、ユーザー介入ポイントを提供します。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import UUID, uuid4


class AgentCapability(str, Enum):
    """エージェントの能力タイプ"""

    CODE_GENERATION = "code_generation"
    CODE_EDITING = "code_editing"
    CODE_REVIEW = "code_review"
    DEBUGGING = "debugging"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    SYSTEM_ADMINISTRATION = "system_administration"
    DATA_ANALYSIS = "data_analysis"
    GENERAL_ASSISTANCE = "general_assistance"


class TaskStatus(str, Enum):
    """タスクの状態"""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_USER_INPUT = "waiting_user_input"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InterventionType(str, Enum):
    """ユーザー介入のタイプ"""

    APPROVAL = "approval"  # 承認が必要
    CHOICE = "choice"  # 選択が必要
    INPUT = "input"  # 入力が必要
    REVIEW = "review"  # レビューが必要
    CONFIRMATION = "confirmation"  # 確認が必要


@dataclass
class UserIntervention:
    """ユーザー介入要求"""

    id: UUID = field(default_factory=uuid4)
    type: InterventionType = InterventionType.APPROVAL
    message: str = ""
    options: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    resolution: Optional[Union[str, bool, int]] = None


@dataclass
class AgentTask:
    """エージェントに依頼するタスク"""

    id: UUID = field(default_factory=uuid4)
    type: str = ""
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    capabilities_required: List[AgentCapability] = field(default_factory=list)
    priority: int = 5  # 1-10, 10が最高
    timeout_seconds: Optional[int] = None
    allow_user_intervention: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    parent_task_id: Optional[UUID] = None
    subtasks: List["AgentTask"] = field(default_factory=list)


@dataclass
class AgentResult:
    """エージェントの実行結果"""

    task_id: UUID
    success: bool = True
    output: Any = None
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    user_interventions: List[UserIntervention] = field(default_factory=list)
    execution_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "task_id": str(self.task_id),
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "logs": self.logs,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "user_interventions": [
                {
                    "id": str(ui.id),
                    "type": ui.type.value,
                    "message": ui.message,
                    "resolution": ui.resolution,
                    "resolved_at": ui.resolved_at.isoformat() if ui.resolved_at else None,
                }
                for ui in self.user_interventions
            ],
            "execution_time_seconds": self.execution_time_seconds,
        }


class AgentInterface(ABC):
    """すべてのAIエージェントが実装すべき基本インターフェース

    このインターフェースは、エージェント間の相互運用性を保証し、
    統一的な方法でタスクの実行、監視、ユーザー介入を可能にします。
    """

    def __init__(self, agent_id: str, capabilities: List[AgentCapability]):
        self.agent_id = agent_id
        self.capabilities = capabilities
        self._running_tasks: Dict[UUID, AgentTask] = {}
        self._intervention_callbacks: List[Callable[[UserIntervention], None]] = []
        self._progress_callbacks: List[Callable[[UUID, float, str], None]] = []

    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """エージェントを初期化

        Args:
            config: エージェント固有の設定

        Returns:
            bool: 初期化が成功した場合True
        """

    @abstractmethod
    async def shutdown(self) -> None:
        """エージェントをシャットダウン"""

    @abstractmethod
    async def execute_task(self, task: AgentTask) -> AgentResult:
        """タスクを実行

        Args:
            task: 実行するタスク

        Returns:
            AgentResult: 実行結果
        """

    @abstractmethod
    async def cancel_task(self, task_id: UUID) -> bool:
        """実行中のタスクをキャンセル

        Args:
            task_id: キャンセルするタスクのID

        Returns:
            bool: キャンセルが成功した場合True
        """

    @abstractmethod
    async def get_task_status(self, task_id: UUID) -> Optional[TaskStatus]:
        """タスクの現在の状態を取得

        Args:
            task_id: 状態を取得するタスクのID

        Returns:
            Optional[TaskStatus]: タスクの状態、存在しない場合None
        """

    @abstractmethod
    async def get_task_progress(self, task_id: UUID) -> Optional[float]:
        """タスクの進捗を取得（0.0-1.0）

        Args:
            task_id: 進捗を取得するタスクのID

        Returns:
            Optional[float]: 進捗率、存在しない場合None
        """

    async def request_user_intervention(self, task_id: UUID, intervention: UserIntervention) -> Any:
        """ユーザー介入を要求

        Args:
            task_id: 関連するタスクのID
            intervention: 介入要求の詳細

        Returns:
            Any: ユーザーの応答
        """
        # コールバックを呼び出し
        for callback in self._intervention_callbacks:
            try:
                await callback(intervention)
            except Exception:
                # ログに記録するが、処理は継続
                pass

        # 応答を待つ（実装はサブクラスで）
        return await self._wait_for_intervention_response(intervention)

    @abstractmethod
    async def _wait_for_intervention_response(self, intervention: UserIntervention) -> Any:
        """介入応答を待つ（サブクラスで実装）"""

    def register_intervention_callback(self, callback: Callable[[UserIntervention], None]) -> None:
        """ユーザー介入コールバックを登録"""
        if callback not in self._intervention_callbacks:
            self._intervention_callbacks.append(callback)

    def unregister_intervention_callback(
        self, callback: Callable[[UserIntervention], None]
    ) -> None:
        """ユーザー介入コールバックを解除"""
        if callback in self._intervention_callbacks:
            self._intervention_callbacks.remove(callback)

    def register_progress_callback(self, callback: Callable[[UUID, float, str], None]) -> None:
        """進捗通知コールバックを登録"""
        if callback not in self._progress_callbacks:
            self._progress_callbacks.append(callback)

    def unregister_progress_callback(self, callback: Callable[[UUID, float, str], None]) -> None:
        """進捗通知コールバックを解除"""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)

    async def report_progress(self, task_id: UUID, progress: float, message: str = "") -> None:
        """タスクの進捗を報告

        Args:
            task_id: タスクID
            progress: 進捗率（0.0-1.0）
            message: 進捗メッセージ
        """
        for callback in self._progress_callbacks:
            try:
                await callback(task_id, progress, message)
            except Exception:
                # ログに記録するが、処理は継続
                pass

    def supports_capability(self, capability: AgentCapability) -> bool:
        """指定された能力をサポートしているか確認"""
        return capability in self.capabilities

    def get_capabilities(self) -> List[AgentCapability]:
        """サポートしている能力のリストを取得"""
        return self.capabilities.copy()

    def get_agent_info(self) -> Dict[str, Any]:
        """エージェントの情報を取得"""
        return {
            "agent_id": self.agent_id,
            "capabilities": [cap.value for cap in self.capabilities],
            "running_tasks": len(self._running_tasks),
            "class": self.__class__.__name__,
        }
