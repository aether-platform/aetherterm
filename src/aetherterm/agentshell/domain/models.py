"""ドメインモデル

ターミナル監視に関するドメインオブジェクトを定義します。
1Wrapper1AetherTermSessionの関係に対応。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


class EventType(Enum):
    """イベントタイプ"""

    INPUT = "input"
    OUTPUT = "output"
    RESIZE = "resize"
    EXIT = "exit"


class NotificationType(Enum):
    """通知タイプ"""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Severity(Enum):
    """重要度"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TerminalEvent:
    """ターミナルイベント"""

    event_type: EventType
    data: bytes
    timestamp: datetime
    session_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WrapperSession:
    """Wrapperセッション情報

    1Wrapper1AetherTermSessionの関係で、AetherTermのセッションと紐づく
    """

    wrapper_id: str  # Wrapper固有のID
    aetherterm_session_id: str  # AetherTermのセッションID
    wrapper_pid: int  # WrapperプロセスのPID
    shell_pid: int  # シェルプロセスのPID
    created_at: datetime
    last_activity: datetime
    terminal_size: tuple[int, int] = (24, 80)
    environment: Dict[str, str] = field(default_factory=dict)
    status: str = "active"  # active, inactive, closed

    # メタデータ
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, timeout: int) -> bool:
        """セッションが期限切れかチェック"""
        return (datetime.now() - self.last_activity).total_seconds() > timeout

    def update_activity(self) -> None:
        """最終活動時刻を更新"""
        self.last_activity = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "wrapper_id": self.wrapper_id,
            "aetherterm_session_id": self.aetherterm_session_id,
            "wrapper_pid": self.wrapper_pid,
            "shell_pid": self.shell_pid,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "terminal_size": self.terminal_size,
            "environment": self.environment,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WrapperSession":
        """辞書から復元"""
        return cls(
            wrapper_id=data["wrapper_id"],
            aetherterm_session_id=data["aetherterm_session_id"],
            wrapper_pid=data["wrapper_pid"],
            shell_pid=data["shell_pid"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_activity=datetime.fromisoformat(data["last_activity"]),
            terminal_size=tuple(data.get("terminal_size", (24, 80))),
            environment=data.get("environment", {}),
            status=data.get("status", "active"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ErrorNotification:
    """エラー通知"""

    session_id: str
    error_type: str
    message: str
    severity: Severity = Severity.MEDIUM
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WarningNotification:
    """警告通知"""

    session_id: str
    warning_type: str
    message: str
    suggestions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandAnalysis:
    """コマンド解析結果"""

    command: str
    exit_code: int
    has_error: bool = False
    error_patterns: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    execution_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
