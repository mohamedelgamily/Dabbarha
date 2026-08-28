from __future__ import annotations

import math
import re
from collections import Counter

from app.core.rag.schemas import DocumentChunk


class LocalEmbeddingEngine:
    """Deterministic local embedding engine using TF-IDF with a fixed vocabulary.

    This engine requires no external API calls and produces deterministic
    embeddings for the same input text. It is suitable for small corpora
    where semantic precision is less critical than deterministic behavior.
    """

    def __init__(self, vocabulary: list[str] | None = None) -> None:
        self._vocabulary = vocabulary or []
        self._vocab_index: dict[str, int] = {term: i for i, term in enumerate(self._vocabulary)}

    def fit(self, documents: list[str]) -> None:
        """Build vocabulary from a corpus of documents."""
        doc_count = len(documents)
        if doc_count == 0:
            return

        df: Counter[str] = Counter()
        for doc in documents:
            terms = self._tokenize(doc)
            df.update(set(terms))

        # Keep terms that appear in at least 1 document and at most all documents
        self._vocabulary = sorted(
            term for term, count in df.items() if 1 <= count <= doc_count
        )
        self._vocab_index = {term: i for i, term in enumerate(self._vocabulary)}

    def embed(self, text: str) -> list[float]:
        """Embed a single text into a TF-IDF vector."""
        if not self._vocabulary:
            return []

        terms = self._tokenize(text)
        term_counts = Counter(terms)
        doc_len = len(terms)
        if doc_len == 0:
            return [0.0] * len(self._vocabulary)

        # TF: term frequency normalized by document length
        # IDF: log(N / df) where N is total docs and df is document frequency
        # We use a simplified IDF based on vocabulary presence
        vector = [0.0] * len(self._vocabulary)
        for term, count in term_counts.items():
            if term in self._vocab_index:
                tf = count / doc_len
                # Use a fixed IDF approximation for determinism
                idf = math.log(len(self._vocabulary) / 1.0)
                vector[self._vocab_index[term]] = tf * idf

        # Normalize to unit length
        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude > 0:
            vector = [v / magnitude for v in vector]

        return vector

    def embed_chunks(self, chunks: list[DocumentChunk]) -> dict[str, list[float]]:
        """Embed multiple chunks and return a mapping of chunk_id to vector."""
        documents = [chunk.content for chunk in chunks]
        self.fit(documents)
        return {f"{chunk.document_source}:{chunk.chunk_id}": self.embed(chunk.content) for chunk in chunks}

    @property
    def vocabulary(self) -> list[str]:
        return list(self._vocabulary)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple deterministic tokenizer."""
        text = text.lower()
        # Split on non-alphanumeric characters and filter empty
        tokens = re.findall(r"[a-z0-9]+", text)
        return tokens