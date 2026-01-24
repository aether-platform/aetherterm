"""
エージェント間通信プロトコル

AgentServer、OpenHands間の通信プロトコルを定義します。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4
class MessageType(str, Enum):
    """メッセージタイプ"""

    # タスク管理
    TASK_CREATE = "task_create"
    TASK_CANCEL = "task_cancel"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"

    # ペーン管理
    PANE_CREATE = "pane_create"
    PANE_DESTROY = "pane_destroy"
    PANE_RESIZE = "pane_resize"
    PANE_FOCUS = "pane_focus"

    # 進捗報告
    PROGRESS_UPDATE = "progress_update"
    STATUS_UPDATE = "status_update"
    LOG_MESSAGE = "log_message"

    # ユーザー介入
    INTERVENTION_REQUEST = "intervention_request"
    INTERVENTION_RESPONSE = "intervention_response"

    # エージェント管理
    AGENT_REGISTER = "agent_register"
    AGENT_UNREGISTER = "agent_unregister"
    AGENT_HEARTBEAT = "agent_heartbeat"

    # データ同期
    SYNC_REQUEST = "sync_request"
    SYNC_RESPONSE = "sync_response"
class PaneType(str, Enum):
    """ペーンタイプ"""

    TERMINAL = "terminal"
    AGENT = "agent"
    LOG = "log"
    REPORT = "report"
@dataclass
class AgentMessage:
    """エージェント間メッセージ"""

    message_id: UUID = field(default_factory=uuid4)
    from_agent: str = ""
    to_agent: str = ""
    message_type: MessageType = MessageType.STATUS_UPDATE
    timestamp: datetime = field(default_factory=datetime.utcnow)
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[UUID] = None  # 関連メッセージのID
    reply_to: Optional[UUID] = None  # 返信先メッセージID

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "message_id": str(self.message_id),
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type.value,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "reply_to": str(self.reply_to) if self.reply_to else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """辞書形式から復元"""
        return cls(
            message_id=UUID(data["message_id"]),
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            message_type=MessageType(data["message_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            payload=data.get("payload", {}),
            correlation_id=UUID(data["correlation_id"]) if data.get("correlation_id") else None,
            reply_to=UUID(data["reply_to"]) if data.get("reply_to") else None,
        )
@dataclass
class PaneConfig:
    """ペーン設定"""

    pane_type: PaneType = PaneType.TERMINAL
    title: str = ""
    size: Dict[str, int] = field(default_factory=lambda: {"rows": 24, "cols": 80})
    position: Optional[Dict[str, int]] = None
    parent_pane_id: Optional[str] = None
    agent_config: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
@dataclass
class TaskCreateRequest:
    """タスク作成リクエスト"""

    task_id: UUID = field(default_factory=uuid4)
    agent_type: str = ""
    task_type: str = ""
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    pane_config: Optional[PaneConfig] = None
    timeout_seconds: Optional[int] = None
    allow_user_intervention: bool = True

    def to_payload(self) -> Dict[str, Any]:
        """ペイロードに変換"""
        return {
            "task_id": str(self.task_id),
            "agent_type": self.agent_type,
            "task_type": self.task_type,
            "description": self.description,
            "context": self.context,
            "pane_config": self.pane_config.__dict__ if self.pane_config else None,
            "timeout_seconds": self.timeout_seconds,
            "allow_user_intervention": self.allow_user_intervention,
        }
@dataclass
class ProgressUpdate:
    """進捗更新"""

    task_id: UUID
    progress: float  # 0.0-1.0
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    estimated_remaining_seconds: Optional[int] = None

    def to_payload(self) -> Dict[str, Any]:
        """ペイロードに変換"""
        return {
            "task_id": str(self.task_id),
            "progress": self.progress,
            "message": self.message,
            "details": self.details,
            "estimated_remaining_seconds": self.estimated_remaining_seconds,
        }
@dataclass
class InterventionRequest:
    """ユーザー介入要求"""

    intervention_id: UUID = field(default_factory=uuid4)
    task_id: UUID = field(default_factory=uuid4)
    intervention_type: str = "approval"
    title: str = ""
    message: str = ""
    options: List[Union[str, Dict[str, Any]]] = field(default_factory=list)
    default_option: Optional[Union[str, int]] = None
    timeout_seconds: Optional[int] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        """ペイロードに変換"""
        return {
            "intervention_id": str(self.intervention_id),
            "task_id": str(self.task_id),
            "intervention_type": self.intervention_type,
            "title": self.title,
            "message": self.message,
            "options": self.options,
            "default_option": self.default_option,
            "timeout_seconds": self.timeout_seconds,
            "context": self.context,
        }
@dataclass
class InterventionResponse:
    """ユーザー介入応答"""

    intervention_id: UUID
    task_id: UUID
    response: Union[str, int, bool, Dict[str, Any]]
    response_time_seconds: float
    timed_out: bool = False

    def to_payload(self) -> Dict[str, Any]:
        """ペイロードに変換"""
        return {
            "intervention_id": str(self.intervention_id),
            "task_id": str(self.task_id),
            "response": self.response,
            "response_time_seconds": self.response_time_seconds,
            "timed_out": self.timed_out,
        }
class MessageBuilder:
    """メッセージビルダー（便利クラス）"""

    @staticmethod
    def create_task(from_agent: str, to_agent: str, request: TaskCreateRequest) -> AgentMessage:
        """タスク作成メッセージを生成"""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=MessageType.TASK_CREATE,
            payload=request.to_payload(),
        )

    @staticmethod
    def update_progress(from_agent: str, to_agent: str, update: ProgressUpdate) -> AgentMessage:
        """進捗更新メッセージを生成"""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=MessageType.PROGRESS_UPDATE,
            payload=update.to_payload(),
        )

    @staticmethod
    def request_intervention(
        from_agent: str, to_agent: str, request: InterventionRequest
    ) -> AgentMessage:
        """介入要求メッセージを生成"""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=MessageType.INTERVENTION_REQUEST,
            payload=request.to_payload(),
        )

    @staticmethod
    def respond_intervention(
        from_agent: str, to_agent: str, response: InterventionResponse, reply_to: UUID
    ) -> AgentMessage:
        """介入応答メッセージを生成"""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=MessageType.INTERVENTION_RESPONSE,
            payload=response.to_payload(),
            reply_to=reply_to,
        )

    @staticmethod
    def create_pane(from_agent: str, to_agent: str, pane_config: PaneConfig) -> AgentMessage:
        """ペーン作成メッセージを生成"""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=MessageType.PANE_CREATE,
            payload=pane_config.__dict__,
        )

    @staticmethod
    def complete_task(
        from_agent: str, to_agent: str, task_id: UUID, result: Dict[str, Any]
    ) -> AgentMessage:
        """タスク完了メッセージを生成"""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=MessageType.TASK_COMPLETE,
            payload={"task_id": str(task_id), "result": result},
        )

    @staticmethod
    def fail_task(
        from_agent: str,
        to_agent: str,
        task_id: UUID,
        error: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AgentMessage:
        """タスク失敗メッセージを生成"""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=MessageType.TASK_FAILED,
            payload={"task_id": str(task_id), "error": error, "details": details or {}},
        )
