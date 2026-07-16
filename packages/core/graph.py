"""
Neo4j Graph Client

Async Neo4j driver singleton with connection pooling and health checks.
"""

import os
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import ServiceUnavailable, AuthError


class GraphClient:
    """Singleton async Neo4j driver."""

    _driver: Optional[AsyncDriver] = None
    _uri: str
    _auth: tuple

    @classmethod
    def initialize(
        cls,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """Initialize the driver singleton."""
        cls._uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        username = username or os.getenv("NEO4J_USERNAME", "neo4j")
        password = password or os.getenv("NEO4J_PASSWORD", "devpassword")
        cls._auth = (username, password)

        cls._driver = AsyncGraphDatabase.driver(
            cls._uri,
            auth=cls._auth,
            max_connection_lifetime=3600,
            max_connection_pool_size=50,
            connection_acquisition_timeout=60.0
        )

    @classmethod
    async def close(cls):
        """Close the driver connection pool."""
        if cls._driver:
            await cls._driver.close()
            cls._driver = None

    @classmethod
    def get_driver(cls) -> AsyncDriver:
        """Get the driver instance."""
        if not cls._driver:
            cls.initialize()
        return cls._driver

    @classmethod
    @asynccontextmanager
    async def session(cls, database: str = "neo4j") -> AsyncSession:
        """Context manager for Neo4j sessions."""
        driver = cls.get_driver()
        session = driver.session(database=database)
        try:
            yield session
        finally:
            await session.close()

    @classmethod
    async def run_query(
        cls,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
        database: str = "neo4j"
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results as list of dicts.

        Args:
            cypher: Cypher query string
            params: Query parameters
            database: Target database name

        Returns:
            List of result records as dictionaries

        Raises:
            ServiceUnavailable: Database connection failed
            AuthError: Authentication failed
        """
        async with cls.session(database=database) as session:
            result = await session.run(cypher, params or {})
            records = await result.data()
            return records

    @classmethod
    async def health_check(cls) -> Dict[str, Any]:
        """
        Check Neo4j connection health.

        Returns:
            Dict with status, uri, and database info
        """
        try:
            driver = cls.get_driver()
            await driver.verify_connectivity()

            # Get database info
            records = await cls.run_query("CALL dbms.components() YIELD name, versions RETURN name, versions[0] as version")

            return {
                "status": "healthy",
                "uri": cls._uri,
                "database": records[0] if records else {"name": "unknown", "version": "unknown"}
            }
        except ServiceUnavailable as e:
            return {
                "status": "unavailable",
                "uri": cls._uri,
                "error": str(e)
            }
        except AuthError as e:
            return {
                "status": "auth_error",
                "uri": cls._uri,
                "error": str(e)
            }
        except Exception as e:
            return {
                "status": "error",
                "uri": cls._uri,
                "error": str(e)
            }


# Convenience alias
graph = GraphClient
