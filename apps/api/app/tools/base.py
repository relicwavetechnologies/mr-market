"""Abstract base class for all agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Base class that every tool must extend.

    Subclasses define ``name``, ``description``, ``parameters`` (JSON Schema),
    and implement ``execute``.  The ``to_function_schema`` method emits the
    schema in the OpenAI / Gemini function-calling format.
    """

    name: str
    description: str
    parameters: dict[str, Any]

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Run the tool with the given keyword arguments.

        Must return a JSON-serialisable dict.
        """
        ...

    def to_function_schema(self) -> dict[str, Any]:
        """Return the tool definition in OpenAI function-calling format.

        Example output::

            {
                "type": "function",
                "function": {
                    "name": "get_live_price",
                    "description": "...",
                    "parameters": { ... }
                }
            }
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
