"""Core agent loop — routes intent, builds context, calls LLM, verifies output."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import RedisCache
from app.config import Settings
from app.services.compliance import ComplianceService
from app.services.context_builder import ContextBuilder
from app.services.intent_router import IntentRouter, Intent
from app.services.prompt_templates import PromptTemplates
from app.services.verification import VerificationService
from app.tools import ToolRegistry

logger = logging.getLogger(__name__)

# Maximum number of tool-call round-trips before forcing a final answer.
_MAX_TOOL_ROUNDS = 8


class LLMOrchestrator:
    """End-to-end agent loop that processes user messages.

    Flow:
      1. Classify intent via ``IntentRouter``.
      2. Assemble structured context via ``ContextBuilder``.
      3. Build messages with system prompt + context + user message.
      4. Call LLM with tool definitions.
      5. If the LLM requests tool calls, execute them and feed results back
         (repeat up to ``_MAX_TOOL_ROUNDS``).
      6. Run ``VerificationService`` anti-hallucination pass.
      7. Append SEBI disclaimer via ``ComplianceService``.
      8. Return or yield the final response.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: RedisCache,
        settings: Settings,
    ) -> None:
        self._db = db
        self._redis = redis
        self._settings = settings
        self._intent_router = IntentRouter()
        self._context_builder = ContextBuilder(db=db, redis=redis)
        self._verification = VerificationService()
        self._compliance = ComplianceService()
        self._tool_registry = ToolRegistry(db=db, redis=redis)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        user_message: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Process a message and return the complete response dict."""
        intent = self._intent_router.classify(user_message)
        logger.info("Classified intent: %s for user %s", intent.value, user_id)

        context = await self._context_builder.build(
            user_message=user_message,
            intent=intent,
        )

        messages = self._build_messages(user_message, context, intent)
        tool_schemas = self._tool_registry.get_schemas_for_intent(intent)

        response_text, sources = await self._agent_loop(messages, tool_schemas)

        verification = self._verification.verify(
            llm_output=response_text,
            source_data=context,
        )
        if verification.status == "REJECT":
            logger.warning("Verification rejected: %s", verification.details)
            response_text = self._build_rejection_response(verification.details)

        response_text = self._compliance.process_response(
            response=response_text,
            intent=intent,
            user_risk_profile=None,  # fetched in Phase 2
        )

        conv_id = conversation_id or uuid.uuid4()

        return {
            "reply": response_text,
            "conversation_id": conv_id,
            "sources": sources,
            "disclaimer": self._compliance.get_disclaimer(),
        }

    async def run_stream(
        self,
        user_message: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream the response as chunks, yielding dicts with type=chunk|done."""
        result = await self.run(
            user_message=user_message,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        reply = result["reply"]
        chunk_size = 80
        for i in range(0, len(reply), chunk_size):
            yield {
                "type": "chunk",
                "content": reply[i : i + chunk_size],
            }

        yield {
            "type": "done",
            "conversation_id": result["conversation_id"],
            "sources": result["sources"],
            "disclaimer": result["disclaimer"],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        user_message: str,
        context: dict[str, Any],
        intent: Intent,
    ) -> list[dict[str, str]]:
        """Construct the message array for the LLM call."""
        system_prompt = PromptTemplates.system_prompt(intent=intent)
        context_block = json.dumps(context, indent=2, default=str)

        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"<context>\n{context_block}\n</context>\n\n"
                    f"User query: {user_message}"
                ),
            },
        ]

    async def _agent_loop(
        self,
        messages: list[dict[str, str]],
        tool_schemas: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Run the LLM tool-call loop until a final text response is produced.

        Returns ``(response_text, sources_list)``.
        """
        sources: list[dict[str, Any]] = []

        for round_num in range(_MAX_TOOL_ROUNDS):
            llm_response = await self._call_llm(messages, tool_schemas)

            if not llm_response.get("tool_calls"):
                return llm_response.get("content", ""), sources

            # Execute requested tools and feed results back
            for tool_call in llm_response["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])

                logger.info("Round %d — calling tool %s(%s)", round_num, tool_name, tool_args)
                tool_result = await self._tool_registry.execute(tool_name, **tool_args)

                sources.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "timestamp": tool_result.get("timestamp"),
                })

                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": json.dumps(tool_result, default=str),
                })

        return "I gathered the data but could not finalize a response. Please try again.", sources

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Dispatch to the configured LLM provider (Gemini or OpenAI).

        Returns a normalised dict with ``content`` and optional ``tool_calls``.
        """
        model = self._settings.LLM_MODEL

        if model.startswith("gemini"):
            return await self._call_gemini(messages, tool_schemas)
        return await self._call_openai(messages, tool_schemas)

    async def _call_gemini(
        self,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Call Google Gemini via the google-genai SDK."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._settings.GEMINI_API_KEY)

        gemini_tools = None
        if tool_schemas:
            function_declarations = []
            for schema in tool_schemas:
                func = schema["function"]
                function_declarations.append(types.FunctionDeclaration(
                    name=func["name"],
                    description=func["description"],
                    parameters=func.get("parameters"),
                ))
            gemini_tools = [types.Tool(function_declarations=function_declarations)]

        contents: list[types.Content] = []
        system_instruction = None
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=msg["content"])],
                ))
            elif msg["role"] == "assistant":
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=msg.get("content") or "")],
                ))
            elif msg["role"] == "tool":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=msg["content"])],
                ))

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
            temperature=0.3,
        )

        response = await client.aio.models.generate_content(
            model=self._settings.LLM_MODEL,
            contents=contents,
            config=config,
        )

        # Normalise response
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None:
            return {"content": "No response generated.", "tool_calls": None}

        text_parts = [p.text for p in candidate.content.parts if p.text]
        function_calls = [p.function_call for p in candidate.content.parts if p.function_call]

        tool_calls = None
        if function_calls:
            tool_calls = []
            for fc in function_calls:
                tool_calls.append({
                    "id": f"call_{fc.name}",
                    "function": {
                        "name": fc.name,
                        "arguments": json.dumps(dict(fc.args) if fc.args else {}),
                    },
                })

        return {
            "content": "\n".join(text_parts) if text_parts else None,
            "tool_calls": tool_calls,
        }

    async def _call_openai(
        self,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Call the OpenAI-compatible API."""
        import openai

        client = openai.AsyncOpenAI(api_key=self._settings.OPENAI_API_KEY)

        kwargs: dict[str, Any] = {
            "model": self._settings.LLM_MODEL,
            "messages": messages,
            "temperature": 0.3,
        }
        if tool_schemas:
            kwargs["tools"] = tool_schemas

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]

        return {
            "content": choice.message.content,
            "tool_calls": tool_calls,
        }

    @staticmethod
    def _build_rejection_response(details: list[str]) -> str:
        """Build a user-facing message when verification rejects the LLM output."""
        issues = "\n".join(f"  - {d}" for d in details)
        return (
            "I found some inconsistencies in my initial response and want to be "
            "transparent about it. Let me re-check the data:\n\n"
            f"{issues}\n\n"
            "Please verify these numbers from the source directly. "
            "I never want to give you incorrect data."
        )
