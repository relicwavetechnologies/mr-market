"""Chat endpoints — synchronous POST and streaming WebSocket."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, DBSessionDep, RedisDep, SettingsDep
from app.services.llm_orchestrator import LLMOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Incoming chat message from the client."""
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    """Full (non-streaming) chat response."""
    reply: str
    conversation_id: UUID
    sources: list[dict[str, Any]] = Field(default_factory=list)
    disclaimer: str | None = None


# ---------------------------------------------------------------------------
# ChatRouter — encapsulates handler logic
# ---------------------------------------------------------------------------

class ChatRouter:
    """Handles chat requests by delegating to the LLMOrchestrator."""

    def __init__(
        self,
        db: AsyncSession,
        redis: Any,
        settings: Any,
        user_id: UUID,
    ) -> None:
        self._db = db
        self._redis = redis
        self._settings = settings
        self._user_id = user_id
        self._orchestrator = LLMOrchestrator(
            db=db,
            redis=redis,
            settings=settings,
        )

    async def handle_message(self, request: ChatRequest) -> ChatResponse:
        """Process a single chat message and return a complete response."""
        result = await self._orchestrator.run(
            user_message=request.message,
            user_id=self._user_id,
            conversation_id=request.conversation_id,
        )
        return ChatResponse(
            reply=result["reply"],
            conversation_id=result["conversation_id"],
            sources=result.get("sources", []),
            disclaimer=result.get("disclaimer"),
        )

    async def handle_stream(self, websocket: WebSocket) -> None:
        """Stream responses over a WebSocket connection.

        Protocol:
          Client sends: ``{"message": "...", "conversation_id": "..."}``
          Server sends chunks: ``{"type": "chunk", "content": "..."}``
          Server sends final:  ``{"type": "done", "conversation_id": "..."}``
        """
        await websocket.accept()
        try:
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                user_message: str = data.get("message", "")
                conversation_id = data.get("conversation_id")

                if not user_message.strip():
                    await websocket.send_json({"type": "error", "detail": "Empty message"})
                    continue

                conv_id_parsed = UUID(conversation_id) if conversation_id else None

                async for chunk in self._orchestrator.run_stream(
                    user_message=user_message,
                    user_id=self._user_id,
                    conversation_id=conv_id_parsed,
                ):
                    if chunk["type"] == "chunk":
                        await websocket.send_json({
                            "type": "chunk",
                            "content": chunk["content"],
                        })
                    elif chunk["type"] == "done":
                        await websocket.send_json({
                            "type": "done",
                            "conversation_id": str(chunk["conversation_id"]),
                            "sources": chunk.get("sources", []),
                            "disclaimer": chunk.get("disclaimer"),
                        })
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected for user %s", self._user_id)
        except Exception:
            logger.exception("WebSocket error for user %s", self._user_id)
            await websocket.close(code=1011)


# ---------------------------------------------------------------------------
# Route definitions
# ---------------------------------------------------------------------------

@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_id: CurrentUserDep,
    db: DBSessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> ChatResponse:
    """Send a message and receive a complete response."""
    handler = ChatRouter(db=db, redis=redis, settings=settings, user_id=user_id)
    return await handler.handle_message(request)


@router.websocket("/ws")
async def chat_ws(
    websocket: WebSocket,
    db: AsyncSession = Depends(DBSessionDep),
    redis: Any = Depends(RedisDep),
    settings: Any = Depends(SettingsDep),
) -> None:
    """Stream chat responses over a WebSocket connection."""
    # For WebSocket we extract user_id from query param token
    token = websocket.query_params.get("token")
    from app.core.security import JWTAuth

    jwt_auth = JWTAuth(secret=settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    payload = jwt_auth.verify_token(token or "")
    if payload is None:
        await websocket.close(code=4001)
        return

    user_id = UUID(payload["sub"])
    handler = ChatRouter(db=db, redis=redis, settings=settings, user_id=user_id)
    await handler.handle_stream(websocket)
