"""
SQLAlchemy ORM models for AetherTerm LangChain storage.
"""

from datetime import datetime

try:
    from sqlalchemy import (
        JSON,
        Column,
        DateTime,
        Float,
        Index,
        Integer,
        String,
        Text,
    )
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    from sqlalchemy.orm import declarative_base
    from sqlalchemy.types import CHAR, TypeDecorator
except ImportError:
    declarative_base = None

Base = declarative_base() if declarative_base else None


class GUID(TypeDecorator):
    """Platform-independent GUID type."""

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
    """Conversation table model."""

    __tablename__ = "conversations"

    id = Column(GUID(), primary_key=True)
    session_id = Column(String(255), nullable=False, index=True)
    conversation_type = Column(String(50), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    metadata = Column(JSON, default={})
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    parent_id = Column(GUID(), nullable=True)
    thread_id = Column(String(255), nullable=True, index=True)
    tokens = Column(Integer, nullable=True)
    model_name = Column(String(100), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    confidence_score = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_conversations_session_timestamp", "session_id", "timestamp"),
        Index("idx_conversations_type_role", "conversation_type", "role"),
        Index("idx_conversations_thread_id", "thread_id"),
    )


class SessionModel(Base):
    """Session table model."""

    __tablename__ = "sessions"

    session_id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=True, index=True)
    session_type = Column(String(50), nullable=False, default="terminal")
    status = Column(String(20), nullable=False, default="active")

    start_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_activity = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    end_time = Column(DateTime, nullable=True)

    conversation_count = Column(Integer, nullable=False, default=0)
    command_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)

    metadata = Column(JSON, default={})
    tags = Column(JSON, default=[])
    settings = Column(JSON, default={})
    environment_info = Column(JSON, default={})

    __table_args__ = (
        Index("idx_sessions_user_status", "user_id", "status"),
        Index("idx_sessions_last_activity", "last_activity"),
        Index("idx_sessions_start_time", "start_time"),
    )


class SummaryModel(Base):
    """Summary table model."""

    __tablename__ = "summaries"

    id = Column(GUID(), primary_key=True)
    session_id = Column(String(255), nullable=False, index=True)
    summary_type = Column(String(20), nullable=False, default="session")
    content = Column(Text, nullable=False)

    total_conversations = Column(Integer, nullable=False, default=0)
    total_commands = Column(Integer, nullable=False, default=0)
    total_errors = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    duration_minutes = Column(Float, nullable=False, default=0.0)

    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    metadata = Column(JSON, default={})

    __table_args__ = (
        Index("idx_summaries_session_type", "session_id", "summary_type"),
        Index("idx_summaries_created_at", "created_at"),
    )
