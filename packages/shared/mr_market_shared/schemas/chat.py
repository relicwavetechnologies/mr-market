"""Pydantic v2 schemas for chat request/response models."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolCallSchema(BaseModel):
    """Represents a single tool/function call made by the assistant."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str | None = None


class MessageSchema(BaseModel):
    """A single message in a conversation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    role: str  # user / assistant / tool
    content: str | None = None
    tool_calls: list[ToolCallSchema] | None = None
    tokens_used: int | None = None
    model_used: str | None = None
    created_at: datetime | None = None


class ChatRequest(BaseModel):
    """Incoming chat request from the client."""

    conversation_id: uuid.UUID | None = None
    message: str
    ticker: str | None = None
    context: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    """Chat response returned to the client."""

    conversation_id: uuid.UUID
    message: MessageSchema
    suggested_actions: list[str] = Field(default_factory=list)
