"""Semantic search over Qdrant vector store."""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "concall_transcripts"


class RAGSearcher:
    """Perform semantic search over the Qdrant vector store.

    Returns the top-k most relevant document chunks for a given query,
    optionally filtered by ticker.
    """

    def __init__(
        self,
        qdrant_url: str | None = None,
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        settings = get_settings()
        self._qdrant_url = qdrant_url or settings.QDRANT_URL
        self._embedding_model = embedding_model
        self._openai_api_key = settings.OPENAI_API_KEY

    async def search(
        self,
        query: str,
        ticker: str | None = None,
        top_k: int = 5,
        score_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Search Qdrant for chunks relevant to *query*.

        Parameters
        ----------
        query : str
            Natural language search query.
        ticker : str, optional
            Filter results to a specific ticker.
        top_k : int
            Maximum number of results.
        score_threshold : float
            Minimum similarity score to include.

        Returns
        -------
        list[dict]
            Each dict contains ``text``, ``score``, and ``metadata``.
        """
        query_vector = await self._embed_query(query)

        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = AsyncQdrantClient(url=self._qdrant_url)

        search_filter = None
        if ticker:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="ticker",
                        match=MatchValue(value=ticker.upper()),
                    ),
                ],
            )

        results = await client.query_points(
            collection_name=_COLLECTION_NAME,
            query=query_vector,
            query_filter=search_filter,
            limit=top_k,
            score_threshold=score_threshold,
        )

        await client.close()

        return [
            {
                "text": point.payload.get("text", "") if point.payload else "",
                "score": round(point.score, 4) if point.score else 0.0,
                "metadata": {
                    k: v
                    for k, v in (point.payload or {}).items()
                    if k != "text"
                },
            }
            for point in results.points
        ]

    async def _embed_query(self, query: str) -> list[float]:
        """Generate an embedding vector for the search query."""
        import openai

        client = openai.AsyncOpenAI(api_key=self._openai_api_key)
        response = await client.embeddings.create(
            model=self._embedding_model,
            input=[query],
        )
        return response.data[0].embedding
