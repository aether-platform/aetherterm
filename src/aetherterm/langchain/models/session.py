"""
セッションデータモデル
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
class SessionStatus(Enum):
    """セッションステータス"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    TERMINATED = "terminated"
class SessionType(Enum):
    """セッションタイプ"""

    TERMINAL = "terminal"
    CHAT = "chat"
    API = "api"
    SYSTEM = "system"
@dataclass
class SessionContext:
    """セッションコンテキスト"""

    session_id: str
    user_id: Optional[str] = None
    session_type: SessionType = SessionType.TERMINAL
    status: SessionStatus = SessionStatus.ACTIVE

    # 時間情報
    start_time: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None

    # 統計情報
    conversation_count: int = 0
    command_count: int = 0
    error_count: int = 0
    total_tokens: int = 0

    # メタデータ
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    # 設定情報
    settings: Dict[str, Any] = field(default_factory=dict)

    # 環境情報
    environment_info: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """初期化後の処理"""
        # メタデータの初期化
        if "created_at" not in self.metadata:
            self.metadata["created_at"] = self.start_time.isoformat()

        # デフォルト設定
        if not self.settings:
            self.settings = {"auto_save": True, "max_history": 1000, "timeout_minutes": 60}

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "session_type": self.session_type.value,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "conversation_count": self.conversation_count,
            "command_count": self.command_count,
            "error_count": self.error_count,
            "total_tokens": self.total_tokens,
            "metadata": self.metadata,
            "tags": self.tags,
            "settings": self.settings,
            "environment_info": self.environment_info,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionContext":
        """辞書から復元"""
        return cls(
            session_id=data["session_id"],
            user_id=data.get("user_id"),
            session_type=SessionType(data.get("session_type", "terminal")),
            status=SessionStatus(data.get("status", "active")),
            start_time=datetime.fromisoformat(data["start_time"]),
            last_activity=datetime.fromisoformat(data["last_activity"]),
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            conversation_count=data.get("conversation_count", 0),
            command_count=data.get("command_count", 0),
            error_count=data.get("error_count", 0),
            total_tokens=data.get("total_tokens", 0),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            settings=data.get("settings", {}),
            environment_info=data.get("environment_info", {}),
        )

    def update_activity(self) -> None:
        """最終アクティビティ時刻を更新"""
        self.last_activity = datetime.utcnow()
        self.metadata["updated_at"] = self.last_activity.isoformat()

    def increment_conversation_count(self) -> None:
        """会話数をインクリメント"""
        self.conversation_count += 1
        self.update_activity()

    def increment_command_count(self) -> None:
        """コマンド数をインクリメント"""
        self.command_count += 1
        self.update_activity()

    def increment_error_count(self) -> None:
        """エラー数をインクリメント"""
        self.error_count += 1
        self.update_activity()

    def add_tokens(self, token_count: int) -> None:
        """トークン数を追加"""
        self.total_tokens += token_count
        self.update_activity()

    def get_duration_minutes(self) -> float:
        """セッション継続時間を分単位で取得"""
        end_time = self.end_time or datetime.utcnow()
        duration = end_time - self.start_time
        return duration.total_seconds() / 60

    def get_idle_minutes(self) -> float:
        """アイドル時間を分単位で取得"""
        idle_time = datetime.utcnow() - self.last_activity
        return idle_time.total_seconds() / 60

    def is_active(self) -> bool:
        """アクティブセッションかどうか"""
        return self.status == SessionStatus.ACTIVE

    def is_expired(self, timeout_minutes: int = None) -> bool:
        """セッションが期限切れかどうか"""
        if self.status in [SessionStatus.EXPIRED, SessionStatus.TERMINATED]:
            return True

        timeout = timeout_minutes or self.settings.get("timeout_minutes", 60)
        return self.get_idle_minutes() > timeout

    def terminate(self, reason: str = None) -> None:
        """セッションを終了"""
        self.status = SessionStatus.TERMINATED
        self.end_time = datetime.utcnow()
        if reason:
            self.metadata["termination_reason"] = reason
        self.metadata["terminated_at"] = self.end_time.isoformat()

    def expire(self) -> None:
        """セッションを期限切れにする"""
        self.status = SessionStatus.EXPIRED
        self.end_time = datetime.utcnow()
        self.metadata["expired_at"] = self.end_time.isoformat()

    def reactivate(self) -> None:
        """セッションを再アクティブ化"""
        if self.status in [SessionStatus.INACTIVE, SessionStatus.EXPIRED]:
            self.status = SessionStatus.ACTIVE
            self.update_activity()
            self.metadata["reactivated_at"] = datetime.utcnow().isoformat()

    def add_tag(self, tag: str) -> None:
        """タグを追加"""
        normalized_tag = tag.lower().strip()
        if normalized_tag and normalized_tag not in self.tags:
            self.tags.append(normalized_tag)
            self.update_activity()

    def remove_tag(self, tag: str) -> bool:
        """タグを削除"""
        normalized_tag = tag.lower().strip()
        if normalized_tag in self.tags:
            self.tags.remove(normalized_tag)
            self.update_activity()
            return True
        return False

    def has_tag(self, tag: str) -> bool:
        """タグを持っているかチェック"""
        return tag.lower().strip() in self.tags

    def update_environment_info(self, info: Dict[str, Any]) -> None:
        """環境情報を更新"""
        self.environment_info.update(info)
        self.update_activity()

    def get_error_rate(self) -> float:
        """エラー率を取得"""
        total_operations = self.conversation_count + self.command_count
        if total_operations == 0:
            return 0.0
        return self.error_count / total_operations

    def get_activity_summary(self) -> Dict[str, Any]:
        """アクティビティサマリーを取得"""
        return {
            "session_id": self.session_id,
            "duration_minutes": self.get_duration_minutes(),
            "idle_minutes": self.get_idle_minutes(),
            "conversation_count": self.conversation_count,
            "command_count": self.command_count,
            "error_count": self.error_count,
            "error_rate": self.get_error_rate(),
            "total_tokens": self.total_tokens,
            "status": self.status.value,
            "is_active": self.is_active(),
        }

    def to_json(self) -> str:
        """JSON文字列に変換"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "SessionContext":
        """JSON文字列から復元"""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def __str__(self) -> str:
        """文字列表現"""
        return f"SessionContext(id={self.session_id}, status={self.status.value}, duration={self.get_duration_minutes():.1f}min)"

    def __repr__(self) -> str:
        """詳細な文字列表現"""
        return (
            f"SessionContext("
            f"session_id='{self.session_id}', "
            f"user_id='{self.user_id}', "
            f"type={self.session_type.value}, "
            f"status={self.status.value}, "
            f"conversations={self.conversation_count}, "
            f"commands={self.command_count}, "
            f"duration={self.get_duration_minutes():.1f}min"
            f")"
        )
@dataclass
class SessionSummary:
    """セッションサマリー"""

    session_id: str
    summary_type: str = "session"  # session, daily, weekly
    content: str = ""

    # 統計情報
    total_conversations: int = 0
    total_commands: int = 0
    total_errors: int = 0
    total_tokens: int = 0
    duration_minutes: float = 0.0

    # 時間情報
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)

    # メタデータ
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "session_id": self.session_id,
            "summary_type": self.summary_type,
            "content": self.content,
            "total_conversations": self.total_conversations,
            "total_commands": self.total_commands,
            "total_errors": self.total_errors,
            "total_tokens": self.total_tokens,
            "duration_minutes": self.duration_minutes,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSummary":
        """辞書から復元"""
        return cls(
            session_id=data["session_id"],
            summary_type=data.get("summary_type", "session"),
            content=data.get("content", ""),
            total_conversations=data.get("total_conversations", 0),
            total_commands=data.get("total_commands", 0),
            total_errors=data.get("total_errors", 0),
            total_tokens=data.get("total_tokens", 0),
            duration_minutes=data.get("duration_minutes", 0.0),
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            created_at=datetime.fromisoformat(data.get("created_at", data["start_time"])),
            metadata=data.get("metadata", {}),
        )
