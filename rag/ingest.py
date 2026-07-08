"""Ingest kb/*.md → chunk → embed → upsert into a local Chroma collection.

Idempotent: chunk ids are derived from (filename, index), so re-running
overwrites existing chunks rather than duplicating them. See docs/feature.prd §7.
"""

from __future__ import annotations

import re
from pathlib import Path

import chromadb

from rag.embeddings import GeminiEmbeddingFunction

KB_DIR = Path(__file__).resolve().parent.parent / "kb"
CHROMA_DIR = Path(__file__).resolve().parent.parent / "chroma_data"
COLLECTION_NAME = "policy_kb"


def chunk_markdown(text: str) -> list[str]:
    """Splits a markdown file into paragraph-level chunks (blank-line separated)."""
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text)]
    return [c for c in chunks if c]


def get_collection(client: chromadb.ClientAPI | None = None):
    client = client or chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME, embedding_function=GeminiEmbeddingFunction()
    )


def ingest() -> int:
    """Ingests all kb/*.md files into the policy_kb collection. Returns chunk count."""
    collection = get_collection()
    ids, documents, metadatas = [], [], []
    for path in sorted(KB_DIR.glob("*.md")):
        for i, chunk in enumerate(chunk_markdown(path.read_text(encoding="utf-8"))):
            ids.append(f"{path.stem}::{i}")
            documents.append(chunk)
            metadatas.append({"source": path.name})
    if not ids:
        return 0
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(ids)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    count = ingest()
    print(f"Ingested {count} chunks from {KB_DIR} into '{COLLECTION_NAME}' at {CHROMA_DIR}")
