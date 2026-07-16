"""
Embedding utilities.

OpenAI ``text-embedding-3-small`` is the production default. In mock mode a
deterministic hash vector exercises storage and retrieval contracts without
calling a model or the network; it is not a semantic embedding.
"""

import os
import hashlib
import math
from typing import Any, List, Optional
from abc import ABC, abstractmethod
from enum import Enum


class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""
    MOCK = "mock"
    OPENAI = "openai"
    OLLAMA = "ollama"


# Fixed embedding dimensions for compatibility with Neo4j vector index
EMBEDDING_DIMENSIONS = 1536


class BaseEmbeddingClient(ABC):
    """Abstract base class for embedding clients."""

    DIMENSIONS = EMBEDDING_DIMENSIONS

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Embed a single text."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts in batch."""
        pass


class OpenAIEmbeddingClient(BaseEmbeddingClient):
    """OpenAI embedding client."""

    def __init__(self, api_key: Optional[str] = None, client: Any = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if client is None:
            if not self.api_key:
                raise ValueError(
                    "OPENAI_API_KEY is not set. Use KOMPONIST_AI_MODE=mock "
                    "for offline development."
                )
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key)

        self.client = client
        self.model = os.getenv("KOMPONIST_EMBEDDING_MODEL", "text-embedding-3-small")

    @classmethod
    def _validate_dimensions(cls, embedding: List[float]) -> List[float]:
        if len(embedding) != cls.DIMENSIONS:
            raise ValueError(
                f"Embedding model returned {len(embedding)} dimensions; "
                f"Neo4j expects {cls.DIMENSIONS}."
            )
        return embedding

    async def embed(self, text: str) -> List[float]:
        """
        Embed a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (1536 dims)
        """
        response = await self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.DIMENSIONS,
            encoding_format="float",
        )

        return self._validate_dimensions(response.data[0].embedding)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts in batch.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.DIMENSIONS,
            encoding_format="float",
        )

        # Sort by index to maintain order
        embeddings = sorted(response.data, key=lambda x: x.index)
        return [self._validate_dimensions(e.embedding) for e in embeddings]


class MockEmbeddingClient(BaseEmbeddingClient):
    """Deterministic no-model embedding double for offline contract tests."""

    model = "mock-hash-embedding"

    async def embed(self, text: str) -> List[float]:
        raw = hashlib.shake_256(text.encode("utf-8")).digest(self.DIMENSIONS * 2)
        values = [
            (int.from_bytes(raw[index:index + 2], "big") / 32767.5) - 1.0
            for index in range(0, len(raw), 2)
        ]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed(text) for text in texts]


class OllamaEmbeddingClient(BaseEmbeddingClient):
    """Ollama local embedding client."""

    def __init__(self, base_url: Optional[str] = None):
        import httpx

        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.getenv("KOMPONIST_EMBEDDING_MODEL", "nomic-embed-text")
        self._httpx = httpx

    async def embed(self, text: str) -> List[float]:
        """
        Embed a single text using Ollama.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        async with self._httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text
                }
            )
            response.raise_for_status()
            data = response.json()

        embedding = data.get("embedding", [])

        # Pad or truncate to match expected dimensions
        if len(embedding) < self.DIMENSIONS:
            embedding.extend([0.0] * (self.DIMENSIONS - len(embedding)))
        elif len(embedding) > self.DIMENSIONS:
            embedding = embedding[:self.DIMENSIONS]

        return embedding

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts (sequentially for Ollama).

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        embeddings = []
        for text in texts:
            emb = await self.embed(text)
            embeddings.append(emb)
        return embeddings


# =============================================================================
# Provider Factory
# =============================================================================

def get_embedding_client(provider: Optional[str] = None) -> BaseEmbeddingClient:
    """
    Get embedding client for the specified provider.

    Args:
        provider: Provider name. Defaults to OpenAI. KOMPONIST_AI_MODE=mock
                  always selects the deterministic offline test double.

    Returns:
        Configured embedding client
    """
    ai_mode = os.getenv("KOMPONIST_AI_MODE", "live").lower()
    if ai_mode not in {"mock", "live"}:
        raise ValueError("KOMPONIST_AI_MODE must be 'mock' or 'live'")
    if ai_mode == "mock":
        return MockEmbeddingClient()

    provider = provider or os.getenv(
        "KOMPONIST_EMBEDDING_PROVIDER", EmbeddingProvider.OPENAI.value
    )

    if provider == EmbeddingProvider.MOCK:
        return MockEmbeddingClient()
    elif provider == EmbeddingProvider.OPENAI:
        return OpenAIEmbeddingClient()
    elif provider == EmbeddingProvider.OLLAMA:
        return OllamaEmbeddingClient()
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


# =============================================================================
# Global Client (Backwards Compatibility)
# =============================================================================

# Global client instance
_client: Optional[BaseEmbeddingClient] = None


def get_embedder() -> BaseEmbeddingClient:
    """Get global embedding client singleton."""
    global _client
    if _client is None:
        _client = get_embedding_client()
    return _client


def reset_embedder() -> None:
    """Reset the process-global client after configuration changes or in tests."""
    global _client
    _client = None


# Backwards-compatible alias
EmbeddingClient = OpenAIEmbeddingClient


# Convenience functions
async def embed(text: str) -> List[float]:
    """Convenience: embed single text."""
    return await get_embedder().embed(text)


async def embed_batch(texts: List[str]) -> List[List[float]]:
    """Convenience: embed multiple texts."""
    return await get_embedder().embed_batch(texts)


def combine_for_embedding(statement: str, detail: Optional[str] = None) -> str:
    """
    Combine statement and detail for embedding.

    Args:
        statement: One-sentence canonical statement
        detail: Optional detailed explanation

    Returns:
        Combined text for embedding
    """
    if detail:
        return f"{statement}\n\n{detail}"
    return statement
