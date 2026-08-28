from __future__ import annotations

import re

from app.core.rag.schemas import Document, DocumentChunk


def chunk_document(
    document: Document,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[DocumentChunk]:
    """Split a document into overlapping chunks while preserving metadata.

    Args:
        document: The source document to chunk.
        chunk_size: Maximum number of characters per chunk.
        chunk_overlap: Number of characters to overlap between chunks.

    Returns:
        A list of DocumentChunk objects with preserved source metadata.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be non-negative")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be less than chunk_size")

    text = document.content
    chunks: list[DocumentChunk] = []

    if not text.strip():
        return chunks

    # Split on paragraph boundaries first, then on sentences, then on words
    paragraphs = re.split(r"\n\s*\n", text)
    current_chunk = ""
    chunk_id = 0

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if len(current_chunk) + len(paragraph) + 1 <= chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + paragraph
        else:
            if current_chunk:
                chunks.append(
                    DocumentChunk(
                        document_source=document.source_path,
                        document_title=document.title,
                        chunk_id=chunk_id,
                        content=current_chunk,
                    )
                )
                chunk_id += 1

            # If a single paragraph is larger than chunk_size, split it
            if len(paragraph) > chunk_size:
                words = paragraph.split()
                current_chunk = ""
                for word in words:
                    if len(current_chunk) + len(word) + 1 <= chunk_size:
                        current_chunk += (" " if current_chunk else "") + word
                    else:
                        if current_chunk:
                            chunks.append(
                                DocumentChunk(
                                    document_source=document.source_path,
                                    document_title=document.title,
                                    chunk_id=chunk_id,
                                    content=current_chunk,
                                )
                            )
                            chunk_id += 1
                        current_chunk = word
            else:
                current_chunk = paragraph

    if current_chunk:
        chunks.append(
            DocumentChunk(
                document_source=document.source_path,
                document_title=document.title,
                chunk_id=chunk_id,
                content=current_chunk,
            )
        )

    # Apply overlap by prepending the end of the previous chunk to the next
    if chunk_overlap > 0 and len(chunks) > 1:
        overlapped: list[DocumentChunk] = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                overlapped.append(chunk)
                continue
            prev_end = overlapped[-1].content[-chunk_overlap:] if overlapped[-1].content else ""
            overlapped.append(
                DocumentChunk(
                    document_source=chunk.document_source,
                    document_title=chunk.document_title,
                    chunk_id=chunk.chunk_id,
                    content=prev_end + chunk.content,
                )
            )
        return overlapped

    return chunks