"""E2E checks for rendering a Canvas from a hand-written specification.

No model is involved. This proves the renderer, the query catalog, the
citations and the permission scope work end to end, so generation later only
has to produce a spec — if it regresses, the feature still functions.
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
    Canvas,
    CanvasVersion,
    Department,
    DepartmentMembership,
    Org,
    OrganizationMembership,
    PasswordCredential,
    User,
    async_session,
    init_db,
)


OWNER_EMAIL = "canvas-owner-e2e@example.com"
LIMITED_EMAIL = "canvas-limited-e2e@example.com"
FOREIGN_EMAIL = "canvas-foreign-e2e@example.com"
PASSWORD = "correct horse battery staple"
EMAILS = [OWNER_EMAIL, LIMITED_EMAIL, FOREIGN_EMAIL]

RUN_TAG = uuid4().hex[:8]
SECRET_AMOUNT = f"7700{RUN_TAG[:2]}"


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
            for table in (CanvasVersion, Canvas, DepartmentMembership, Department):
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


async def seed_graph(org_id: str, board_department_id: str) -> None:
    await GraphClient.run_query(
        """
        CREATE (project:Entity:Project {
            id: 'cv-project', org_id: $org_id, entity_type: 'Project',
            statement: 'Northstar pilot programme.',
            status: 'confirmed', confidence: 'high', department_ids: [],
            created_at: datetime(), confirmed_at: datetime(), updated_at: datetime()
        })
        CREATE (unrelated:Entity:Decision {
            id: 'cv-unrelated', org_id: $org_id, entity_type: 'Decision',
            statement: 'Move the office coffee machine to the second floor.',
            status: 'confirmed', confidence: 'high', department_ids: [],
            created_at: datetime(), confirmed_at: datetime(), updated_at: datetime()
        })
        CREATE (e6:Evidence {
            id: 'cv-evidence-unrelated', org_id: $org_id, source: 'upload',
            title: 'Office notes', reference: 'office-notes.md',
            excerpt: 'Coffee machine moves upstairs.', line_start: 3, line_end: 3,
            source_date: datetime()
        })
        CREATE (decision:Entity:Decision {
            id: 'cv-decision', org_id: $org_id, entity_type: 'Decision',
            statement: 'Launch the Northstar pilot in September.',
            detail: 'Confirmed with the pilot team.',
            status: 'confirmed', confidence: 'high', department_ids: [],
            created_at: datetime(), confirmed_at: datetime(), updated_at: datetime()
        })
        CREATE (goal:Entity {
            id: 'cv-goal', org_id: $org_id, entity_type: 'Goal',
            statement: 'The Northstar pilot runs for four weeks.',
            status: 'confirmed', confidence: 'high', department_ids: [],
            created_at: datetime(), confirmed_at: datetime(), updated_at: datetime()
        })
        CREATE (constraint:Entity {
            id: 'cv-constraint', org_id: $org_id, entity_type: 'Constraint',
            statement: 'Every extracted fact needs human review.',
            status: 'confirmed', confidence: 'medium', department_ids: [],
            created_at: datetime(), confirmed_at: datetime(), updated_at: datetime()
        })
        CREATE (proposed:Entity {
            id: 'cv-proposed', org_id: $org_id, entity_type: 'Decision',
            statement: 'Unreviewed claim that must never appear.',
            status: 'proposed', confidence: 'low', department_ids: [],
            created_at: datetime(), updated_at: datetime()
        })
        CREATE (secret:Entity {
            id: 'cv-secret', org_id: $org_id, entity_type: 'Constraint',
            statement: 'The confidential board budget is ' + $secret + ' euros.',
            status: 'confirmed', confidence: 'high',
            department_ids: [$board],
            created_at: datetime(), confirmed_at: datetime(), updated_at: datetime()
        })
        CREATE (e1:Evidence {
            id: 'cv-evidence-decision', org_id: $org_id, source: 'upload',
            title: 'Northstar plan', reference: 'northstar-plan.md',
            excerpt: 'Launch in September.', line_start: 12, line_end: 12,
            source_date: datetime()
        })
        CREATE (e2:Evidence {
            id: 'cv-evidence-goal', org_id: $org_id, source: 'upload',
            title: 'Northstar plan', reference: 'northstar-plan.md',
            excerpt: 'The pilot lasts four weeks.', line_start: 18, line_end: 18,
            source_date: datetime()
        })
        CREATE (e3:Evidence {
            id: 'cv-evidence-constraint', org_id: $org_id, source: 'upload',
            title: 'Review policy', reference: 'review-policy.md',
            excerpt: 'Extracted knowledge must be reviewed.',
            line_start: 4, line_end: 4, source_date: datetime()
        })
        CREATE (e4:Evidence {
            id: 'cv-evidence-secret', org_id: $org_id, source: 'upload',
            title: 'Confidential board budget', reference: 'board-budget.md',
            excerpt: 'Confidential budget.', department_id: $board,
            source_date: datetime()
        })
        CREATE (e5:Evidence {
            id: 'cv-evidence-proposed', org_id: $org_id, source: 'upload',
            title: 'Draft notes', reference: 'draft-notes.md',
            excerpt: 'Unreviewed note.', line_start: 1, line_end: 1,
            source_date: datetime()
        })
        CREATE (decision)-[:CITED_BY]->(e1)
        CREATE (goal)-[:CITED_BY]->(e2)
        CREATE (constraint)-[:CITED_BY]->(e3)
        CREATE (secret)-[:CITED_BY]->(e4)
        CREATE (proposed)-[:CITED_BY]->(e5)
        CREATE (unrelated)-[:CITED_BY]->(e6)
        CREATE (decision)-[:ADVANCES]->(goal)
        CREATE (decision)-[:RELATES_TO]->(project)
        """,
        {"org_id": org_id, "board": board_department_id, "secret": SECRET_AMOUNT},
    )


async def run() -> None:
    previous_mode = os.environ.get("KOMPONIST_AI_MODE")
    os.environ["KOMPONIST_AI_MODE"] = "mock"
    GraphClient.initialize()
    await init_db()
    await cleanup()
    transport = httpx.ASGITransport(app=main.app)

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, base_url="http://testserver")

    try:
        async with client() as owner_c, client() as limited_c, client() as foreign_c:
            owner = (await owner_c.post(
                "/auth/register",
                json={"name": "Canvas Owner", "email": OWNER_EMAIL, "password": PASSWORD},
            )).json()["user"]
            limited = (await limited_c.post(
                "/auth/register",
                json={"name": "Canvas Limited", "email": LIMITED_EMAIL, "password": PASSWORD},
            )).json()["user"]
            await foreign_c.post(
                "/auth/register",
                json={"name": "Other Org", "email": FOREIGN_EMAIL, "password": PASSWORD},
            )
            org_id = owner["org_id"]

            async with async_session() as session:
                board = Department(
                    id=str(uuid4()), org_id=org_id,
                    name=f"Board {RUN_TAG}", description="Restricted",
                )
                session.add(board)
                session.add(OrganizationMembership(
                    id=str(uuid4()), user_id=limited["id"], org_id=org_id,
                    role="member", status="active",
                ))
                await session.commit()
                board_id = board.id

            await seed_graph(org_id, board_id)

            # --- The example renders without a model ----------------------
            listing = await owner_c.get("/canvases", params={"org_id": org_id})
            assert listing.status_code == 200, listing.text
            assert listing.json()["canvases"] == [], listing.json()
            assert any(
                item["key"] == "northstar-command-center"
                for item in listing.json()["examples"]
            ), listing.json()["examples"]

            created = await owner_c.post(
                "/canvases/examples",
                params={"org_id": org_id},
                json={"example": "northstar-command-center", "visibility": "private"},
            )
            assert created.status_code == 201, created.text
            canvas_id = created.json()["id"]
            assert created.json()["current_version"] == 1
            print("✓ the built-in example creates a canvas with no model involved")

            rendered = await owner_c.get(
                f"/canvases/{canvas_id}", params={"org_id": org_id}
            )
            assert rendered.status_code == 200, rendered.text
            body = rendered.json()
            components = body["data"]["components"]
            assert len(components) == len(body["spec"]["components"]), components

            # --- Bindings return real graph data --------------------------
            decisions = components["confirmed-decisions"]
            assert decisions["value"] == 2, decisions
            mix = components["knowledge-mix"]
            labels = {row["label"] for row in mix["rows"]}
            assert "Decision" in labels and "Goal" in labels, mix
            log = components["decision-log"]
            assert any("September" in row["statement"] for row in log["rows"]), log
            relationships = components["how-things-connect"]
            assert any(
                row["relation"].lower().startswith("advances")
                for row in relationships["rows"]
            ), relationships
            timeline = components["milestones"]
            assert timeline["rows"], timeline
            print("✓ bindings return real, confirmed graph data")

            # --- Unreviewed knowledge never appears -----------------------
            serialized = str(body)
            assert "cv-proposed" not in serialized, "an unconfirmed entity leaked"
            assert "Unreviewed claim" not in serialized, "an unconfirmed claim leaked"
            assert "cv-evidence-proposed" not in serialized, "unreviewed evidence leaked"
            print("✓ unconfirmed knowledge never reaches a canvas")

            # --- Every fact carries a citation with a deep link -----------
            passages = components["supporting-evidence"]
            assert passages["rows"], passages
            assert body["data"]["sources"], body["data"]
            for source in body["data"]["sources"]:
                assert source["id"], source
                assert source["excerpt"], source
                assert source["komponist_path"].startswith("/"), source
                # Citations point into Komponist, never outward.
                assert "://" not in source["komponist_path"], source
            cited = {source["id"] for source in body["data"]["sources"]}
            assert "cv-evidence-decision" in cited, cited

            # Not "sources exist somewhere" but "every row that asserts
            # something carries its own evidence, and that evidence is
            # actually offered to the reader".
            factual_queries = {
                "entity_list", "entity_fact", "timeline_events",
                "relationship_list", "aggregate_by_type",
                "aggregate_by_confidence", "evidence_list", "source_passages",
            }
            checked = 0
            for component in body["spec"]["components"]:
                payload = components[component["id"]]
                if payload["kind"] not in factual_queries:
                    continue
                available = {source["id"] for source in payload["sources"]}
                for row in payload["rows"]:
                    assert row.get("source_ids"), (
                        f"{component['id']} returned an uncited row: {row}"
                    )
                    assert set(row["source_ids"]) <= available, (
                        f"{component['id']} cites evidence it does not offer: {row}"
                    )
                    checked += 1
            assert checked > 0, "no factual rows were checked"

            # A count is a factual claim too, so it carries its evidence.
            assert components["confirmed-decisions"]["sources"], (
                components["confirmed-decisions"]
            )
            print(f"✓ all {checked} factual rows carry evidence the reader can open")

            # --- Each render honours the viewer's own department scope ----
            # The organization owner has access to every department, so the
            # board fact legitimately appears for them. Asserting this makes
            # the negative case below meaningful rather than vacuous: the data
            # really is reachable, and only the scope keeps it out.
            scope = body["data"]["permission_scope"]
            assert scope["confirmed_only"] is True, scope
            assert scope["access_all_departments"] is True, scope
            assert SECRET_AMOUNT in serialized, (
                "the owner has full department access and should see the board fact"
            )
            print("✓ a viewer with full access sees department knowledge")

            # --- A second viewer renders under their own permissions ------
            shared = await owner_c.patch(
                f"/canvases/{canvas_id}",
                params={"org_id": org_id},
                json={"visibility": "organization"},
            )
            assert shared.status_code == 200, shared.text

            limited_view = await limited_c.get(
                f"/canvases/{canvas_id}", params={"org_id": org_id}
            )
            assert limited_view.status_code == 200, limited_view.text
            limited_json = limited_view.json()
            limited_body = str(limited_json)
            # The same view, resolved against a narrower scope: the board fact
            # and its source are both gone.
            assert SECRET_AMOUNT not in limited_body, (
                f"a confidential fact leaked to a limited viewer: {limited_body[:400]}"
            )
            assert "board-budget" not in limited_body, "a confidential source leaked"
            assert limited_json["data"]["permission_scope"]["access_all_departments"] is False
            # The specification is shared; the data is not.
            assert limited_json["spec"] == body["spec"], "the spec should be shared"
            print("✓ a shared canvas resolves per viewer, not as a stored snapshot")

            # --- Aggregates are computed after scoping --------------------
            # Six confirmed facts exist, but one has no evidence and is
            # therefore never shown or counted; the limited viewer may
            # read four of the remaining five.
            # A differing count is exactly the point: the aggregate is computed
            # after the scope predicate, so it cannot betray what it excludes.
            owner_total = components["knowledge-mix"]["value"]
            limited_total = limited_json["data"]["components"]["knowledge-mix"]["value"]
            assert owner_total == 5, owner_total
            assert limited_total == 4, limited_total
            constraints = limited_json["data"]["components"]["open-constraints"]
            assert constraints["rows"], constraints
            assert all(
                SECRET_AMOUNT not in row["statement"] for row in constraints["rows"]
            ), constraints
            print("✓ aggregate counts are scoped and cannot reveal excluded knowledge")

            # --- A project-scoped view excludes unrelated knowledge -------
            scoped = await owner_c.post(
                "/canvases/examples",
                params={"org_id": org_id},
                json={"example": "northstar-command-center", "visibility": "private"},
            )
            assert scoped.status_code == 201, scoped.text
            scoped_id = scoped.json()["id"]

            # Rewrite the stored spec to scope every binding to the project,
            # exercising the same path a generated project dashboard takes.
            async with async_session() as session:
                version = (
                    await session.execute(
                        select(CanvasVersion).where(
                            CanvasVersion.canvas_id == scoped_id
                        )
                    )
                ).scalars().first()
                spec_payload = dict(version.spec)
                spec_payload["components"] = [
                    {
                        **component,
                        "binding": {**component["binding"], "project": "Northstar"},
                    }
                    for component in spec_payload["components"]
                ]
                version.spec = spec_payload
                await session.commit()

            project_view = await owner_c.get(
                f"/canvases/{scoped_id}", params={"org_id": org_id}
            )
            assert project_view.status_code == 200, project_view.text
            project_body = str(project_view.json()["data"])
            assert "Northstar" in project_body, "the project's own knowledge is missing"
            assert "coffee machine" not in project_body.lower(), (
                "a project-scoped view leaked unrelated company knowledge"
            )
            assert "cv-unrelated" not in project_body, project_body[:300]
            # And the unscoped view does show it, so the exclusion is real.
            assert "coffee machine" in str(body["data"]).lower(), (
                "the unscoped view should contain the unrelated decision"
            )
            print("✓ a project-scoped view excludes unrelated company knowledge")

            # --- Only the creator may change it ---------------------------
            refused = await limited_c.patch(
                f"/canvases/{canvas_id}",
                params={"org_id": org_id},
                json={"title": "Not mine"},
            )
            assert refused.status_code == 403, refused.text

            # --- Cross-organization access is impossible ------------------
            foreign = await foreign_c.get(
                f"/canvases/{canvas_id}", params={"org_id": org_id}
            )
            assert foreign.status_code in (401, 403), foreign.text

            unauthenticated = await client().get(
                f"/canvases/{canvas_id}", params={"org_id": org_id}
            )
            assert unauthenticated.status_code == 401, unauthenticated.text
            print("✓ canvases are organization-isolated and creator-owned")

            # --- A private canvas is not disclosed ------------------------
            private = await owner_c.patch(
                f"/canvases/{canvas_id}",
                params={"org_id": org_id},
                json={"visibility": "private"},
            )
            assert private.status_code == 200, private.text
            hidden = await limited_c.get(
                f"/canvases/{canvas_id}", params={"org_id": org_id}
            )
            assert hidden.status_code == 404, hidden.text
            hidden_list = await limited_c.get("/canvases", params={"org_id": org_id})
            assert all(
                item["id"] != canvas_id for item in hidden_list.json()["canvases"]
            ), hidden_list.json()
            print("✓ a private canvas is invisible rather than forbidden")

            # --- A tampered stored spec cannot be rendered ----------------
            async with async_session() as session:
                version = (
                    await session.execute(
                        select(CanvasVersion).where(
                            CanvasVersion.canvas_id == canvas_id
                        )
                    )
                ).scalars().first()
                spec = dict(version.spec)
                spec["components"] = [
                    {**spec["components"][0], "type": "script_runner"}
                ]
                version.spec = spec
                await session.commit()

            tampered = await owner_c.get(
                f"/canvases/{canvas_id}", params={"org_id": org_id}
            )
            assert tampered.status_code == 422, tampered.text
            assert "no longer valid" in tampered.json()["detail"], tampered.json()
            print("✓ a spec tampered with in the database is refused at render time")
    finally:
        await cleanup()
        await GraphClient.close()
        if previous_mode is None:
            os.environ.pop("KOMPONIST_AI_MODE", None)
        else:
            os.environ["KOMPONIST_AI_MODE"] = previous_mode


if __name__ == "__main__":
    asyncio.run(run())
    print("Canvas render E2E: OK")
