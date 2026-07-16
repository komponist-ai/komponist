"""
LLM Wrapper

Centralized interface for LLM calls with retry logic and structured output.

OpenAI is the production default. ``KOMPONIST_AI_MODE=mock`` enables a
deterministic, no-network test double so the application can be developed
before an API key or credits are available.
"""

import asyncio
import json
import os
import re
import time
from copy import deepcopy
from typing import Optional, Dict, Any, List, AsyncGenerator
from enum import Enum
from abc import ABC, abstractmethod


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    MOCK = "mock"
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
    GPT56 = "gpt-5.6"
    GPT56_TERRA = "gpt-5.6-terra"
    GPT56_LUNA = "gpt-5.6-luna"
    # Ollama (common models)
    LLAMA3 = "llama3"
    MISTRAL = "mistral"
    MIXTRAL = "mixtral"


def _schema_example(schema: Dict[str, Any]) -> Any:
    """Build a minimal deterministic value that satisfies a JSON schema."""
    if "default" in schema:
        return deepcopy(schema["default"])
    if schema.get("enum"):
        return deepcopy(schema["enum"][0])
    if schema.get("anyOf"):
        candidates = [item for item in schema["anyOf"] if item.get("type") != "null"]
        return _schema_example(candidates[0] if candidates else schema["anyOf"][0])

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), "null")

    if schema_type == "object":
        properties = schema.get("properties", {})
        return {
            name: _schema_example(properties[name])
            for name in schema.get("required", [])
            if name in properties
        }
    if schema_type == "array":
        return []
    if schema_type == "boolean":
        return False
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0.0
    if schema_type == "null":
        return None
    return ""


