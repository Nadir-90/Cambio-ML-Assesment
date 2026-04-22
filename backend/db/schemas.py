from datetime import datetime
from pydantic import BaseModel


class SessionCreate(BaseModel):
    """Request body for creating a new session."""

    title: str | None = None
    username: str | None = None


class SessionSummary(BaseModel):
    """Lightweight session info for the sidebar list."""

    id: str
    title: str | None
    status: str
    display_num: int | None = None
    vnc_port: int | None = None
    username: str | None = None
    home_dir: str | None = None
    container_id: str | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    """Single chat message returned to the frontend."""

    id: int
    session_id: str
    role: str
    content: dict | list | None
    message_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionDetail(BaseModel):
    """Full session data including inline message snapshot."""

    id: str
    title: str | None
    status: str
    messages: list | None
    display_num: int | None = None
    vnc_port: int | None = None
    username: str | None = None
    home_dir: str | None = None
    container_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActivateRequest(BaseModel):
    """Request body for session activation with optional display reset."""

    reset_display: bool = False
