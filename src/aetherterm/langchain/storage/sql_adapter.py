"""SQLストレージアダプター（中期メモリ用）"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    import sqlalchemy as sa
    from sqlalchemy import (
        JSON,
        Boolean,
        Column,
        DateTime,
        Float,
        Index,
        Integer,
        String,
        Text,
        and_,
        delete,
        func,
        or_,
        select,
        update,
    )
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import declarative_base, sessionmaker
    from sqlalchemy.types import CHAR, TypeDecorator
except ImportError:
    create_async_engine = None
    AsyncSession = None
    declarative_base = None

from ..config.storage_config import StorageConfig
from ..models.conversation import ConversationEntry, ConversationType, MessageRole
from ..models.session import SessionContext, SessionStatus, SessionSummary, SessionType
from .base_storage import (
    BaseStorageAdapter,
    MemoryStorageAdapter,
    SessionStorageAdapter,
    SummaryStorageAdapter,
)

logger = logging.getLogger(__name__)

# SQLAlchemy Base
Base = declarative_base()


class GUID(TypeDecorator):
    """プラットフォーム独立のGUID型"""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID())
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, str):
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return str(value)


class ConversationModel(Base):
    """会話テーブルモデル"""

    __tablename__ = "conversations"

    id = Column(GUID(), primary_key=True)
    session_id = Column(String(255), nullable=False, index=True)
    conversation_type = Column(String(50), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    metadata = Column(JSON, default={})
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # 追加フィールド
    parent_id = Column(GUID(), nullable=True)
    thread_id = Column(String(255), nullable=True, index=True)
    tokens = Column(Integer, nullable=True)
    model_name = Column(String(100), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    confidence_score = Column(Float, nullable=True)

    # インデックス
    __table_args__ = (
        Index("idx_conversations_session_timestamp", "session_id", "timestamp"),
        Index("idx_conversations_type_role", "conversation_type", "role"),
        Index("idx_conversations_thread_id", "thread_id"),
    )


class SessionModel(Base):
    """セッションテーブルモデル"""

    __tablename__ = "sessions"

    session_id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=True, index=True)
    session_type = Column(String(50), nullable=False, default="terminal")
    status = Column(String(20), nullable=False, default="active")

    # 時間情報
    start_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_activity = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    end_time = Column(DateTime, nullable=True)

    # 統計情報
    conversation_count = Column(Integer, nullable=False, default=0)
    command_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)

    # メタデータ
    metadata = Column(JSON, default={})
    tags = Column(JSON, default=[])
    settings = Column(JSON, default={})
    environment_info = Column(JSON, default={})

    # インデックス
    __table_args__ = (
        Index("idx_sessions_user_status", "user_id", "status"),
        Index("idx_sessions_last_activity", "last_activity"),
        Index("idx_sessions_start_time", "start_time"),
    )


class SummaryModel(Base):
    """要約テーブルモデル"""

    __tablename__ = "summaries"

    id = Column(GUID(), primary_key=True)
    session_id = Column(String(255), nullable=False, index=True)
    summary_type = Column(String(20), nullable=False, default="session")
    content = Column(Text, nullable=False)

    # 統計情報
    total_conversations = Column(Integer, nullable=False, default=0)
    total_commands = Column(Integer, nullable=False, default=0)
    total_errors = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    duration_minutes = Column(Float, nullable=False, default=0.0)

    # 時間情報
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # メタデータ
    metadata = Column(JSON, default={})

    # インデックス
    __table_args__ = (
        Index("idx_summaries_session_type", "session_id", "summary_type"),
        Index("idx_summaries_created_at", "created_at"),
    )


class SQLStorageAdapter(
    BaseStorageAdapter, MemoryStorageAdapter, SessionStorageAdapter, SummaryStorageAdapter
):
    """SQLストレージアダプター"""

    def __init__(self, config: StorageConfig):
        """初期化

        Args:
            config: ストレージ設定
        """
        if create_async_engine is None:
            raise ImportError("sqlalchemy パッケージがインストールされていません")

        super().__init__(config.to_dict())
        self.config = config
        self._engine = None
        self._session_factory = None

    async def _connect_impl(self) -> None:
        """SQL接続実装"""
        try:
            database_url = self.config.get_database_url()

            # SQLiteの場合は非同期URLに変換
            if database_url.startswith("sqlite:///"):
                database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
            elif database_url.startswith("postgresql://"):
                database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")

            self._engine = create_async_engine(
                database_url,
                pool_size=self.config.database_pool_size,
                max_overflow=self.config.database_max_overflow,
                pool_timeout=self.config.database_pool_timeout,
                pool_recycle=self.config.database_pool_recycle,
                echo=self.config.to_dict().get("debug", False),
            )

            self._session_factory = async_sessionmaker(
                self._engine, class_=AsyncSession, expire_on_commit=False
            )

            # テーブル作成
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self._logger.info("SQLデータベースに接続しました")

        except Exception as e:
            self._logger.error(f"SQL接続エラー: {e}")
            raise

    async def _disconnect_impl(self) -> None:
        """SQL切断実装"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    async def _health_check_impl(self) -> Dict[str, Any]:
        """SQLヘルスチェック実装"""
        if not self._engine:
            raise RuntimeError("SQL接続が確立されていません")

        async with self._session_factory() as session:
            # 簡単なクエリでヘルスチェック
            result = await session.execute(select(func.count()).select_from(ConversationModel))
            conversation_count = result.scalar()

            result = await session.execute(select(func.count()).select_from(SessionModel))
            session_count = result.scalar()

            return {
                "conversation_count": conversation_count,
                "session_count": session_count,
                "engine_pool_size": self._engine.pool.size(),
                "engine_pool_checked_in": self._engine.pool.checkedin(),
                "engine_pool_checked_out": self._engine.pool.checkedout(),
            }

    # MemoryStorageAdapter実装

    async def store_conversation(self, entry: ConversationEntry) -> str:
        """会話エントリを保存"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                conversation = ConversationModel(
                    id=str(entry.id),
                    session_id=entry.session_id,
                    conversation_type=entry.conversation_type.value,
                    role=entry.role.value,
                    content=entry.content,
                    metadata=entry.metadata,
                    timestamp=entry.timestamp,
                    created_at=datetime.utcnow(),
                    parent_id=str(entry.parent_id) if entry.parent_id else None,
                    thread_id=entry.thread_id,
                    tokens=entry.tokens,
                    model_name=entry.model_name,
                    processing_time_ms=entry.processing_time_ms,
                    confidence_score=entry.confidence_score,
                )

                session.add(conversation)
                await session.commit()

                self._logger.debug(f"会話を保存しました: {entry.id}")
                return str(entry.id)

        except Exception as e:
            self._logger.error(f"会話保存エラー: {e}")
            raise

    async def retrieve_conversations(
        self, session_id: str, limit: int = 10, offset: int = 0
    ) -> List[ConversationEntry]:
        """会話履歴を取得"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                stmt = (
                    select(ConversationModel)
                    .where(ConversationModel.session_id == session_id)
                    .order_by(ConversationModel.timestamp.desc())
                    .limit(limit)
                    .offset(offset)
                )

                result = await session.execute(stmt)
                conversations = result.scalars().all()

                entries = []
                for conv in conversations:
                    entry = ConversationEntry(
                        id=conv.id,
                        session_id=conv.session_id,
                        conversation_type=ConversationType(conv.conversation_type),
                        role=MessageRole(conv.role),
                        content=conv.content,
                        metadata=conv.metadata or {},
                        timestamp=conv.timestamp,
                        parent_id=conv.parent_id if conv.parent_id else None,
                        thread_id=conv.thread_id,
                        tokens=conv.tokens,
                        model_name=conv.model_name,
                        processing_time_ms=conv.processing_time_ms,
                        confidence_score=conv.confidence_score,
                    )
                    entries.append(entry)

                self._logger.debug(f"会話履歴を取得しました: {len(entries)}件")
                return entries

        except Exception as e:
            self._logger.error(f"会話履歴取得エラー: {e}")
            return []

    async def search_conversations(
        self, query: str, session_id: Optional[str] = None, limit: int = 10, threshold: float = 0.7
    ) -> List[ConversationEntry]:
        """会話を検索（テキスト検索）"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                stmt = select(ConversationModel).where(ConversationModel.content.contains(query))

                if session_id:
                    stmt = stmt.where(ConversationModel.session_id == session_id)

                stmt = stmt.order_by(ConversationModel.timestamp.desc()).limit(limit)

                result = await session.execute(stmt)
                conversations = result.scalars().all()

                entries = []
                for conv in conversations:
                    entry = ConversationEntry(
                        id=conv.id,
                        session_id=conv.session_id,
                        conversation_type=ConversationType(conv.conversation_type),
                        role=MessageRole(conv.role),
                        content=conv.content,
                        metadata=conv.metadata or {},
                        timestamp=conv.timestamp,
                        parent_id=conv.parent_id if conv.parent_id else None,
                        thread_id=conv.thread_id,
                        tokens=conv.tokens,
                        model_name=conv.model_name,
                        processing_time_ms=conv.processing_time_ms,
                        confidence_score=conv.confidence_score,
                    )
                    entries.append(entry)

                self._logger.debug(f"会話検索結果: {len(entries)}件")
                return entries

        except Exception as e:
            self._logger.error(f"会話検索エラー: {e}")
            return []

    async def delete_old_conversations(self, days: int) -> int:
        """古い会話を削除"""
        if not self._engine:
            await self.connect()

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            async with self._session_factory() as session:
                stmt = delete(ConversationModel).where(ConversationModel.timestamp < cutoff_date)

                result = await session.execute(stmt)
                await session.commit()

                deleted_count = result.rowcount
                self._logger.info(f"古い会話を削除しました: {deleted_count}件")
                return deleted_count

        except Exception as e:
            self._logger.error(f"会話削除エラー: {e}")
            return 0

    async def get_conversation_statistics(self, session_id: str) -> Dict[str, Any]:
        """会話統計情報を取得"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                # 基本統計
                stmt = select(
                    func.count(ConversationModel.id).label("total_count"),
                    func.min(ConversationModel.timestamp).label("first_conversation"),
                    func.max(ConversationModel.timestamp).label("last_conversation"),
                    func.avg(ConversationModel.tokens).label("avg_tokens"),
                ).where(ConversationModel.session_id == session_id)

                result = await session.execute(stmt)
                stats = result.first()

                # タイプ別統計
                stmt = (
                    select(
                        ConversationModel.conversation_type,
                        func.count(ConversationModel.id).label("count"),
                    )
                    .where(ConversationModel.session_id == session_id)
                    .group_by(ConversationModel.conversation_type)
                )

                result = await session.execute(stmt)
                type_stats = {row.conversation_type: row.count for row in result}

                return {
                    "total_conversations": stats.total_count or 0,
                    "first_conversation": stats.first_conversation.isoformat()
                    if stats.first_conversation
                    else None,
                    "last_conversation": stats.last_conversation.isoformat()
                    if stats.last_conversation
                    else None,
                    "average_tokens": float(stats.avg_tokens) if stats.avg_tokens else 0.0,
                    "conversations_by_type": type_stats,
                }

        except Exception as e:
            self._logger.error(f"統計情報取得エラー: {e}")
            return {}

    # SessionStorageAdapter実装

    async def store_session_context(self, context: SessionContext) -> None:
        """セッションコンテキストを保存"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                # 既存セッションをチェック
                stmt = select(SessionModel).where(SessionModel.session_id == context.session_id)
                result = await session.execute(stmt)
                existing_session = result.scalar_one_or_none()

                if existing_session:
                    # 更新
                    stmt = (
                        update(SessionModel)
                        .where(SessionModel.session_id == context.session_id)
                        .values(
                            user_id=context.user_id,
                            session_type=context.session_type.value,
                            status=context.status.value,
                            last_activity=context.last_activity,
                            end_time=context.end_time,
                            conversation_count=context.conversation_count,
                            command_count=context.command_count,
                            error_count=context.error_count,
                            total_tokens=context.total_tokens,
                            metadata=context.metadata,
                            tags=context.tags,
                            settings=context.settings,
                            environment_info=context.environment_info,
                        )
                    )
                    await session.execute(stmt)
                else:
                    # 新規作成
                    session_model = SessionModel(
                        session_id=context.session_id,
                        user_id=context.user_id,
                        session_type=context.session_type.value,
                        status=context.status.value,
                        start_time=context.start_time,
                        last_activity=context.last_activity,
                        end_time=context.end_time,
                        conversation_count=context.conversation_count,
                        command_count=context.command_count,
                        error_count=context.error_count,
                        total_tokens=context.total_tokens,
                        metadata=context.metadata,
                        tags=context.tags,
                        settings=context.settings,
                        environment_info=context.environment_info,
                    )
                    session.add(session_model)

                await session.commit()
                self._logger.debug(f"セッションコンテキストを保存しました: {context.session_id}")

        except Exception as e:
            self._logger.error(f"セッション保存エラー: {e}")
            raise

    async def retrieve_session_context(self, session_id: str) -> Optional[SessionContext]:
        """セッションコンテキストを取得"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                stmt = select(SessionModel).where(SessionModel.session_id == session_id)
                result = await session.execute(stmt)
                session_model = result.scalar_one_or_none()

                if not session_model:
                    return None

                context = SessionContext(
                    session_id=session_model.session_id,
                    user_id=session_model.user_id,
                    session_type=SessionType(session_model.session_type),
                    status=SessionStatus(session_model.status),
                    start_time=session_model.start_time,
                    last_activity=session_model.last_activity,
                    end_time=session_model.end_time,
                    conversation_count=session_model.conversation_count,
                    command_count=session_model.command_count,
                    error_count=session_model.error_count,
                    total_tokens=session_model.total_tokens,
                    metadata=session_model.metadata or {},
                    tags=session_model.tags or [],
                    settings=session_model.settings or {},
                    environment_info=session_model.environment_info or {},
                )

                return context

        except Exception as e:
            self._logger.error(f"セッション取得エラー: {e}")
            return None

    async def update_session_activity(self, session_id: str) -> None:
        """セッションアクティビティを更新"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                stmt = (
                    update(SessionModel)
                    .where(SessionModel.session_id == session_id)
                    .values(last_activity=datetime.utcnow())
                )

                await session.execute(stmt)
                await session.commit()

        except Exception as e:
            self._logger.error(f"セッションアクティビティ更新エラー: {e}")

    async def list_active_sessions(self) -> List[SessionContext]:
        """アクティブセッション一覧を取得"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                stmt = (
                    select(SessionModel)
                    .where(SessionModel.status == "active")
                    .order_by(SessionModel.last_activity.desc())
                )

                result = await session.execute(stmt)
                session_models = result.scalars().all()

                contexts = []
                for session_model in session_models:
                    context = SessionContext(
                        session_id=session_model.session_id,
                        user_id=session_model.user_id,
                        session_type=SessionType(session_model.session_type),
                        status=SessionStatus(session_model.status),
                        start_time=session_model.start_time,
                        last_activity=session_model.last_activity,
                        end_time=session_model.end_time,
                        conversation_count=session_model.conversation_count,
                        command_count=session_model.command_count,
                        error_count=session_model.error_count,
                        total_tokens=session_model.total_tokens,
                        metadata=session_model.metadata or {},
                        tags=session_model.tags or [],
                        settings=session_model.settings or {},
                        environment_info=session_model.environment_info or {},
                    )
                    contexts.append(context)

                return contexts

        except Exception as e:
            self._logger.error(f"アクティブセッション取得エラー: {e}")
            return []

    async def cleanup_expired_sessions(self, timeout_minutes: int = 60) -> int:
        """期限切れセッションをクリーンアップ"""
        if not self._engine:
            await self.connect()

        try:
            cutoff_time = datetime.utcnow() - timedelta(minutes=timeout_minutes)

            async with self._session_factory() as session:
                stmt = (
                    update(SessionModel)
                    .where(
                        and_(
                            SessionModel.status == "active",
                            SessionModel.last_activity < cutoff_time,
                        )
                    )
                    .values(status="expired", end_time=datetime.utcnow())
                )

                result = await session.execute(stmt)
                await session.commit()

                expired_count = result.rowcount
                self._logger.info(f"期限切れセッションをクリーンアップしました: {expired_count}件")
                return expired_count

        except Exception as e:
            self._logger.error(f"セッションクリーンアップエラー: {e}")
            return 0

    # SummaryStorageAdapter実装

    async def store_summary(self, summary: SessionSummary) -> str:
        """要約を保存"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                summary_model = SummaryModel(
                    id=str(
                        summary.session_id
                        + "_"
                        + summary.summary_type
                        + "_"
                        + summary.created_at.isoformat()
                    ),
                    session_id=summary.session_id,
                    summary_type=summary.summary_type,
                    content=summary.content,
                    total_conversations=summary.total_conversations,
                    total_commands=summary.total_commands,
                    total_errors=summary.total_errors,
                    total_tokens=summary.total_tokens,
                    duration_minutes=summary.duration_minutes,
                    start_time=summary.start_time,
                    end_time=summary.end_time,
                    created_at=summary.created_at,
                    metadata=summary.metadata,
                )

                session.add(summary_model)
                await session.commit()

                self._logger.debug(f"要約を保存しました: {summary_model.id}")
                return summary_model.id

        except Exception as e:
            self._logger.error(f"要約保存エラー: {e}")
            raise

    async def retrieve_summaries(
        self, session_id: str, summary_type: Optional[str] = None
    ) -> List[SessionSummary]:
        """要約を取得"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                stmt = select(SummaryModel).where(SummaryModel.session_id == session_id)

                if summary_type:
                    stmt = stmt.where(SummaryModel.summary_type == summary_type)

                stmt = stmt.order_by(SummaryModel.created_at.desc())

                result = await session.execute(stmt)
                summary_models = result.scalars().all()

                summaries = []
                for summary_model in summary_models:
                    summary = SessionSummary(
                        session_id=summary_model.session_id,
                        summary_type=summary_model.summary_type,
                        content=summary_model.content,
                        total_conversations=summary_model.total_conversations,
                        total_commands=summary_model.total_commands,
                        total_errors=summary_model.total_errors,
                        total_tokens=summary_model.total_tokens,
                        duration_minutes=summary_model.duration_minutes,
                        start_time=summary_model.start_time,
                        end_time=summary_model.end_time,
                        created_at=summary_model.created_at,
                        metadata=summary_model.metadata or {},
                    )
                    summaries.append(summary)

                return summaries

        except Exception as e:
            self._logger.error(f"要約取得エラー: {e}")
            return []

    async def search_summaries(self, query: str, limit: int = 10) -> List[SessionSummary]:
        """要約を検索"""
        if not self._engine:
            await self.connect()

        try:
            async with self._session_factory() as session:
                stmt = (
                    select(SummaryModel)
                    .where(SummaryModel.content.contains(query))
                    .order_by(SummaryModel.created_at.desc())
                    .limit(limit)
                )

                result = await session.execute(stmt)
                summary_models = result.scalars().all()

                summaries = []
                for summary_model in summary_models:
                    summary = SessionSummary(
                        session_id=summary_model.session_id,
                        summary_type=summary_model.summary_type,
                        content=summary_model.content,
                        total_conversations=summary_model.total_conversations,
                        total_commands=summary_model.total_commands,
                        total_errors=summary_model.total_errors,
                        total_tokens=summary_model.total_tokens,
                        duration_minutes=summary_model.duration_minutes,
                        start_time=summary_model.start_time,
                        end_time=summary_model.end_time,
                        created_at=summary_model.created_at,
                        metadata=summary_model.metadata or {},
                    )
                    summaries.append(summary)

                return summaries

        except Exception as e:
            self._logger.error(f"要約検索エラー: {e}")
            return []

    async def delete_old_summaries(self, days: int) -> int:
        """古い要約を削除"""
        if not self._engine:
            await self.connect()

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            async with self._session_factory() as session:
                stmt = delete(SummaryModel).where(SummaryModel.created_at < cutoff_date)

                result = await session.execute(stmt)
                await session.commit()

                deleted_count = result.rowcount
                self._logger.info(f"古い要約を削除しました: {deleted_count}件")
                return deleted_count

        except Exception as e:
            self._logger.error(f"要約削除エラー: {e}")
            return 0
