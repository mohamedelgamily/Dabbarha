from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Document:
    source_path: str
    title: str
    content: str


@dataclass(frozen=True)
class DocumentChunk:
    document_source: str
    document_title: str
    chunk_id: int
    content: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    chunk: DocumentChunk
    score: float


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievalResult]:
        ...