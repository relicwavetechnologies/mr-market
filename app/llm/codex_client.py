"""Small OpenAI-chat-shaped adapter for the ChatGPT Codex backend.

Gateway uses the same backend for Codex OAuth tokens. This adapter implements
only the subset of the OpenAI SDK surface the orchestrator needs:
``client.chat.completions.create(...)`` with optional streaming and function
tool calls.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx

CODEX_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"

MODEL_ALIASES = {
    "gpt-4o": "gpt-5.4",
    "gpt-4o-mini": "gpt-5.4-mini",
    "gpt-4o-2024-11-20": "gpt-5.4",
    "gpt-4o-2024-08-06": "gpt-5.4",
    "gpt-4": "gpt-5.4",
    "gpt-4-turbo": "gpt-5.4",
    "o1": "gpt-5.3-codex",
    "o1-mini": "gpt-5.4-mini",
    "o3": "gpt-5.3-codex",
    "o3-mini": "gpt-5.4-mini",
    "o4-mini": "gpt-5.4-mini",
}


class CodexOpenAIClient:
    def __init__(self, access_token: str) -> None:
        self.chat = _Chat(access_token)


class _Chat:
    def __init__(self, access_token: str) -> None:
        self.completions = _Completions(access_token)


class _Completions:
    def __init__(self, access_token: str) -> None:
        self._access_token = access_token

    async def create(self, **kwargs: Any) -> Any:
        payload = _to_codex_payload(kwargs)
        if kwargs.get("stream") is True:
            return _stream_chat(self._access_token, payload)

        text, tool_calls = await _run_buffered(self._access_token, payload)
        message = SimpleNamespace(content=text, tool_calls=tool_calls or None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _to_codex_payload(kwargs: dict[str, Any]) -> dict[str, Any]:
    messages = list(kwargs.get("messages") or [])
    instructions = (
        "\n\n".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "system"
        ).strip()
        or "You are a helpful assistant."
    )
    return {
        "model": _normalize_model(str(kwargs.get("model") or "gpt-5.4-mini")),
        "instructions": instructions,
        "input": _messages_to_input(messages),
        "tools": [_tool_to_codex(t) for t in (kwargs.get("tools") or [])],
        "tool_choice": kwargs.get("tool_choice") or "auto",
        "parallel_tool_calls": False,
        "reasoning": {"summary": "auto"},
        "store": False,
        "stream": True,
        "prompt_cache_key": str(uuid.uuid4()),
    }


def _normalize_model(model: str) -> str:
    return MODEL_ALIASES.get(model, model)


def _messages_to_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "system":
            continue
        items.extend(_message_to_input(message))
    return items


def _message_to_input(message: dict[str, Any]) -> list[dict[str, Any]]:
    role = message.get("role")
    if role == "tool":
        return [
            {
                "type": "function_call_output",
                "call_id": message.get("tool_call_id"),
                "output": str(message.get("content") or ""),
            }
        ]
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        out = []
        for tc in tool_calls:
            fn = tc.get("function") or {}
            out.append(
                {
                    "type": "function_call",
                    "call_id": tc.get("id"),
                    "name": fn.get("name"),
                    "arguments": fn.get("arguments") or "{}",
                }
            )
        return out
    return [
        {
            "type": "message",
            "role": role if role in {"user", "assistant"} else "user",
            "content": str(message.get("content") or ""),
        }
    ]


def _tool_to_codex(tool: dict[str, Any]) -> dict[str, Any]:
    fn = tool.get("function") or {}
    return {
        "type": "function",
        "name": fn.get("name"),
        "description": fn.get("description") or "",
        "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
    }


async def _run_buffered(
    access_token: str,
    payload: dict[str, Any],
) -> tuple[str, list[SimpleNamespace]]:
    text = ""
    tool_calls: dict[int, dict[str, Any]] = {}
    async for evt in _events(access_token, payload):
        kind = evt.get("type")
        if kind == "response.output_item.added":
            item = evt.get("item") or {}
            if item.get("type") == "message":
                text = ""
            elif item.get("type") == "function_call":
                ix = int(evt.get("output_index") or len(tool_calls))
                tool_calls[ix] = {
                    "id": item.get("call_id")
                    or item.get("id")
                    or f"call_{uuid.uuid4().hex}",
                    "name": item.get("name"),
                    "arguments": item.get("arguments") or "",
                }
        elif kind == "response.output_text.delta":
            text += str(evt.get("delta") or "")
        elif kind == "response.function_call_arguments.delta":
            ix = int(evt.get("output_index") or 0)
            tool_calls.setdefault(
                ix, {"id": f"call_{uuid.uuid4().hex}", "arguments": ""}
            )
            tool_calls[ix]["arguments"] = tool_calls[ix].get("arguments", "") + str(
                evt.get("delta") or ""
            )
        elif kind in {
            "response.function_call_arguments.done",
            "response.output_item.done",
        }:
            _merge_tool_call(tool_calls, evt)

    return text, [
        _tool_call_obj(tc) for _, tc in sorted(tool_calls.items()) if tc.get("name")
    ]


def _merge_tool_call(
    tool_calls: dict[int, dict[str, Any]], evt: dict[str, Any]
) -> None:
    item = evt.get("item") or {}
    if (
        item.get("type") != "function_call"
        and evt.get("type") != "response.function_call_arguments.done"
    ):
        return
    ix = int(evt.get("output_index") or 0)
    current = tool_calls.setdefault(ix, {"id": f"call_{uuid.uuid4().hex}"})
    if item:
        current["id"] = item.get("call_id") or item.get("id") or current["id"]
        current["name"] = item.get("name") or current.get("name")
        current["arguments"] = item.get("arguments") or current.get("arguments") or "{}"
    if evt.get("arguments"):
        current["arguments"] = evt.get("arguments")


def _tool_call_obj(tc: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=tc["id"],
        function=SimpleNamespace(
            name=tc["name"],
            arguments=tc.get("arguments") or "{}",
        ),
    )


async def _stream_chat(
    access_token: str, payload: dict[str, Any]
) -> AsyncIterator[Any]:
    async for evt in _events(access_token, payload):
        if evt.get("type") == "response.output_text.delta":
            delta = SimpleNamespace(content=str(evt.get("delta") or ""))
            yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


async def _events(
    access_token: str, payload: dict[str, Any]
) -> AsyncIterator[dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST", CODEX_ENDPOINT, headers=headers, json=payload
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise RuntimeError(
                    f"Codex API error {resp.status_code}: {body[:500]!r}"
                )

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    evt = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(evt, dict):
                    yield evt
