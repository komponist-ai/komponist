"""E2E checks for the knowledge graph explorer's API contract.

The explorer is the one place a reader sees the company graph as a graph, so
what it may draw has to match what the reader is allowed to know. These checks
pin down the filters the toolbar depends on and, more importantly, that neither
another organization's knowledge nor another department's leaks in through the
overview or through neighbour expansion.

Run the whole thing:
    python tests/graph_explorer_e2e.py

Or leave a fixture graph in place for browser work, then remove it:
    python tests/graph_explorer_e2e.py seed [node_count]
    python tests/graph_explorer_e2e.py cleanup
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

import httpx
from sqlalchemy import delete, select

import main
from core.graph import GraphClient
from database import (
    AuthIdentity,
    AuthSession,
    AuthSessionContext,
    Department,
    DepartmentMembership,
    Org,
    OrganizationMembership,
    PasswordCredential,
    User,
    async_session,
    init_db,
)


OWNER_EMAIL = "graph-explorer-owner-e2e@example.com"
LIMITED_EMAIL = "graph-explorer-limited-e2e@example.com"
FOREIGN_EMAIL = "graph-explorer-foreign-e2e@example.com"
PASSWORD = "correct horse battery staple"
EMAILS = [OWNER_EMAIL, LIMITED_EMAIL, FOREIGN_EMAIL]

ENTITY_TYPES = ["Decision", "Goal", "Constraint", "Project"]
RELATIONSHIP_TYPES = ["AFFECTS", "ADVANCES", "CONSTRAINS", "RELATES_TO"]


async def cleanup() -> None:
    async with async_session() as session:
        users = (
            await session.execute(select(User).where(User.email.in_(EMAILS)))
        ).scalars().all()
        user_ids = [user.id for user in users]
        org_ids = list({user.org_id for user in users})

        if org_ids:
            for org_id in org_ids:
                await GraphClient.run_query(
                    "MATCH (node) WHERE node.org_id = $org_id DETACH DELETE node",
                    {"org_id": org_id},
                )
            for table in (DepartmentMembership, Department):
                await session.execute(
                    delete(table).where(table.org_id.in_(org_ids))
                )
        if user_ids:
            session_ids = list((
                await session.execute(
                    select(AuthSession.id).where(AuthSession.user_id.in_(user_ids))
                )
            ).scalars())
            if session_ids:
                await session.execute(
                    delete(AuthSessionContext).where(
                        AuthSessionContext.session_id.in_(session_ids)
                    )
                )
            for table in (
                AuthSession, PasswordCredential, AuthIdentity, OrganizationMembership,
            ):
                await session.execute(
                    delete(table).where(table.user_id.in_(user_ids))
                )
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        if org_ids:
            await session.execute(delete(Org).where(Org.id.in_(org_ids)))
        await session.commit()


async def seed_graph(org_id: str, count: int, *, private_department_id: str) -> None:
    """Create a connected fixture graph of `count` entities.

    Nodes are chained so the graph is genuinely connected rather than a cloud of
    isolated dots, with extra chords every few nodes so degrees actually differ
    and the explorer's size and label ranking has something to rank.
    """
    await GraphClient.run_query(
        """
        UNWIND range(0, $count - 1) AS index
        CREATE (entity:Entity {
            id: 'gx-' + toString(index),
            org_id: $org_id,
            entity_type: $types[index % size($types)],
            statement: 'Fixture entity ' + toString(index)
                       + ' for the knowledge graph explorer',
            detail: 'Detail for fixture entity ' + toString(index),
            // Every fifth entity stays proposed so the renderer has both
            // statuses to tell apart.
            status: CASE WHEN index % 5 = 4 THEN 'proposed' ELSE 'confirmed' END,
            confidence: 'high',
            department_ids: [],
            created_at: datetime(),
            updated_at: datetime()
        })
        CREATE (evidence:Evidence {
            id: 'gx-evidence-' + toString(index),
            org_id: $org_id,
            source: 'upload',
            title: 'Fixture source ' + toString(index),
            reference: 'fixture-' + toString(index) + '.md',
            excerpt: 'Supporting passage for fixture entity ' + toString(index),
            line_start: 1,
            line_end: 2,
            source_date: datetime()
        })
        CREATE (entity)-[:CITED_BY]->(evidence)
        """,
        {"org_id": org_id, "count": count, "types": ENTITY_TYPES},
    )

    await GraphClient.run_query(
        """
        UNWIND range(1, $count - 1) AS index
        MATCH (source:Entity {id: 'gx-' + toString(index - 1), org_id: $org_id})
        MATCH (target:Entity {id: 'gx-' + toString(index), org_id: $org_id})
        CALL apoc.create.relationship(
            source,
            $rels[index % size($rels)],
            {description: 'Fixture link ' + toString(index)},
            target
        ) YIELD rel
        RETURN count(rel)
        """,
        {"org_id": org_id, "count": count, "rels": RELATIONSHIP_TYPES},
    )

    if count > 8:
        await GraphClient.run_query(
            """
            UNWIND range(0, $count - 5) AS index
            WITH index WHERE index % 4 = 0
            MATCH (source:Entity {id: 'gx-' + toString(index), org_id: $org_id})
            MATCH (target:Entity {id: 'gx-' + toString(index + 4), org_id: $org_id})
            CALL apoc.create.relationship(
                source, 'RELATES_TO', {description: 'Fixture chord'}, target
            ) YIELD rel
            RETURN count(rel)
            """,
            {"org_id": org_id, "count": count},
        )

    # One entity only the finance department may see, wired to a public node so
    # neighbour expansion has a chance to leak it if scoping is wrong.
    await GraphClient.run_query(
        """
        MATCH (public:Entity {id: 'gx-0', org_id: $org_id})
        CREATE (secret:Entity {
            id: 'gx-confidential',
            org_id: $org_id,
            entity_type: 'Decision',
            statement: 'Confidential finance decision about the runway',
            detail: 'Only the finance department may read this.',
            status: 'confirmed',
            confidence: 'high',
            department_ids: [$department_id],
            created_at: datetime(),
            updated_at: datetime()
        })
        CREATE (public)-[:AFFECTS {description: 'Confidential link'}]->(secret)
        """,
        {"org_id": org_id, "department_id": private_department_id},
    )


def client(transport: httpx.ASGITransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def build_fixture(node_count: int) -> dict:
    """Create the org, the two members, the department and the graph."""
    transport = httpx.ASGITransport(app=main.app)

    async with client(transport) as owner_c, client(transport) as limited_c:
        owner = (await owner_c.post(
            "/auth/register",
            json={"name": "Graph Owner", "email": OWNER_EMAIL, "password": PASSWORD},
        )).json()["user"]
        limited = (await limited_c.post(
            "/auth/register",
            json={"name": "Graph Limited", "email": LIMITED_EMAIL, "password": PASSWORD},
        )).json()["user"]
        org_id = owner["org_id"]

        async with async_session() as session:
            session.add(OrganizationMembership(
                id=str(uuid4()),
                user_id=limited["id"],
                org_id=org_id,
                role="member",
                status="active",
            ))
            await session.commit()

        created = await owner_c.post(
            f"/auth/organizations/{org_id}/departments",
            json={"name": "Finance"},
        )
        assert created.status_code == 201, created.text
        department = created.json()

        await seed_graph(org_id, node_count, private_department_id=department["id"])

    return {"org_id": org_id, "department_id": department["id"]}


async def seed(node_count: int) -> None:
    GraphClient.initialize()
    await init_db()
    await cleanup()
    try:
        fixture = await build_fixture(node_count)
    finally:
        await GraphClient.close()
    print("Fixture graph ready.")
    print(f"  org_id:   {fixture['org_id']}")
    print(f"  email:    {OWNER_EMAIL}")
    print(f"  password: {PASSWORD}")
    print(f"  entities: {node_count} plus one department-restricted entity")


async def run() -> None:
    previous_mode = os.environ.get("KOMPONIST_AI_MODE")
    os.environ["KOMPONIST_AI_MODE"] = "mock"
    GraphClient.initialize()
    await init_db()
    await cleanup()
    transport = httpx.ASGITransport(app=main.app)

    try:
        fixture = await build_fixture(24)
        org_id = fixture["org_id"]

        async with client(transport) as owner_c, \
                client(transport) as limited_c, \
                client(transport) as foreign_c:
            await owner_c.post(
                "/auth/login/email", json={"email": OWNER_EMAIL, "password": PASSWORD}
            )
            await limited_c.post(
                "/auth/login/email", json={"email": LIMITED_EMAIL, "password": PASSWORD}
            )
            foreign = (await foreign_c.post(
                "/auth/register",
                json={
                    "name": "Graph Foreign",
                    "email": FOREIGN_EMAIL,
                    "password": PASSWORD,
                },
            )).json()["user"]

            # --- The overview the toolbar depends on ----------------------
            overview = await owner_c.get(
                "/graph", params={"org_id": org_id, "limit": 400}
            )
            assert overview.status_code == 200, overview.text
            payload = overview.json()
            node_ids = {node["id"] for node in payload["nodes"]}
            assert len(node_ids) == len(payload["nodes"]), "overview repeated a node"
            assert all(node["name"] for node in payload["nodes"]), \
                "an overview node arrived without a name"
            # Every relationship must land between nodes that are on screen,
            # or the renderer would be asked to draw a dangling endpoint.
            for edge in payload["edges"]:
                assert edge["source"] in node_ids and edge["target"] in node_ids, edge
            print("✓ the overview returns named nodes and connectable edges")

            # --- Filters ---------------------------------------------------
            decisions = (await owner_c.get(
                "/graph", params={"org_id": org_id, "entity_types": "Decision"}
            )).json()
            assert decisions["nodes"], "the type filter removed everything"
            assert {node["type"] for node in decisions["nodes"]} == {"Decision"}

            proposed = (await owner_c.get(
                "/graph", params={"org_id": org_id, "status": "proposed"}
            )).json()
            assert proposed["nodes"], "the status filter removed everything"
            assert {node["status"] for node in proposed["nodes"]} == {"proposed"}

            rejected = await owner_c.get(
                "/graph", params={"org_id": org_id, "status": "rejected"}
            )
            assert rejected.status_code == 400, rejected.text

            searched = (await owner_c.get(
                "/graph", params={"org_id": org_id, "query": "fixture entity 7"}
            )).json()
            assert searched["nodes"], "search found nothing it seeded"
            assert all(
                "fixture entity 7" in node["name"].lower()
                or "fixture entity 7" in (node["description"] or "").lower()
                for node in searched["nodes"]
            ), searched["nodes"]
            print("✓ type, status and search filters narrow the graph")

            # --- Truncation is announced, not silent ----------------------
            small = (await owner_c.get(
                "/graph", params={"org_id": org_id, "limit": 5}
            )).json()
            assert len(small["nodes"]) == 5, small["nodes"]
            assert small["truncated"] is True, small
            assert small["total"] > 5, small
            print("✓ a truncated graph says so and reports the real total")

            # --- Neighbour expansion --------------------------------------
            neighbors = await owner_c.get(
                "/graph/neighbors/gx-3", params={"org_id": org_id, "depth": 1}
            )
            assert neighbors.status_code == 200, neighbors.text
            hood = neighbors.json()
            assert hood["center"] == "gx-3"
            hood_ids = [node["id"] for node in hood["nodes"]]
            assert len(hood_ids) == len(set(hood_ids)), "expansion repeated a node"
            assert "gx-3" in hood_ids, hood_ids
            assert all(node["name"] for node in hood["nodes"]), \
                "expansion returned an unnamed node"
            # The explorer merges these into the overview, so the shape has to
            # match or a node would change appearance depending on how it was
            # reached.
            for node in hood["nodes"]:
                assert set(node) >= {
                    "id", "name", "type", "description",
                    "status", "confidence", "degree", "evidence_count",
                }, node
            assert any(node["evidence_count"] for node in hood["nodes"]), hood["nodes"]

            deeper = (await owner_c.get(
                "/graph/neighbors/gx-3", params={"org_id": org_id, "depth": 2}
            )).json()
            assert len(deeper["nodes"]) > len(hood["nodes"]), (deeper, hood)
            print("✓ neighbour expansion returns the same node shape at both depths")

            # --- Department isolation -------------------------------------
            # The confidential entity hangs off gx-0, which everyone can see.
            owner_overview = (await owner_c.get(
                "/graph", params={"org_id": org_id, "limit": 400}
            )).json()
            assert "gx-confidential" in {n["id"] for n in owner_overview["nodes"]}, \
                "the org owner should see department knowledge"

            limited_overview = (await limited_c.get(
                "/graph", params={"org_id": org_id, "limit": 400}
            )).json()
            limited_ids = {node["id"] for node in limited_overview["nodes"]}
            assert "gx-confidential" not in limited_ids, \
                "a member outside Finance saw a Finance-only entity"
            assert "gx-0" in limited_ids, "unrelated knowledge was hidden too"

            # Expanding the public neighbour must not reveal it either.
            limited_hood = (await limited_c.get(
                "/graph/neighbors/gx-0", params={"org_id": org_id, "depth": 1}
            )).json()
            leaked = {node["id"] for node in limited_hood["nodes"]}
            assert "gx-confidential" not in leaked, \
                "expansion leaked a department-restricted entity"
            for edge in limited_hood["edges"]:
                assert "gx-confidential" not in (edge["source"], edge["target"]), edge
            print("✓ department-restricted knowledge stays out of both views")

            # --- Organization isolation -----------------------------------
            foreign_graph = await foreign_c.get("/graph", params={"org_id": org_id})
            assert foreign_graph.status_code in (401, 403), foreign_graph.text
            foreign_hood = await foreign_c.get(
                "/graph/neighbors/gx-3", params={"org_id": org_id}
            )
            assert foreign_hood.status_code in (401, 403), foreign_hood.text

            own_graph = (await foreign_c.get(
                "/graph", params={"org_id": foreign["org_id"]}
            )).json()
            assert own_graph["nodes"] == [], own_graph

            anonymous = await httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ).get("/graph", params={"org_id": org_id})
            assert anonymous.status_code == 401, anonymous.text
            print("✓ the graph is organization-isolated and needs a session")
    finally:
        await cleanup()
        await GraphClient.close()
        if previous_mode is None:
            os.environ.pop("KOMPONIST_AI_MODE", None)
        else:
            os.environ["KOMPONIST_AI_MODE"] = previous_mode


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "seed":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 40
        asyncio.run(seed(count))
    elif mode == "cleanup":
        GraphClient.initialize()
        asyncio.run(cleanup())
        asyncio.run(GraphClient.close())
        print("Fixture graph removed.")
    else:
        asyncio.run(run())
        print("Graph explorer E2E: OK")
