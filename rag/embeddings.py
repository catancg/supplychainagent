"""Gemini text-embeddings adapter for ChromaDB (docs/feature.prd §7)."""

from __future__ import annotations

import os

from chromadb import Documents, EmbeddingFunction, Embeddings
from google import genai


class GeminiEmbeddingFunction(EmbeddingFunction):
    def __init__(self, model: str | None = None):
        self._model = model or os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
        self._client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    def __call__(self, input: Documents) -> Embeddings:
        response = self._client.models.embed_content(model=self._model, contents=list(input))
        return [embedding.values for embedding in response.embeddings]

    def name(self) -> str:
        return f"gemini:{self._model}"
