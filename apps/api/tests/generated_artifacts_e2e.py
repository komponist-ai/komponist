"""E2E checks for permission-aware generated deliverables and exports."""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

import httpx
from sqlalchemy import delete, select

import auth
import main
from artifacts import sanitize_artifact_content
from core.graph import GraphClient
from database import (
    AuthIdentity,
    AuthSession,
    AuthSessionContext,
    GeneratedArtifact,
    Org,
    OrganizationMembership,
    PasswordCredential,
    User,
    async_session,
    init_db,
)


OWNER_EMAIL = "artifacts-owner-e2e@example.com"
MEMBER_EMAIL = "artifacts-member-e2e@example.com"
PASSWORD = "correct horse battery staple"


async def cleanup() -> None:
    async with async_session() as session:
        users = (
            await session.execute(
                select(User).where(User.email.in_([OWNER_EMAIL, MEMBER_EMAIL]))
            )
        ).scalars().all()
        user_ids = [user.id for user in users]
        org_ids = list({user.org_id for user in users})
        if org_ids:
            for org_id in org_ids:
                await GraphClient.run_query(
                    "MATCH (node) WHERE node.org_id = $org_id DETACH DELETE node",
                    {"org_id": org_id},
                )
        if user_ids:
            await session.execute(
                delete(GeneratedArtifact).where(GeneratedArtifact.user_id.in_(user_ids))
            )
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
            await session.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
            await session.execute(delete(PasswordCredential).where(PasswordCredential.user_id.in_(user_ids)))
            await session.execute(delete(AuthIdentity).where(AuthIdentity.user_id.in_(user_ids)))
            await session.execute(delete(OrganizationMembership).where(OrganizationMembership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        if org_ids:
            await session.execute(delete(Org).where(Org.id.in_(org_ids)))
        await session.commit()


async def run() -> None:
    previous_mode = os.environ.get("KOMPONIST_AI_MODE")
    os.environ["KOMPONIST_AI_MODE"] = "mock"
    GraphClient.initialize()
    await init_db()
    await cleanup()
    transport = httpx.ASGITransport(app=main.app)

    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as owner_client, httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as member_client:
            owner_response = await owner_client.post(
                "/auth/register",
                json={"name": "Artifact Owner", "email": OWNER_EMAIL, "password": PASSWORD},
            )
            assert owner_response.status_code == 201, owner_response.text
            owner = owner_response.json()["user"]

            member_response = await member_client.post(
                "/auth/register",
                json={"name": "Artifact Member", "email": MEMBER_EMAIL, "password": PASSWORD},
            )
            assert member_response.status_code == 201, member_response.text
            member = member_response.json()["user"]

            async with async_session() as session:
                session.add(OrganizationMembership(
                    id=str(uuid4()),
                    user_id=member["id"],
                    org_id=owner["org_id"],
                    role="member",
                    status="active",
                ))
                await session.commit()

            await GraphClient.run_query(
                """
                CREATE (decision:Entity {
                    id: 'artifact-decision', org_id: $org_id,
                    entity_type: 'Decision', statement: 'Launch the Northstar pilot in September.',
                    detail: 'The reviewed launch decision applies to the pilot team.',
                    status: 'confirmed', confidence: 'high', department_ids: [],
                    created_at: datetime(), confirmed_at: datetime()
                })
                CREATE (goal:Entity {
                    id: 'artifact-goal', org_id: $org_id,
                    entity_type: 'Goal', statement: 'The Northstar pilot runs for 4 weeks.',
                    status: 'confirmed', confidence: 'high', department_ids: [],
                    created_at: datetime(), confirmed_at: datetime()
                })
                CREATE (hidden:Entity {
                    id: 'artifact-hidden', org_id: $org_id,
                    entity_type: 'Constraint', statement: 'Confidential board budget is 900000 euros.',
                    status: 'confirmed', confidence: 'high', department_ids: ['board'],
                    created_at: datetime(), confirmed_at: datetime()
                })
                CREATE (proposed:Entity {
                    id: 'artifact-proposed', org_id: $org_id,
                    entity_type: 'Goal', statement: 'Unreviewed target must never be generated.',
                    status: 'proposed', confidence: 'low', department_ids: [],
                    created_at: datetime()
                })
                CREATE (e1:Evidence {
                    id: 'artifact-evidence-1', org_id: $org_id, source: 'upload',
                    title: 'Northstar plan', reference: 'northstar-plan.md',
                    url: 'upload://northstar-plan.md', excerpt: 'Launch in September.',
                    line_start: 12, line_end: 12,
                    source_date: datetime()
                })
                CREATE (e2:Evidence {
                    id: 'artifact-evidence-2', org_id: $org_id, source: 'upload',
                    title: 'Northstar plan', reference: 'northstar-plan.md',
                    url: 'upload://northstar-plan.md',
                    excerpt: 'The pilot lasts four weeks.',
                    line_start: 18, line_end: 18,
                    source_date: datetime()
                })
                CREATE (e3:Evidence {
                    id: 'artifact-evidence-hidden', org_id: $org_id, source: 'upload',
                    reference: 'board-budget.md', excerpt: 'Confidential budget.',
                    department_id: 'board', source_date: datetime()
                })
                CREATE (e4:Evidence {
                    id: 'artifact-evidence-proposed', org_id: $org_id, source: 'upload',
                    reference: 'draft.md', excerpt: 'Unreviewed target.', source_date: datetime()
                })
                CREATE (decision)-[:CITED_BY]->(e1)
                CREATE (goal)-[:CITED_BY]->(e2)
                CREATE (hidden)-[:CITED_BY]->(e3)
                CREATE (proposed)-[:CITED_BY]->(e4)
                CREATE (decision)-[:ADVANCES]->(goal)
                """,
                {"org_id": owner["org_id"]},
            )

            unauthenticated = await httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ).get("/artifacts", params={"org_id": owner["org_id"]})
            assert unauthenticated.status_code == 401, unauthenticated.text

            owner_deck = await owner_client.post(
                "/artifacts/generate",
                params={"org_id": owner["org_id"]},
                json={
                    "artifact_type": "presentation",
                    "topic": "Company overview",
                    "audience": "Client stakeholders",
                    "language": "english",
                    "instructions": "Keep it concise",
                },
            )
            assert owner_deck.status_code == 201, owner_deck.text
            owner_payload = owner_deck.json()
            assert owner_payload["content"]["blocks"], owner_payload
            assert owner_payload["sources"], owner_payload
            assert owner_payload["sources"][0]["komponist_path"].startswith(
                f"/sources?org_id={owner['org_id']}&evidence="
            ), owner_payload["sources"][0]
            assert "artifact-proposed" not in owner_payload["source_entity_ids"]

            member_list = await member_client.get(
                "/artifacts", params={"org_id": owner["org_id"]}
            )
            assert member_list.status_code == 200, member_list.text
            assert member_list.json()["artifacts"] == [], member_list.text

            member_deck = await member_client.post(
                "/artifacts/generate",
                params={"org_id": owner["org_id"]},
                json={
                    "artifact_type": "presentation",
                    "topic": "Northstar pilot",
                    "audience": "Project team",
                    "language": "english",
                },
            )
            assert member_deck.status_code == 201, member_deck.text
            member_payload = member_deck.json()
            assert set(member_payload["source_entity_ids"]) == {
                "artifact-decision", "artifact-goal"
            }, member_payload
            assert all(
                block.get("layout") and block.get("eyebrow")
                and block.get("takeaway")
                for block in member_payload["content"]["blocks"]
            ), member_payload["content"]["blocks"]
            serialized_member = str(member_payload)
            assert "900000" not in serialized_member
            assert "Unreviewed target" not in serialized_member
            allowed_ids = set(member_payload["source_entity_ids"])
            for block in member_payload["content"]["blocks"]:
                assert block["source_ids"], block
                assert set(block["source_ids"]).issubset(allowed_ids), block

            leaked_id = "artifact-decision"
            leaky_candidate = {
                "title": "Pilot briefing",
                "subtitle": "Reviewed context",
                "executive_summary": f"Launch in September [{leaked_id}].",
                "source_ids": [leaked_id],
                "blocks": [{
                    "title": "Timing",
                    "body": f"The decision is recorded ({leaked_id}).",
                    "bullets": [f"Launch in September {leaked_id}."],
                    "speaker_notes": "",
                    "source_ids": [leaked_id],
                }],
            }
            cleaned = sanitize_artifact_content(
                leaky_candidate,
                member_payload["content"],
                [{"id": leaked_id, "evidence": [{"id": "artifact-evidence-1"}]}],
            )
            reader_text = " ".join([
                cleaned["title"],
                cleaned["subtitle"],
                cleaned["executive_summary"],
                *[
                    " ".join([
                        block["title"], block["body"],
                        *block["bullets"], block["speaker_notes"],
                    ])
                    for block in cleaned["blocks"]
                ],
            ])
            assert leaked_id not in reader_text, cleaned

            deck_download = await member_client.get(
                f"/artifacts/{member_payload['id']}/download",
                params={"org_id": owner["org_id"]},
            )
            assert deck_download.status_code == 200, deck_download.text
            assert deck_download.content[:2] == b"PK"
            assert deck_download.headers["content-type"].startswith(
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            )
            deck_pdf = await member_client.get(
                f"/artifacts/{member_payload['id']}/download",
                params={"org_id": owner["org_id"], "format": "pdf"},
            )
            assert deck_pdf.status_code == 200, deck_pdf.text
            assert deck_pdf.content[:4] == b"%PDF"
            assert deck_pdf.headers["content-type"].startswith("application/pdf")

            deck_markdown = await member_client.get(
                f"/artifacts/{member_payload['id']}/download",
                params={"org_id": owner["org_id"], "format": "markdown"},
            )
            assert deck_markdown.status_code == 200, deck_markdown.text
            assert "## Sources" in deck_markdown.text
            assert "http://localhost:3000/sources?org_id=" in deck_markdown.text
            assert "line 12" in deck_markdown.text

            cited_passage = await member_client.get(
                "/evidence/artifact-evidence-1",
                params={"org_id": owner["org_id"]},
            )
            assert cited_passage.status_code == 200, cited_passage.text
            cited_payload = cited_passage.json()
            assert cited_payload["excerpt"] == "Launch in September.", cited_payload
            assert cited_payload["location"] == {
                "kind": "lines",
                "label": "Line 12",
                "line_start": 12,
                "line_end": 12,
            }, cited_payload

            briefing = await member_client.post(
                "/artifacts/generate",
                params={"org_id": owner["org_id"]},
                json={
                    "artifact_type": "briefing",
                    "topic": "Northstar pilot",
                    "audience": "Leadership team",
                    "language": "english",
                },
            )
            assert briefing.status_code == 201, briefing.text
            briefing_payload = briefing.json()
            markdown = await member_client.get(
                f"/artifacts/{briefing_payload['id']}/download",
                params={"org_id": owner["org_id"], "format": "markdown"},
            )
            assert markdown.status_code == 200, markdown.text
            assert markdown.headers["content-type"].startswith("text/markdown")
            assert "## Sources" in markdown.text
            assert "northstar-plan.md" in markdown.text

            briefing_pdf = await member_client.get(
                f"/artifacts/{briefing_payload['id']}/download",
                params={"org_id": owner["org_id"], "format": "pdf"},
            )
            assert briefing_pdf.status_code == 200, briefing_pdf.text
            assert briefing_pdf.content[:4] == b"%PDF"

            invalid_pptx = await member_client.get(
                f"/artifacts/{briefing_payload['id']}/download",
                params={"org_id": owner["org_id"], "format": "pptx"},
            )
            assert invalid_pptx.status_code == 400, invalid_pptx.text

            deleted = await member_client.delete(
                f"/artifacts/{briefing_payload['id']}",
                params={"org_id": owner["org_id"]},
            )
            assert deleted.status_code == 204, deleted.text

        print("Generated artifacts E2E: OK")
    finally:
        await cleanup()
        await GraphClient.close()
        if previous_mode is None:
            os.environ.pop("KOMPONIST_AI_MODE", None)
        else:
            os.environ["KOMPONIST_AI_MODE"] = previous_mode


if __name__ == "__main__":
    asyncio.run(run())
