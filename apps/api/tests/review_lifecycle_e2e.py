"""Local E2E check for review lifecycle mutations.

Run inside the API container while the stack is healthy:
    python tests/review_lifecycle_e2e.py
"""

import asyncio

import httpx

from core.graph import GraphClient


ORG_ID = "e2e-review-lifecycle"


async def seed() -> None:
    await GraphClient.run_query(
        "MATCH (n) WHERE n.org_id = $org_id DETACH DELETE n",
        {"org_id": ORG_ID},
    )
    await GraphClient.run_query(
        """
        CREATE (goal:Entity:Goal {
            id: 'review-confirm', org_id: $org_id, entity_type: 'Goal',
            statement: 'Original goal', status: 'proposed', confidence: 'high',
            created_at: datetime(), updated_at: datetime()
        })
        CREATE (constraint:Entity:Constraint {
            id: 'review-reject', org_id: $org_id, entity_type: 'Constraint',
            statement: 'Reject this constraint', status: 'proposed', confidence: 'low',
            created_at: datetime(), updated_at: datetime()
        })
        CREATE (target:Entity:Decision {
            id: 'review-target', org_id: $org_id, entity_type: 'Decision',
            statement: 'Canonical decision', status: 'confirmed', confidence: 'high',
            created_at: datetime(), updated_at: datetime(), confirmed_at: datetime()
        })
        CREATE (source:Entity:Decision {
            id: 'review-source', org_id: $org_id, entity_type: 'Decision',
            statement: 'Duplicate decision', status: 'proposed', confidence: 'medium',
            created_at: datetime(), updated_at: datetime()
        })
        CREATE (wrong:Entity:Project {
            id: 'review-wrong-type', org_id: $org_id, entity_type: 'Project',
            statement: 'Wrong merge type', status: 'proposed', confidence: 'medium',
            created_at: datetime(), updated_at: datetime()
        })
        CREATE (target_ev:Evidence {
            id: 'review-target-ev', org_id: $org_id, source: 'manual',
            reference: 'target', excerpt: 'target evidence',
            source_date: datetime(), created_at: datetime()
        })
        CREATE (source_ev_1:Evidence {
            id: 'review-source-ev-1', org_id: $org_id, source: 'manual',
            reference: 'source-1', excerpt: 'source evidence one',
            source_date: datetime(), created_at: datetime()
        })
        CREATE (source_ev_2:Evidence {
            id: 'review-source-ev-2', org_id: $org_id, source: 'manual',
            reference: 'source-2', excerpt: 'source evidence two',
            source_date: datetime(), created_at: datetime()
        })
        CREATE (target)-[:CITED_BY]->(target_ev)
        CREATE (source)-[:CITED_BY]->(source_ev_1)
        CREATE (source)-[:CITED_BY]->(source_ev_2)
        """,
        {"org_id": ORG_ID},
    )


async def run() -> None:
    GraphClient.initialize()
    await seed()

    try:
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            confirm = await client.post(
                f"/entities/review-confirm/confirm?org_id={ORG_ID}",
                json={"statement": "Edited and confirmed goal"},
            )
            assert confirm.status_code == 200, confirm.text
            assert confirm.json()["status"] == "confirmed"

            confirm_again = await client.post(
                f"/entities/review-confirm/confirm?org_id={ORG_ID}",
                json={"statement": "Must not overwrite"},
            )
            assert confirm_again.status_code == 409, confirm_again.text

            reject = await client.post(
                f"/entities/review-reject/reject?org_id={ORG_ID}"
            )
            assert reject.status_code == 200, reject.text
            assert reject.json()["status"] == "rejected"

            reject_again = await client.post(
                f"/entities/review-reject/reject?org_id={ORG_ID}"
            )
            assert reject_again.status_code == 409, reject_again.text

            wrong_type = await client.post(
                f"/entities/review-wrong-type/merge?org_id={ORG_ID}",
                json={"target_id": "review-target"},
            )
            assert wrong_type.status_code == 409, wrong_type.text

            merge = await client.post(
                f"/entities/review-source/merge?org_id={ORG_ID}",
                json={"target_id": "review-target"},
            )
            assert merge.status_code == 200, merge.text
            assert merge.json()["evidence_moved"] == 2

        verification = await GraphClient.run_query(
            """
            MATCH (target:Entity {id: 'review-target', org_id: $org_id})
            OPTIONAL MATCH (target)-[:CITED_BY]->(ev:Evidence)
            OPTIONAL MATCH (source:Entity {id: 'review-source', org_id: $org_id})
            RETURN target.statement AS statement,
                   count(DISTINCT ev) AS evidence,
                   count(DISTINCT source) AS source_count
            """,
            {"org_id": ORG_ID},
        )
        assert verification == [{
            "statement": "Canonical decision",
            "evidence": 3,
            "source_count": 0,
        }], verification
        print("review lifecycle E2E: OK")
    finally:
        await GraphClient.run_query(
            "MATCH (n) WHERE n.org_id = $org_id DETACH DELETE n",
            {"org_id": ORG_ID},
        )
        await GraphClient.close()


if __name__ == "__main__":
    asyncio.run(run())
