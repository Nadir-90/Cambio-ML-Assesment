import uuid
from datetime import datetime, timezone
from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


def utcNow() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


class Session(Base):
    """User session with chat history and agent state."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="new")
    messages: Mapped[list | None] = mapped_column(JSON, default=list)
    display_num: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    vnc_port: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    username: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    home_dir: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    container_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcNow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcNow, onupdate=utcNow
    )


class Message(Base):
    """Individual chat message stored for session history replay."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_session_id", "session_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[dict | list | None] = mapped_column(JSON)
    message_type: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcNow
    )
