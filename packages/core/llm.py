"""
LLM Wrapper

Centralized interface for LLM calls with retry logic, JSON parsing, and cost tracking.
Supports multiple providers: Anthropic, OpenAI, Ollama.
"""

import os
import json
import time
import asyncio
from typing import Optional, Dict, Any, List, Protocol, AsyncGenerator
from enum import Enum
from abc import ABC, abstractmethod


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class Model(str, Enum):
    """Common model identifiers."""
    # Anthropic
    OPUS = "claude-opus-4-8"
    SONNET = "claude-sonnet-4-20250514"
    HAIKU = "claude-haiku-4-5-20251001"
    # OpenAI
    GPT4 = "gpt-4-turbo"
    GPT4O = "gpt-4o"
    GPT35 = "gpt-3.5-turbo"
    # Ollama (common models)
    QWEN35 = "qwen3.5:9b"
    LLAMA3 = "llama3"
    MISTRAL = "mistral"
    MIXTRAL = "mixtral"


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        json_mode: bool = False,
        schema: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """Call the LLM."""
        pass

    async def call_json(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        """
        Call LLM and parse JSON output.

        Args:
            prompt: User prompt
            model: Model to use
            system: System prompt
            max_tokens: Maximum output tokens
            schema: Optional JSON schema for validation

        Returns:
            Parsed JSON object

        Raises:
            ValueError: If response is not valid JSON
        """
        response = await self.call(
            prompt=prompt,
            model=model,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
            schema=schema
        )

        text = response["text"].strip()

        # Try to extract JSON from markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        text = text.strip("`").strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e}\n{text[:200]}")

        # Basic schema validation if provided
        if schema and "required" in schema:
            for field in schema["required"]:
                if field not in data:
                    raise ValueError(f"Missing required field: {field}")

        return data


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude LLM client."""

    def __init__(self, api_key: Optional[str] = None):
        from anthropic import AsyncAnthropic
        import anthropic

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.client = AsyncAnthropic(api_key=self.api_key)
        self.default_model = os.getenv("KOMPONIST_LLM_MODEL", Model.SONNET)
        self._anthropic = anthropic

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        json_mode: bool = False,
        schema: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        model = model or self.default_model

        messages = [{"role": "user", "content": prompt}]

        system_prompt = system or ""
        if json_mode:
            system_prompt += "\n\nYou must respond with valid JSON only. No markdown, no explanation."
        if schema:
            system_prompt += f"\n\nThe response must match this JSON Schema:\n{json.dumps(schema)}"

        for attempt in range(max_retries):
            try:
                start = time.time()

                response = await self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=messages
                )

                latency_ms = int((time.time() - start) * 1000)
                text = response.content[0].text

                return {
                    "text": text,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens
                    },
                    "model": model,
                    "latency_ms": latency_ms
                }

            except self._anthropic.RateLimitError:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"Rate limit hit, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise

            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"Error: {e}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise

    async def stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ) -> AsyncGenerator[str, None]:
        """
        Stream LLM response token by token.

        Args:
            prompt: User prompt
            model: Model to use
            system: System prompt
            max_tokens: Maximum output tokens
            temperature: Sampling temperature

        Yields:
            Text chunks as they arrive
        """
        model = model or self.default_model
        messages = [{"role": "user", "content": prompt}]

        async with self.client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "",
            messages=messages
        ) as stream:
            async for text in stream.text_stream:
                yield text


class OpenAIClient(BaseLLMClient):
    """OpenAI GPT LLM client."""

    def __init__(self, api_key: Optional[str] = None):
        from openai import AsyncOpenAI

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")

        self.client = AsyncOpenAI(api_key=self.api_key)
        self.default_model = os.getenv("KOMPONIST_LLM_MODEL", Model.GPT4O)

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        json_mode: bool = False,
        schema: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        model = model or self.default_model

        messages = []
        sys_prompt = system or ""
        if json_mode:
            sys_prompt += "\n\nYou must respond with valid JSON only. No markdown, no explanation."
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(max_retries):
            try:
                start = time.time()

                kwargs = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": messages
                }

                if json_mode and schema:
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "komponist_response",
                            "strict": True,
                            "schema": schema
                        }
                    }
                elif json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                response = await self.client.chat.completions.create(**kwargs)

                latency_ms = int((time.time() - start) * 1000)
                text = response.choices[0].message.content

                return {
                    "text": text,
                    "usage": {
                        "input_tokens": response.usage.prompt_tokens,
                        "output_tokens": response.usage.completion_tokens
                    },
                    "model": model,
                    "latency_ms": latency_ms
                }

            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"Error: {e}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise


class OllamaClient(BaseLLMClient):
    """Ollama local LLM client."""

    def __init__(self, base_url: Optional[str] = None):
        import httpx

        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.default_model = os.getenv("KOMPONIST_LLM_MODEL", Model.QWEN35)
        self._httpx = httpx

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        json_mode: bool = False,
        schema: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        model = model or self.default_model

        for attempt in range(max_retries):
            try:
                start = time.time()

                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature
                    }
                }
                if system:
                    payload["system"] = system
                if json_mode:
                    payload["format"] = schema or "json"
                    # Reasoning-capable local models may otherwise place the
                    # structured object in Ollama's separate `thinking` field.
                    payload["think"] = False

                async with self._httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        f"{self.base_url}/api/generate",
                        json=payload
                    )
                    response.raise_for_status()
                    data = response.json()

                latency_ms = int((time.time() - start) * 1000)

                return {
                    "text": data.get("response", ""),
                    "usage": {
                        "input_tokens": data.get("prompt_eval_count", 0),
                        "output_tokens": data.get("eval_count", 0)
                    },
                    "model": model,
                    "latency_ms": latency_ms
                }

            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"Error: {e}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise


# =============================================================================
# Provider Factory
# =============================================================================

def get_llm_client(provider: Optional[str] = None) -> BaseLLMClient:
    """
    Get LLM client for the specified provider.

    Args:
        provider: Provider name (anthropic, openai, ollama).
                  Defaults to KOMPONIST_LLM_PROVIDER env var or 'anthropic'.

    Returns:
        Configured LLM client
    """
    provider = provider or os.getenv("KOMPONIST_LLM_PROVIDER", LLMProvider.ANTHROPIC)

    if provider == LLMProvider.ANTHROPIC:
        return AnthropicClient()
    elif provider == LLMProvider.OPENAI:
        return OpenAIClient()
    elif provider == LLMProvider.OLLAMA:
        return OllamaClient()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


# =============================================================================
# Global Client (Backwards Compatibility)
# =============================================================================

# Global client instance
_client: Optional[BaseLLMClient] = None


def get_llm() -> BaseLLMClient:
    """Get global LLM client singleton."""
    global _client
    if _client is None:
        _client = get_llm_client()
    return _client


# Backwards-compatible LLMClient alias
LLMClient = AnthropicClient


# Convenience functions
async def call_llm(prompt: str, **kwargs) -> Dict[str, Any]:
    """Convenience: call LLM."""
    return await get_llm().call(prompt, **kwargs)


async def call_llm_json(prompt: str, **kwargs) -> Dict[str, Any]:
    """Convenience: call LLM with JSON output."""
    return await get_llm().call_json(prompt, **kwargs)
