"""
メモリデータモデル
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
class MemoryType(Enum):
    """メモリタイプ"""

    SHORT_TERM = "short_term"  # 短期メモリ（Redis）
    MEDIUM_TERM = "medium_term"  # 中期メモリ（SQL）
    LONG_TERM = "long_term"  # 長期メモリ（Vector Store）
class MemoryPriority(Enum):
    """メモリ優先度"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"
@dataclass
class MemoryEntry:
    """メモリエントリ"""

    id: UUID = field(default_factory=uuid4)
    session_id: str = ""
    memory_type: MemoryType = MemoryType.MEDIUM_TERM
    content: str = ""
    content_type: str = "text"  # text, json, binary
    priority: MemoryPriority = MemoryPriority.NORMAL

    # メタデータ
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    # 時間情報
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    accessed_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    # ベクトル情報
    embedding: Optional[List[float]] = None
    embedding_model: Optional[str] = None

    # 関連情報
    source_id: Optional[UUID] = None  # 元となったエントリのID
    related_ids: List[UUID] = field(default_factory=list)  # 関連エントリのID

    # 統計情報
    access_count: int = 0
    relevance_score: float = 0.0

    def __post_init__(self):
        """初期化後の処理"""
        # メタデータの初期化
        if "created_at" not in self.metadata:
            self.metadata["created_at"] = self.created_at.isoformat()

        # タグの正規化
        self.tags = [tag.lower().strip() for tag in self.tags if tag.strip()]

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "memory_type": self.memory_type.value,
            "content": self.content,
            "content_type": self.content_type,
            "priority": self.priority.value,
            "metadata": self.metadata,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "embedding": self.embedding,
            "embedding_model": self.embedding_model,
            "source_id": str(self.source_id) if self.source_id else None,
            "related_ids": [str(rid) for rid in self.related_ids],
            "access_count": self.access_count,
            "relevance_score": self.relevance_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """辞書から復元"""
        return cls(
            id=UUID(data["id"]),
            session_id=data["session_id"],
            memory_type=MemoryType(data["memory_type"]),
            content=data["content"],
            content_type=data.get("content_type", "text"),
            priority=MemoryPriority(data.get("priority", "normal")),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            accessed_at=datetime.fromisoformat(data["accessed_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"])
            if data.get("expires_at")
            else None,
            embedding=data.get("embedding"),
            embedding_model=data.get("embedding_model"),
            source_id=UUID(data["source_id"]) if data.get("source_id") else None,
            related_ids=[UUID(rid) for rid in data.get("related_ids", [])],
            access_count=data.get("access_count", 0),
            relevance_score=data.get("relevance_score", 0.0),
        )

    def update_access(self) -> None:
        """アクセス情報を更新"""
        self.accessed_at = datetime.utcnow()
        self.access_count += 1
        self.updated_at = datetime.utcnow()

    def add_tag(self, tag: str) -> None:
        """タグを追加"""
        normalized_tag = tag.lower().strip()
        if normalized_tag and normalized_tag not in self.tags:
            self.tags.append(normalized_tag)
            self.updated_at = datetime.utcnow()

    def remove_tag(self, tag: str) -> bool:
        """タグを削除"""
        normalized_tag = tag.lower().strip()
        if normalized_tag in self.tags:
            self.tags.remove(normalized_tag)
            self.updated_at = datetime.utcnow()
            return True
        return False

    def has_tag(self, tag: str) -> bool:
        """タグを持っているかチェック"""
        return tag.lower().strip() in self.tags

    def is_expired(self) -> bool:
        """有効期限切れかチェック"""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def get_age_in_hours(self) -> float:
        """作成からの経過時間を時間単位で取得"""
        time_diff = datetime.utcnow() - self.created_at
        return time_diff.total_seconds() / 3600

    def get_last_access_hours(self) -> float:
        """最終アクセスからの経過時間を時間単位で取得"""
        time_diff = datetime.utcnow() - self.accessed_at
        return time_diff.total_seconds() / 3600
@dataclass
class ContextEntry:
    """コンテキストエントリ"""

    content: str
    source: str  # conversation, summary, command, memory
    relevance_score: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 追加情報
    source_id: Optional[str] = None
    memory_type: Optional[MemoryType] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "content": self.content,
            "source": self.source,
            "relevance_score": self.relevance_score,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "source_id": self.source_id,
            "memory_type": self.memory_type.value if self.memory_type else None,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextEntry":
        """辞書から復元"""
        return cls(
            content=data["content"],
            source=data["source"],
            relevance_score=data["relevance_score"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
            source_id=data.get("source_id"),
            memory_type=MemoryType(data["memory_type"]) if data.get("memory_type") else None,
            tags=data.get("tags", []),
        )

    def get_content_preview(self, max_length: int = 100) -> str:
        """コンテンツのプレビューを取得"""
        if len(self.content) <= max_length:
            return self.content
        return self.content[:max_length] + "..."

    def is_recent(self, hours: int = 24) -> bool:
        """指定した時間以内の最近のエントリかどうか"""
        time_diff = datetime.utcnow() - self.timestamp
        return time_diff.total_seconds() <= hours * 3600
@dataclass
class MemorySearchResult:
    """メモリ検索結果"""

    entries: List[MemoryEntry]
    total_count: int
    search_time_ms: int
    query: str
    filters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "total_count": self.total_count,
            "search_time_ms": self.search_time_ms,
            "query": self.query,
            "filters": self.filters,
        }

    def get_top_entries(self, limit: int = 5) -> List[MemoryEntry]:
        """上位エントリを取得"""
        return sorted(self.entries, key=lambda x: x.relevance_score, reverse=True)[:limit]

    def filter_by_type(self, memory_type: MemoryType) -> List[MemoryEntry]:
        """メモリタイプでフィルタリング"""
        return [entry for entry in self.entries if entry.memory_type == memory_type]

    def filter_by_tag(self, tag: str) -> List[MemoryEntry]:
        """タグでフィルタリング"""
        return [entry for entry in self.entries if entry.has_tag(tag)]
@dataclass
class MemoryStatistics:
    """メモリ統計情報"""

    total_entries: int = 0
    entries_by_type: Dict[str, int] = field(default_factory=dict)
    entries_by_priority: Dict[str, int] = field(default_factory=dict)
    total_size_bytes: int = 0
    average_relevance_score: float = 0.0
    most_accessed_entries: List[UUID] = field(default_factory=list)
    oldest_entry_date: Optional[datetime] = None
    newest_entry_date: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "total_entries": self.total_entries,
            "entries_by_type": self.entries_by_type,
            "entries_by_priority": self.entries_by_priority,
            "total_size_bytes": self.total_size_bytes,
            "average_relevance_score": self.average_relevance_score,
            "most_accessed_entries": [str(eid) for eid in self.most_accessed_entries],
            "oldest_entry_date": self.oldest_entry_date.isoformat()
            if self.oldest_entry_date
            else None,
            "newest_entry_date": self.newest_entry_date.isoformat()
            if self.newest_entry_date
            else None,
        }
