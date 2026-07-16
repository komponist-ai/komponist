"""
Security utilities.

Org isolation verification, input validation, rate limiting.
"""

from functools import wraps
from typing import Callable, Any
import hashlib
import secrets


def verify_org_isolation(query: str) -> bool:
    """
    Verify that a Cypher query properly filters by org_id.

    Args:
        query: Cypher query string

    Returns:
        True if query includes org_id filter
    """
    query_lower = query.lower()

    # Check for org_id in WHERE or property match
    has_org_filter = (
        "org_id = $org_id" in query_lower or
        "{org_id: $org_id" in query_lower or
        "org_id: $org_id}" in query_lower
    )

    return has_org_filter


def require_org_isolation(func: Callable) -> Callable:
    """
    Decorator to verify org isolation in graph queries.

    Usage:
        @require_org_isolation
        async def my_query(query: str, params: dict):
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Get query from args or kwargs
        query = args[0] if args else kwargs.get("query", "")

        if not verify_org_isolation(query):
            raise ValueError(
                "Query must filter by org_id for security. "
                "Include 'org_id = $org_id' in WHERE clause or {org_id: $org_id} in node match."
            )

        return await func(*args, **kwargs)

    return wrapper


def hash_api_key(api_key: str) -> str:
    """
    Hash API key for storage.

    Uses SHA-256 with salt for one-way hashing.

    Args:
        api_key: Raw API key

    Returns:
        Hashed key (hex)
    """
    # In production, use a proper salt (stored separately)
    salt = b"komponist-api-key-salt-v1"
    return hashlib.sha256(salt + api_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key.

    Returns:
        Tuple of (raw_key, hashed_key)
    """
    raw_key = f"komponist_{secrets.token_urlsafe(32)}"
    hashed_key = hash_api_key(raw_key)
    return raw_key, hashed_key


def validate_org_id(org_id: str) -> bool:
    """
    Validate org_id format.

    Args:
        org_id: Organization ID

    Returns:
        True if valid format
    """
    if not org_id:
        return False

    # Must be lowercase alphanumeric with hyphens, 3-50 chars
    if not org_id.replace("-", "").replace("_", "").isalnum():
        return False

    if not org_id.islower():
        return False

    if len(org_id) < 3 or len(org_id) > 50:
        return False

    return True


def sanitize_input(text: str, max_length: int = 10000) -> str:
    """
    Sanitize user input.

    Args:
        text: Input text
        max_length: Maximum allowed length

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Truncate
    text = text[:max_length]

    # Remove null bytes
    text = text.replace("\x00", "")

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self):
        self._requests = {}  # key -> list of timestamps

    def check_limit(
        self,
        key: str,
        limit: int = 100,
        window_seconds: int = 60
    ) -> bool:
        """
        Check if key is within rate limit.

        Args:
            key: Identifier (e.g., org_id, ip)
            limit: Max requests per window
            window_seconds: Time window in seconds

        Returns:
            True if within limit
        """
        import time

        now = time.time()
        cutoff = now - window_seconds

        # Get requests for this key
        if key not in self._requests:
            self._requests[key] = []

        # Remove old requests
        self._requests[key] = [
            ts for ts in self._requests[key]
            if ts > cutoff
        ]

        # Check limit
        if len(self._requests[key]) >= limit:
            return False

        # Add new request
        self._requests[key].append(now)
        return True


# Global rate limiter instance
rate_limiter = RateLimiter()


def check_rate_limit(org_id: str, limit: int = 100) -> bool:
    """
    Check rate limit for org.

    Args:
        org_id: Organization ID
        limit: Requests per minute

    Returns:
        True if within limit
    """
    return rate_limiter.check_limit(org_id, limit=limit, window_seconds=60)
