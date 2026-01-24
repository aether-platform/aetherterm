"""
会話データモデル
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
class ConversationType(Enum):
    """会話タイプ"""

    USER_INPUT = "user_input"
    AI_RESPONSE = "ai_response"
    COMMAND_EXECUTION = "command_execution"
    SYSTEM_MESSAGE = "system_message"
    ERROR_MESSAGE = "error_message"
    LOG_ENTRY = "log_entry"
class MessageRole(Enum):
    """メッセージロール（LangChain互換）"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    FUNCTION = "function"
@dataclass
class ConversationEntry:
    """会話エントリ"""

    id: UUID = field(default_factory=uuid4)
    session_id: str = ""
    conversation_type: ConversationType = ConversationType.USER_INPUT
    role: MessageRole = MessageRole.USER
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    embedding: Optional[List[float]] = None

    # 追加フィールド
    parent_id: Optional[UUID] = None  # 親メッセージのID（スレッド機能用）
    thread_id: Optional[str] = None  # スレッドID
    tokens: Optional[int] = None  # トークン数
    model_name: Optional[str] = None  # 使用されたモデル名
    processing_time_ms: Optional[int] = None  # 処理時間
    confidence_score: Optional[float] = None  # 信頼度スコア

    def __post_init__(self):
        """初期化後の処理"""
        # thread_idが未設定の場合、session_idを使用
        if not self.thread_id:
            self.thread_id = self.session_id

        # メタデータの初期化
        if "created_at" not in self.metadata:
            self.metadata["created_at"] = self.timestamp.isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "conversation_type": self.conversation_type.value,
            "role": self.role.value,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "embedding": self.embedding,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "thread_id": self.thread_id,
            "tokens": self.tokens,
            "model_name": self.model_name,
            "processing_time_ms": self.processing_time_ms,
            "confidence_score": self.confidence_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationEntry":
        """辞書から復元"""
        return cls(
            id=UUID(data["id"]),
            session_id=data["session_id"],
            conversation_type=ConversationType(data["conversation_type"]),
            role=MessageRole(data["role"]),
            content=data["content"],
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            embedding=data.get("embedding"),
            parent_id=UUID(data["parent_id"]) if data.get("parent_id") else None,
            thread_id=data.get("thread_id"),
            tokens=data.get("tokens"),
            model_name=data.get("model_name"),
            processing_time_ms=data.get("processing_time_ms"),
            confidence_score=data.get("confidence_score"),
        )

    def to_langchain_message(self) -> Dict[str, str]:
        """LangChainメッセージ形式に変換"""
        return {"role": self.role.value, "content": self.content}

    def add_metadata(self, key: str, value: Any) -> None:
        """メタデータを追加"""
        self.metadata[key] = value
        self.metadata["updated_at"] = datetime.utcnow().isoformat()

    def get_content_preview(self, max_length: int = 100) -> str:
        """コンテンツのプレビューを取得"""
        if len(self.content) <= max_length:
            return self.content
        return self.content[:max_length] + "..."

    def calculate_similarity_score(self, other: "ConversationEntry") -> float:
        """他の会話エントリとの類似度を計算（簡易版）"""
        if not self.embedding or not other.embedding:
            return 0.0

        # コサイン類似度の計算
        import numpy as np

        vec1 = np.array(self.embedding)
        vec2 = np.array(other.embedding)

        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def is_recent(self, minutes: int = 60) -> bool:
        """指定した分数以内の最近のエントリかどうか"""
        time_diff = datetime.utcnow() - self.timestamp
        return time_diff.total_seconds() <= minutes * 60

    def get_age_in_hours(self) -> float:
        """エントリの経過時間を時間単位で取得"""
        time_diff = datetime.utcnow() - self.timestamp
        return time_diff.total_seconds() / 3600

    def is_user_message(self) -> bool:
        """ユーザーメッセージかどうか"""
        return self.role == MessageRole.USER

    def is_ai_message(self) -> bool:
        """AIメッセージかどうか"""
        return self.role == MessageRole.ASSISTANT

    def is_system_message(self) -> bool:
        """システムメッセージかどうか"""
        return self.role == MessageRole.SYSTEM

    def get_token_count(self) -> int:
        """トークン数を取得（推定値を含む）"""
        if self.tokens is not None:
            return self.tokens

        # 簡易的なトークン数推定（実際の実装では tiktoken などを使用）
        return len(self.content.split()) * 1.3  # 大まかな推定値

    def to_json(self) -> str:
        """JSON文字列に変換"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "ConversationEntry":
        """JSON文字列から復元"""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def __str__(self) -> str:
        """文字列表現"""
        return f"ConversationEntry(id={self.id}, type={self.conversation_type.value}, role={self.role.value}, content='{self.get_content_preview()}')"

    def __repr__(self) -> str:
        """詳細な文字列表現"""
        return (
            f"ConversationEntry("
            f"id={self.id}, "
            f"session_id='{self.session_id}', "
            f"type={self.conversation_type.value}, "
            f"role={self.role.value}, "
            f"timestamp={self.timestamp.isoformat()}, "
            f"content_length={len(self.content)}"
            f")"
        )
