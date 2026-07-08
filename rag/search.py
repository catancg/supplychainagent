"""search_policy tool — RAG retrieval over the policy corpus (docs/feature.prd §7).

Returns raw retrieved chunks. Wrapping them as reference-only, untrusted data
happens in an after_tool_callback (see agents/guardrails.py), not here.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from rag.ingest import get_collection


def search_policy(query: str, k: int, tool_context: ToolContext) -> dict:
    """Searches the policy knowledge base for chunks relevant to a query.

    Args:
        query: natural-language question, e.g. "safety buffer for appliances".
        k: number of chunks to return.
    """
    collection = get_collection()
    results = collection.query(query_texts=[query], n_results=k)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    chunks = [
        {"text": doc, "source": meta.get("source", "unknown")}
        for doc, meta in zip(documents, metadatas)
    ]
    return {"query": query, "chunks": chunks}
