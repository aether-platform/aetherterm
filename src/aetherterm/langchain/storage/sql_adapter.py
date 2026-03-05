"""
SQL storage adapter (for medium-term memory).
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from sqlalchemy import and_, delete, func, select, update
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
except ImportError:
    create_async_engine = None
    AsyncSession = None

from ..config.storage_config import StorageConfig
from ..models.conversation import ConversationEntry, ConversationType, MessageRole
from ..models.session import SessionContext, SessionStatus, SessionSummary, SessionType
from .base_storage import (
    BaseStorageAdapter,
    MemoryStorageAdapter,
    SessionStorageAdapter,
    SummaryStorageAdapter,
)
from .sql_models import Base, ConversationModel, SessionModel, SummaryModel

logger = logging.getLogger(__name__)


def _conversation_model_to_entry(conv: ConversationModel) -> ConversationEntry:
    """Convert a ConversationModel to a ConversationEntry domain object."""
    return ConversationEntry(
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


def _session_model_to_context(session_model: SessionModel) -> SessionContext:
    """Convert a SessionModel to a SessionContext domain object."""
    return SessionContext(
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


def _summary_model_to_domain(summary_model: SummaryModel) -> SessionSummary:
    """Convert a SummaryModel to a SessionSummary domain object."""
    return SessionSummary(
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


class SQLStorageAdapter(
    BaseStorageAdapter, MemoryStorageAdapter, SessionStorageAdapter, SummaryStorageAdapter
):
    """SQL storage adapter."""

    def __init__(self, config: StorageConfig):
        if create_async_engine is None:
            raise ImportError("sqlalchemy package is not installed")

        super().__init__(config.to_dict())
        self.config = config
        self._engine = None
        self._session_factory = None

    async def _ensure_connected(self):
        """Ensure database connection is established."""
        if not self._engine:
            await self.connect()

    async def _connect_impl(self) -> None:
        """SQL connection implementation."""
        try:
            database_url = self.config.get_database_url()

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

            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self._logger.info("Connected to SQL database")

        except Exception as e:
            self._logger.error(f"SQL connection error: {e}")
            raise

    async def _disconnect_impl(self) -> None:
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    async def _health_check_impl(self) -> Dict[str, Any]:
        if not self._engine:
            raise RuntimeError("SQL connection not established")

        async with self._session_factory() as session:
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

    # --- MemoryStorageAdapter ---

    async def store_conversation(self, entry: ConversationEntry) -> str:
        await self._ensure_connected()

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

                self._logger.debug(f"Stored conversation: {entry.id}")
                return str(entry.id)

        except Exception as e:
            self._logger.error(f"Store conversation error: {e}")
            raise

    async def retrieve_conversations(
        self, session_id: str, limit: int = 10, offset: int = 0
    ) -> List[ConversationEntry]:
        await self._ensure_connected()

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

                entries = [_conversation_model_to_entry(conv) for conv in conversations]
                self._logger.debug(f"Retrieved conversations: {len(entries)}")
                return entries

        except Exception as e:
            self._logger.error(f"Retrieve conversations error: {e}")
            return []

    async def search_conversations(
        self, query: str, session_id: Optional[str] = None, limit: int = 10, threshold: float = 0.7
    ) -> List[ConversationEntry]:
        await self._ensure_connected()

        try:
            async with self._session_factory() as session:
                stmt = select(ConversationModel).where(ConversationModel.content.contains(query))

                if session_id:
                    stmt = stmt.where(ConversationModel.session_id == session_id)

                stmt = stmt.order_by(ConversationModel.timestamp.desc()).limit(limit)

                result = await session.execute(stmt)
                conversations = result.scalars().all()

                entries = [_conversation_model_to_entry(conv) for conv in conversations]
                self._logger.debug(f"Search results: {len(entries)}")
                return entries

        except Exception as e:
            self._logger.error(f"Search conversations error: {e}")
            return []

    async def delete_old_conversations(self, days: int) -> int:
        await self._ensure_connected()

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            async with self._session_factory() as session:
                stmt = delete(ConversationModel).where(ConversationModel.timestamp < cutoff_date)

                result = await session.execute(stmt)
                await session.commit()

                deleted_count = result.rowcount
                self._logger.info(f"Deleted old conversations: {deleted_count}")
                return deleted_count

        except Exception as e:
            self._logger.error(f"Delete conversations error: {e}")
            return 0

    async def get_conversation_statistics(self, session_id: str) -> Dict[str, Any]:
        await self._ensure_connected()

        try:
            async with self._session_factory() as session:
                stmt = select(
                    func.count(ConversationModel.id).label("total_count"),
                    func.min(ConversationModel.timestamp).label("first_conversation"),
                    func.max(ConversationModel.timestamp).label("last_conversation"),
                    func.avg(ConversationModel.tokens).label("avg_tokens"),
                ).where(ConversationModel.session_id == session_id)

                result = await session.execute(stmt)
                stats = result.first()

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
            self._logger.error(f"Get statistics error: {e}")
            return {}

    # --- SessionStorageAdapter ---

    async def store_session_context(self, context: SessionContext) -> None:
        await self._ensure_connected()

        try:
            async with self._session_factory() as session:
                stmt = select(SessionModel).where(SessionModel.session_id == context.session_id)
                result = await session.execute(stmt)
                existing_session = result.scalar_one_or_none()

                if existing_session:
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
                self._logger.debug(f"Stored session context: {context.session_id}")

        except Exception as e:
            self._logger.error(f"Store session error: {e}")
            raise

    async def retrieve_session_context(self, session_id: str) -> Optional[SessionContext]:
        await self._ensure_connected()

        try:
            async with self._session_factory() as session:
                stmt = select(SessionModel).where(SessionModel.session_id == session_id)
                result = await session.execute(stmt)
                session_model = result.scalar_one_or_none()

                if not session_model:
                    return None

                return _session_model_to_context(session_model)

        except Exception as e:
            self._logger.error(f"Retrieve session error: {e}")
            return None

    async def update_session_activity(self, session_id: str) -> None:
        await self._ensure_connected()

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
            self._logger.error(f"Update session activity error: {e}")

    async def list_active_sessions(self) -> List[SessionContext]:
        await self._ensure_connected()

        try:
            async with self._session_factory() as session:
                stmt = (
                    select(SessionModel)
                    .where(SessionModel.status == "active")
                    .order_by(SessionModel.last_activity.desc())
                )

                result = await session.execute(stmt)
                session_models = result.scalars().all()

                return [_session_model_to_context(m) for m in session_models]

        except Exception as e:
            self._logger.error(f"List active sessions error: {e}")
            return []

    async def cleanup_expired_sessions(self, timeout_minutes: int = 60) -> int:
        await self._ensure_connected()

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
                self._logger.info(f"Cleaned up expired sessions: {expired_count}")
                return expired_count

        except Exception as e:
            self._logger.error(f"Session cleanup error: {e}")
            return 0

    # --- SummaryStorageAdapter ---

    async def store_summary(self, summary: SessionSummary) -> str:
        await self._ensure_connected()

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

                self._logger.debug(f"Stored summary: {summary_model.id}")
                return summary_model.id

        except Exception as e:
            self._logger.error(f"Store summary error: {e}")
            raise

    async def retrieve_summaries(
        self, session_id: str, summary_type: Optional[str] = None
    ) -> List[SessionSummary]:
        await self._ensure_connected()

        try:
            async with self._session_factory() as session:
                stmt = select(SummaryModel).where(SummaryModel.session_id == session_id)

                if summary_type:
                    stmt = stmt.where(SummaryModel.summary_type == summary_type)

                stmt = stmt.order_by(SummaryModel.created_at.desc())

                result = await session.execute(stmt)
                summary_models = result.scalars().all()

                return [_summary_model_to_domain(m) for m in summary_models]

        except Exception as e:
            self._logger.error(f"Retrieve summaries error: {e}")
            return []

    async def search_summaries(self, query: str, limit: int = 10) -> List[SessionSummary]:
        await self._ensure_connected()

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

                return [_summary_model_to_domain(m) for m in summary_models]

        except Exception as e:
            self._logger.error(f"Search summaries error: {e}")
            return []

    async def delete_old_summaries(self, days: int) -> int:
        await self._ensure_connected()

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            async with self._session_factory() as session:
                stmt = delete(SummaryModel).where(SummaryModel.created_at < cutoff_date)

                result = await session.execute(stmt)
                await session.commit()

                deleted_count = result.rowcount
                self._logger.info(f"Deleted old summaries: {deleted_count}")
                return deleted_count

        except Exception as e:
            self._logger.error(f"Delete summaries error: {e}")
            return 0
