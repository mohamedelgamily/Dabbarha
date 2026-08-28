from __future__ import annotations

from pathlib import Path

from app.core.rag.chunker import chunk_document
from app.core.rag.embeddings import LocalEmbeddingEngine
from app.core.rag.schemas import Document
from app.core.rag.store import VectorStore


class KnowledgeIndex:
    """Deterministic document ingestion and indexing for Dabbarha knowledge base."""

    APPROVED_EXTENSIONS = {".md", ".txt"}
    DEFAULT_KNOWLEDGE_DIR = "docs/knowledge"

    def __init__(
        self,
        knowledge_dir: str | Path | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        self._knowledge_dir = Path(knowledge_dir or self.DEFAULT_KNOWLEDGE_DIR)
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

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

            title = file_path.stem.replace("_", " ").replace("-", " ").title()
            documents.append(
                Document(
                    source_path=str(file_path.relative_to(Path.cwd())),
                    title=title,
                    content=content,
                )
            )

        return documents

    def build_index(self) -> tuple[list[DocumentChunk], dict[str, list[float]]]:
        """Build the index from approved documents.

        Returns:
            A tuple of (chunks, embeddings) where embeddings is a mapping
            of chunk_id to vector.
        """
        documents = self._load_documents()
        all_chunks: list[DocumentChunk] = []

        for document in documents:
            chunks = chunk_document(
                document,
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )
            all_chunks.extend(chunks)

        engine = LocalEmbeddingEngine()
        embeddings = engine.embed_chunks(all_chunks) if all_chunks else {}

        return all_chunks, embeddings

    def rebuild_store(self) -> VectorStore:
        """Rebuild the vector store from the knowledge directory."""
        chunks, embeddings = self.build_index()
        store = VectorStore()
        store.add_chunks(chunks, embeddings)
        return store