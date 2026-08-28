from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from app.core.rag.chunker import chunk_document
from app.core.rag.embeddings import LocalEmbeddingEngine
from app.core.rag.schemas import Document, DocumentChunk, RetrievalResult
from app.core.rag.store import VectorStore


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievalResult]:
        ...


class KnowledgeRetriever:
    """Retriever for Dabbarha product documentation.

    Only ingests documents from the approved knowledge directory.
    Uses deterministic local TF-IDF embeddings and in-memory vector store.
    """

    APPROVED_EXTENSIONS = {".md", ".txt"}
    DEFAULT_KNOWLEDGE_DIR = "docs/knowledge"

    def __init__(
        self,
        knowledge_dir: str | Path | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        top_k: int = 3,
    ) -> None:
        self._knowledge_dir = Path(knowledge_dir or self.DEFAULT_KNOWLEDGE_DIR)
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._top_k = top_k
        self._store = VectorStore()
        self._engine = LocalEmbeddingEngine()
        self._loaded = False

    def _is_approved_path(self, path: Path) -> bool:
        """Check if a file path is within the approved knowledge directory."""
        try:
            resolved = path.resolve()
            approved = self._knowledge_dir.resolve()
            return str(resolved).startswith(str(approved))
        except (OSError, ValueError):
            return False

    def _load_documents(self) -> list[Document]:
        """Load all approved documents from the knowledge directory."""
        documents: list[Document] = []
        if not self._knowledge_dir.exists() or not self._knowledge_dir.is_dir():
            return documents

        for file_path in sorted(self._knowledge_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in self.APPROVED_EXTENSIONS:
                continue
            if not self._is_approved_path(file_path):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            # Extract title from filename (without extension)
            title = file_path.stem.replace("_", " ").replace("-", " ").title()
            documents.append(
                Document(
                    source_path=str(file_path),
                    title=title,
                    content=content,
                )
            )

        return documents

    def _index(self) -> None:
        """Ingest documents, chunk them, generate embeddings, and build the index."""
        documents = self._load_documents()
        all_chunks: list[DocumentChunk] = []

        for document in documents:
            chunks = chunk_document(
                document,
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )
            all_chunks.extend(chunks)

        if not all_chunks:
            self._store = VectorStore()
            self._engine = LocalEmbeddingEngine()
            self._loaded = True
            return

        embeddings = self._engine.embed_chunks(all_chunks)
        self._store = VectorStore()
        self._store.add_chunks(all_chunks, embeddings)
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._index()

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        """Retrieve the most relevant documentation chunks for a query."""
        self._ensure_loaded()
        k = top_k if top_k is not None else self._top_k
        query_vector = self._engine.embed(query)
        return self._store.search(query_vector, top_k=k)

    def rebuild_index(self) -> None:
        """Force rebuild the index from the knowledge directory."""
        self._loaded = False
        self._index()