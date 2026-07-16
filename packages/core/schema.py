"""
Neo4j Graph Schema

Defines and applies the Komponist brain schema: nodes, relationships, constraints, indexes.
"""

from typing import List, Dict, Any
from core.graph import GraphClient
from core.embeddings import EMBEDDING_DIMENSIONS


# Schema version for tracking
SCHEMA_VERSION = "1.1.0"


class GraphSchema:
    """Graph schema manager."""

    @staticmethod
    async def apply_schema():
        """
        Apply complete schema idempotently.

        Creates:
        - Uniqueness constraints
        - Property indexes
        - Full-text index
        - Vector index for embeddings
        """
        print("Applying graph schema...")

        # Uniqueness constraints
        constraints = [
            """
            CREATE CONSTRAINT entity_id IF NOT EXISTS
            FOR (e:Entity) REQUIRE e.id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT evidence_id IF NOT EXISTS
            FOR (v:Evidence) REQUIRE v.id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT person_id IF NOT EXISTS
            FOR (p:Person) REQUIRE p.id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT workpack_id IF NOT EXISTS
            FOR (w:WorkPack) REQUIRE w.id IS UNIQUE
            """
        ]

        for constraint in constraints:
            try:
                await GraphClient.run_query(constraint.strip())
                print(f"✓ Created constraint")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  Constraint already exists")
                else:
                    raise

        # Property indexes
        indexes = [
            """
            CREATE INDEX entity_org_status IF NOT EXISTS
            FOR (e:Entity) ON (e.org_id, e.status)
            """,
            """
            CREATE INDEX entity_type IF NOT EXISTS
            FOR (e:Entity) ON (e.entity_type)
            """,
            """
            CREATE INDEX evidence_org IF NOT EXISTS
            FOR (v:Evidence) ON (v.org_id)
            """,
            """
            CREATE INDEX workpack_org IF NOT EXISTS
            FOR (w:WorkPack) ON (w.org_id)
            """
        ]

        for index in indexes:
            try:
                await GraphClient.run_query(index.strip())
                print(f"✓ Created index")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  Index already exists")
                else:
                    raise

        # Full-text index for entity text search
        try:
            await GraphClient.run_query("""
                CREATE FULLTEXT INDEX entity_text IF NOT EXISTS
                FOR (e:Entity) ON EACH [e.statement, e.detail]
            """)
            print("✓ Created full-text index")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("  Full-text index already exists")
            else:
                raise

        # Vector index for embeddings (Neo4j 5.x native). Neo4j cannot change
        # vector dimensions in place, so discard derived vectors and rebuild the
        # index when the configured dimension changes.
        try:
            existing_indexes = await GraphClient.run_query("""
                SHOW VECTOR INDEXES YIELD name, options
                WHERE name = 'entity_embedding'
                RETURN options
            """)
            if existing_indexes:
                options = existing_indexes[0].get("options") or {}
                index_config = options.get("indexConfig") or {}
                current_dimensions = index_config.get("vector.dimensions")
                if current_dimensions != EMBEDDING_DIMENSIONS:
                    await GraphClient.run_query(
                        "DROP INDEX entity_embedding IF EXISTS"
                    )
                    await GraphClient.run_query("""
                        MATCH (e:Entity)
                        WHERE e.embedding IS NOT NULL
                        REMOVE e.embedding
                    """)
                    print(
                        f"✓ Removed {current_dimensions}-dimensional vector index "
                        f"and stale embeddings"
                    )

            await GraphClient.run_query(f"""
                CREATE VECTOR INDEX entity_embedding IF NOT EXISTS
                FOR (e:Entity) ON (e.embedding)
                OPTIONS {{
                  indexConfig: {{
                    `vector.dimensions`: {EMBEDDING_DIMENSIONS},
                    `vector.similarity_function`: 'cosine'
                  }}
                }}
            """)
            print(
                f"✓ Created vector index ({EMBEDDING_DIMENSIONS} dims, "
                "cosine similarity)"
            )
        except Exception as e:
            if "already exists" in str(e).lower():
                print("  Vector index already exists")
            else:
                raise

        print(f"Schema v{SCHEMA_VERSION} applied successfully")

    @staticmethod
    async def verify_schema() -> Dict[str, Any]:
        """
        Verify schema is correctly applied.

        Returns:
            Dict with constraints, indexes, and node/relationship counts
        """
        # Get constraints
        constraints_result = await GraphClient.run_query("SHOW CONSTRAINTS")
        constraints = [r.get("name") for r in constraints_result]

        # Get indexes
        indexes_result = await GraphClient.run_query("SHOW INDEXES")
        indexes = [r.get("name") for r in indexes_result]

        # Get counts
        counts_result = await GraphClient.run_query("""
            MATCH (e:Entity)
            WITH count(e) as entities
            MATCH (v:Evidence)
            WITH entities, count(v) as evidence
            MATCH (p:Person)
            WITH entities, evidence, count(p) as people
            MATCH (w:WorkPack)
            RETURN entities, evidence, people, count(w) as workpacks
        """)

        counts = counts_result[0] if counts_result else {
            "entities": 0, "evidence": 0, "people": 0, "workpacks": 0
        }

        return {
            "version": SCHEMA_VERSION,
            "constraints": constraints,
            "indexes": indexes,
            "counts": counts
        }