def _validate_schema(value: Any, schema: Dict[str, Any], path: str = "$") -> None:
    """Validate the JSON-schema subset used by Komponist extraction contracts."""
    if "anyOf" in schema:
        errors = []
        for candidate in schema["anyOf"]:
            try:
                _validate_schema(value, candidate, path)
                return
            except ValueError as exc:
                errors.append(str(exc))
        raise ValueError(f"{path} does not match any allowed schema: {'; '.join(errors)}")

    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} must be one of {schema['enum']}, got {value!r}")

    schema_type = schema.get("type")
    allowed_types = schema_type if isinstance(schema_type, list) else [schema_type]
    if schema_type is not None:
        type_checks = {
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
            "string": lambda item: isinstance(item, str),
            "boolean": lambda item: isinstance(item, bool),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "null": lambda item: item is None,
        }
        if not any(type_checks.get(kind, lambda _item: True)(value) for kind in allowed_types):
            raise ValueError(f"{path} must be {schema_type}, got {type(value).__name__}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for field in schema.get("required", []):
            if field not in value:
                raise ValueError(f"{path} is missing required field {field!r}")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise ValueError(f"{path} contains unexpected fields: {extras}")
        for field, item in value.items():
            if field in properties:
                _validate_schema(item, properties[field], f"{path}.{field}")

    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate_schema(item, schema["items"], f"{path}[{index}]")


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
        max_retries: int = 3,
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
            json_mode=True,
            schema=schema,
            max_retries=max_retries,
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

        if schema:
            _validate_schema(data, schema)

        return data

    async def stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> AsyncGenerator[str, None]:
        """Provide a safe one-chunk fallback for clients without native streaming."""
        response = await self.call(
            prompt=prompt,
            model=model,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        yield response["text"]


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

        if json_mode and system:
            system += "\n\nYou must respond with valid JSON only. No markdown, no explanation."

        for attempt in range(max_retries):
            try:
                start = time.time()

                response = await self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system or "",
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

            except ValueError:
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
    """OpenAI Responses API client."""

    def __init__(self, api_key: Optional[str] = None, client: Any = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if client is None:
            from openai import AsyncOpenAI

            if not self.api_key:
                raise ValueError(
                    "OPENAI_API_KEY is not set. Use KOMPONIST_AI_MODE=mock "
                    "for offline development."
                )
            client = AsyncOpenAI(api_key=self.api_key)

        self.client = client
        self.default_model = os.getenv("KOMPONIST_LLM_MODEL", Model.GPT56_TERRA)
        self.store = os.getenv("KOMPONIST_OPENAI_STORE", "false").lower() == "true"

    @staticmethod
    def _schema_name(schema: Dict[str, Any]) -> str:
        title = str(schema.get("title", "komponist_response")).lower()
        name = re.sub(r"[^a-z0-9_-]+", "_", title).strip("_")
        return (name or "komponist_response")[:64]

    @staticmethod
    def _refusal(response: Any) -> Optional[str]:
        for output in getattr(response, "output", []) or []:
            for item in getattr(output, "content", []) or []:
                refusal = getattr(item, "refusal", None)
                if refusal:
                    return refusal
        return None

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

        instructions = system or ""
        if json_mode and not schema:
            instructions = (
                instructions
                + "\n\nReturn a valid JSON object only. Do not use Markdown or explanatory text."
            ).strip()

        kwargs: Dict[str, Any] = {
            "model": model,
            "input": prompt,
            "max_output_tokens": max_tokens,
            "store": self.store,
        }
        if instructions:
            kwargs["instructions"] = instructions
        # GPT-5 reasoning models reject the legacy sampling parameter.
        if temperature is not None and not model.startswith("gpt-5"):
            kwargs["temperature"] = temperature
        if schema:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": self._schema_name(schema),
                    "strict": True,
                    "schema": schema,
                }
            }
        elif json_mode:
            kwargs["text"] = {"format": {"type": "json_object"}}

        for attempt in range(max_retries):
            try:
                start = time.time()

                response = await self.client.responses.create(**kwargs)

                latency_ms = int((time.time() - start) * 1000)
                refusal = self._refusal(response)
                if refusal:
                    raise ValueError(f"OpenAI refused the request: {refusal}")

                status = getattr(response, "status", "completed")
                if status != "completed":
                    details = getattr(response, "incomplete_details", None)
                    raise ValueError(f"OpenAI response status is {status}: {details}")

                text = getattr(response, "output_text", "")
                if not text:
                    raise ValueError("OpenAI response contained no output text")

                usage = getattr(response, "usage", None)

                return {
                    "text": text,
                    "usage": {
                        "input_tokens": getattr(usage, "input_tokens", 0),
                        "output_tokens": getattr(usage, "output_tokens", 0),
                    },
                    "model": model,
                    "latency_ms": latency_ms,
                    "response_id": getattr(response, "id", None),
                }

            except ValueError:
                raise
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"Error: {e}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise


_MOCK_MVP_MARKER = re.compile(
    r"(?im)^\s*(?:(?:[-+*]|\d+[.)]|#{1,6})\s+)?"
    r"(?:\*\*)?(Decision|Goal|Constraint|Project)\s*:(?:\*\*)?\s*(.+?)\s*$"
)


def _mock_prompt_body(prompt: str) -> str:
    """Return the source body embedded in an extraction/classification prompt."""
    body = prompt.split("\nBody:\n", 1)[-1]
    for suffix in (
        "\n\nExtract all relevant items:",
        "\n\nDoes this contain extractable information?",
    ):
        body = body.split(suffix, 1)[0]
    return body


def _mock_marked_facts(prompt: str) -> List[Dict[str, Any]]:
    """Extract explicit MVP markers for deterministic no-model development."""
    facts: List[Dict[str, Any]] = []
    seen = set()

    for match in _MOCK_MVP_MARKER.finditer(_mock_prompt_body(prompt)):
        entity_type = match.group(1)
        statement = match.group(2).strip()
        key = (entity_type, statement.casefold())
        if not statement or key in seen:
            continue

        seen.add(key)
        facts.append({
            "type": entity_type,
            "statement": statement,
            "detail": f"Extracted from an explicit {entity_type.lower()} marker.",
            "excerpt": match.group(0).strip(),
            "confidence": "high",
            "relations_hint": [],
        })

    return facts


class MockLLMClient(BaseLLMClient):
    """No-network LLM test double for development before API access exists."""

    def __init__(self, responses: Optional[List[Any]] = None):
        self.responses = list(responses or [])
        self.default_model = "mock-openai"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        json_mode: bool = False,
        schema: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        del system, max_tokens, temperature, max_retries

        if self.responses:
            value = self.responses.pop(0)
        elif schema and schema.get("title") == "source_classification":
            facts = _mock_marked_facts(prompt)
            value = {
                "is_relevant": bool(facts),
                "reasoning": (
                    "Contains explicit MVP entity markers."
                    if facts
                    else "No explicit MVP entity markers found."
                ),
            }
        elif schema and schema.get("title") == "komponist_fact_extraction":
            value = {"facts": _mock_marked_facts(prompt)}
        elif schema:
            value = _schema_example(schema)
        elif json_mode:
            value = {}
        else:
            value = "Mock response: no OpenAI request was made."

        text = value if isinstance(value, str) else json.dumps(value)
        return {
            "text": text,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "model": model or self.default_model,
            "latency_ms": 0,
            "response_id": None,
        }


class OllamaClient(BaseLLMClient):
    """Ollama local LLM client."""

    def __init__(self, base_url: Optional[str] = None):
        import httpx

        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.default_model = os.getenv("KOMPONIST_LLM_MODEL", Model.LLAMA3)
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

        full_prompt = ""
        if system:
            sys_prompt = system
            if json_mode:
                sys_prompt += "\n\nYou must respond with valid JSON only. No markdown, no explanation."
            full_prompt = f"{sys_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt

        for attempt in range(max_retries):
            try:
                start = time.time()

                async with self._httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        f"{self.base_url}/api/generate",
                        json={
                            "model": model,
                            "prompt": full_prompt,
                            "stream": False,
                            "options": {
                                "num_predict": max_tokens,
                                "temperature": temperature
                            }
                        }
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
        provider: Provider name. Defaults to KOMPONIST_LLM_PROVIDER or OpenAI.
                  KOMPONIST_AI_MODE=mock always selects the offline test double.

    Returns:
        Configured LLM client
    """
    ai_mode = os.getenv("KOMPONIST_AI_MODE", "live").lower()
    if ai_mode not in {"mock", "live"}:
        raise ValueError("KOMPONIST_AI_MODE must be 'mock' or 'live'")
    if ai_mode == "mock":
        return MockLLMClient()

    provider = provider or os.getenv("KOMPONIST_LLM_PROVIDER", LLMProvider.OPENAI.value)

    if provider == LLMProvider.MOCK:
        return MockLLMClient()
    elif provider == LLMProvider.ANTHROPIC:
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
LLMClient = OpenAIClient


def reset_llm() -> None:
    """Reset the process-global client after configuration changes or in tests."""
    global _client
    _client = None


# Convenience functions
async def call_llm(prompt: str, **kwargs) -> Dict[str, Any]:
    """Convenience: call LLM."""
    return await get_llm().call(prompt, **kwargs)


async def call_llm_json(prompt: str, **kwargs) -> Dict[str, Any]:
    """Convenience: call LLM with JSON output."""
    return await get_llm().call_json(prompt, **kwargs)
