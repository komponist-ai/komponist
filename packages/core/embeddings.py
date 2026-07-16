"""
Embedding utilities.

Supports multiple providers: OpenAI, Ollama.
Default: OpenAI text-embedding-3-small (1536 dims)
"""

import os
from typing import List, Optional
from abc import ABC, abstractmethod
from enum import Enum


class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""
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

    def __init__(self, api_key: Optional[str] = None):
        from openai import AsyncOpenAI

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")

        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = os.getenv("KOMPONIST_EMBEDDING_MODEL", "text-embedding-3-small")

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
            dimensions=self.DIMENSIONS
        )

        return response.data[0].embedding

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts in batch.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.DIMENSIONS
        )

        # Sort by index to maintain order
        embeddings = sorted(response.data, key=lambda x: x.index)
        return [e.embedding for e in embeddings]


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
        provider: Provider name (openai, ollama).
                  Defaults to KOMPONIST_EMBEDDING_PROVIDER env var or 'openai'.

    Returns:
        Configured embedding client
    """
    provider = provider or os.getenv("KOMPONIST_EMBEDDING_PROVIDER", EmbeddingProvider.OPENAI)

    if provider == EmbeddingProvider.OPENAI:
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