async def seed_test_data(org_id: str = "test-org"):
    """
    Seed test data for development/testing.

    Creates a small graph with:
    - 3 decisions (one superseded)
    - 2 goals
    - 1 constraint
    - 1 project
    - Evidence nodes
    - Relationships
    """
    print(f"Seeding test data for org: {org_id}")

    queries = [
        # Decision 1: Use Neo4j (confirmed)
        """
        CREATE (d:Entity:Decision {
            id: 'dec-neo4j',
            org_id: $org_id,
            entity_type: 'Decision',
            statement: 'Use Neo4j as the company brain storage',
            detail: 'Neo4j 5 native vector indexes eliminate need for separate vector DB.',
            status: 'confirmed',
            confidence: 'high',
            created_at: datetime(),
            updated_at: datetime(),
            confirmed_at: datetime()
        })
        CREATE (e:Evidence {
            id: 'ev-1',
            org_id: $org_id,
            source: 'manual',
            reference: 'ADR-001',
            excerpt: 'Decision: Use Neo4j 5.x as the sole brain storage.',
            source_date: datetime()
        })
        CREATE (d)-[:CITED_BY]->(e)
        """,

        # Decision 2: Python backend (confirmed)
        """
        CREATE (d:Entity:Decision {
            id: 'dec-python',
            org_id: $org_id,
            entity_type: 'Decision',
            statement: 'Use Python FastAPI for the backend',
            detail: 'FastAPI provides async-native, excellent performance, and great docs.',
            status: 'confirmed',
            confidence: 'high',
            created_at: datetime(),
            updated_at: datetime(),
            confirmed_at: datetime()
        })
        CREATE (e:Evidence {
            id: 'ev-2',
            org_id: $org_id,
            source: 'manual',
            reference: 'ADR-003',
            excerpt: 'Decision: Python 3.12, FastAPI for API/webhooks',
            source_date: datetime()
        })
        CREATE (d)-[:CITED_BY]->(e)
        """,

        # Decision 3: Old auth approach (superseded)
        """
        CREATE (d_old:Entity:Decision {
            id: 'dec-auth-old',
            org_id: $org_id,
            entity_type: 'Decision',
            statement: 'Use internal auth service',
            detail: 'Build custom authentication from scratch.',
            status: 'superseded',
            confidence: 'medium',
            created_at: datetime() - duration('P7D'),
            updated_at: datetime()
        })
        CREATE (d_new:Entity:Decision {
            id: 'dec-auth-new',
            org_id: $org_id,
            entity_type: 'Decision',
            statement: 'Use WorkOS for enterprise identity',
            detail: 'WorkOS handles SSO, directory sync, and compliance.',
            status: 'confirmed',
            confidence: 'high',
            created_at: datetime(),
            updated_at: datetime(),
            confirmed_at: datetime()
        })
        CREATE (e:Evidence {
            id: 'ev-3',
            org_id: $org_id,
            source: 'github',
            reference: 'PR#142',
            url: 'https://github.com/example/repo/pull/142',
            excerpt: 'Switching to WorkOS for better compliance story.',
            source_date: datetime()
        })
        CREATE (d_new)-[:CITED_BY]->(e)
        CREATE (d_new)-[:SUPERSEDES]->(d_old)
        """,

        # Goal 1: Ship MVP
        """
        CREATE (g:Entity:Goal {
            id: 'goal-mvp',
            org_id: $org_id,
            entity_type: 'Goal',
            statement: 'Ship Komponist MVP to 10 design partners',
            detail: 'MVP must include: 3 integrations, review queue, MCP server, constraint checking.',
            status: 'confirmed',
            confidence: 'high',
            created_at: datetime(),
            updated_at: datetime(),
            confirmed_at: datetime()
        })
        CREATE (e:Evidence {
            id: 'ev-4',
            org_id: $org_id,
            source: 'manual',
            reference: 'BUILD_PLAN',
            excerpt: 'MVP Definition of Done section',
            source_date: datetime()
        })
        CREATE (g)-[:CITED_BY]->(e)
        """,

        # Goal 2: YC application
        """
        CREATE (g:Entity:Goal {
            id: 'goal-yc',
            org_id: $org_id,
            entity_type: 'Goal',
            statement: 'Apply to Y Combinator with demo and traction',
            detail: 'Need end-to-end demo video and tool_calls metrics.',
            status: 'confirmed',
            confidence: 'high',
            created_at: datetime(),
            updated_at: datetime(),
            confirmed_at: datetime()
        })
        """,

        # Constraint: No auto-confirm
        """
        CREATE (c:Entity:Constraint {
            id: 'con-review',
            org_id: $org_id,
            entity_type: 'Constraint',
            statement: 'Never auto-confirm extracted entities',
            detail: 'All facts must go through human review. Trust requires human-in-the-loop.',
            status: 'confirmed',
            confidence: 'high',
            enforcement: 'block',
            created_at: datetime(),
            updated_at: datetime(),
            confirmed_at: datetime()
        })
        CREATE (e:Evidence {
            id: 'ev-5',
            org_id: $org_id,
            source: 'manual',
            reference: 'ADR-009',
            excerpt: 'Human-in-the-loop is core to trust',
            source_date: datetime()
        })
        CREATE (c)-[:CITED_BY]->(e)
        """,

        # Project: Step 2 Implementation
        """
        CREATE (p:Entity:Project {
            id: 'proj-step2',
            org_id: $org_id,
            entity_type: 'Project',
            statement: 'Implement graph schema and core queries',
            detail: 'Step 2 of build plan: schema, constraints, indexes, 5 core queries.',
            status: 'confirmed',
            confidence: 'high',
            created_at: datetime(),
            updated_at: datetime(),
            confirmed_at: datetime()
        })
        """,

        # Relationships
        """
        MATCH (p:Project {id: 'proj-step2', org_id: $org_id})
        MATCH (g:Goal {id: 'goal-mvp', org_id: $org_id})
        MERGE (p)-[:ADVANCES]->(g)
        """,
        """
        MATCH (d:Decision {id: 'dec-auth-new', org_id: $org_id})
        MATCH (p:Project {id: 'proj-step2', org_id: $org_id})
        MERGE (d)-[:AFFECTS]->(p)
        """,
    ]

    for query in queries:
        await GraphClient.run_query(query.strip(), {"org_id": org_id})

    print(f"✓ Test data seeded (6 entities, relationships, evidence)")


if __name__ == "__main__":
    import asyncio

    async def main():
        GraphClient.initialize()
        await GraphSchema.apply_schema()
        verification = await GraphSchema.verify_schema()
        print("\nSchema verification:")
        print(f"  Constraints: {len(verification['constraints'])}")
        print(f"  Indexes: {len(verification['indexes'])}")
        print(f"  Node counts: {verification['counts']}")

        # Optionally seed test data
        # await seed_test_data()

        await GraphClient.close()

    asyncio.run(main())
