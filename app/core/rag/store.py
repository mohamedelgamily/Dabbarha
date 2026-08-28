from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.core.rag.schemas import DocumentChunk, RetrievalResult


@dataclass
class VectorStore:
    """In-memory vector store for document chunks and their embeddings."""

    chunks: list[DocumentChunk] = field(default_factory=list)
    embeddings: dict[str, list[float]] = field(default_factory=dict)

    def add_chunks(self, chunks: list[DocumentChunk], embeddings: dict[str, list[float]]) -> None:
        """Add chunks and their embeddings to the store."""
        self.chunks.extend(chunks)
        self.embeddings.update(embeddings)

    def similarity(self, query_vector: list[float], chunk_vector: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not query_vector or not chunk_vector:
            return 0.0
        dot = sum(a * b for a, b in zip(query_vector, chunk_vector))
        mag_q = math.sqrt(sum(a * a for a in query_vector))
        mag_c = math.sqrt(sum(b * b for b in chunk_vector))
        if mag_q == 0 or mag_c == 0:
            return 0.0
        return dot / (mag_q * mag_c)

    def search(self, query_vector: list[float], top_k: int = 3) -> list[RetrievalResult]:
        """Search for the top-k most similar chunks."""
        if not self.chunks or not query_vector:
            return []

        scored: list[RetrievalResult] = []
        for chunk in self.chunks:
            key = f"{chunk.document_source}:{chunk.chunk_id}"
            chunk_vector = self.embeddings.get(key, [])
            score = self.similarity(query_vector, chunk_vector)
            scored.append(RetrievalResult(chunk=chunk, score=score))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]