"""ConcallRagTool — semantic search over con-call transcripts and annual reports."""

from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ConcallRagTool(BaseTool):
    """Search Qdrant for relevant con-call / annual report transcript chunks.

    Uses the ``RAGSearcher`` to perform vector similarity search indexed by
    ticker and date.
    """

    name = "search_concall"
    description = (
        "Search through earnings call transcripts and annual report data "
        "for a stock. Returns relevant text chunks with relevance scores."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "NSE ticker symbol",
            },
            "query": {
                "type": "string",
                "description": "Natural language query to search for in transcripts",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default 5)",
                "default": 5,
            },
        },
        "required": ["ticker", "query"],
    }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        ticker: str = kwargs["ticker"].upper().strip()
        query: str = kwargs["query"]
        top_k: int = kwargs.get("top_k", 5)

        try:
            from app.rag.search import RAGSearcher

            searcher = RAGSearcher()
            results = await searcher.search(
                query=query,
                ticker=ticker,
                top_k=top_k,
            )

            return {
                "ticker": ticker,
                "query": query,
                "results": results,
                "count": len(results),
                "source": "qdrant",
            }
        except Exception as exc:
            logger.warning("Concall RAG search failed for %s: %s", ticker, exc)
            return {
                "ticker": ticker,
                "query": query,
                "results": [],
                "count": 0,
                "error": str(exc),
                "source": "qdrant",
            }
