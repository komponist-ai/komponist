"""Deliverables shared with a Workroom.

Compose artifacts are private by default. A deliverable becomes shared only
when a link row ties it to the Workroom that produced it, and it is then
readable through that room's authorization rather than through ownership.

Two rules hold throughout:

* An artifact with no link stays private to its creator. Existing
  deliverables are never retroactively exposed.
* Room authorization is still bounded by the organization. A link can never
  cross an organization boundary.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select

from database import (
    GeneratedArtifact,
    User,
    Workroom,
    WorkroomArtifact,
    WorkroomMember,
    async_session,
)
from workrooms import effective_room_role, room_can


def link_dict(link: WorkroomArtifact) -> dict[str, Any]:
    return {
        "id": link.id,
        "workroom_id": link.workroom_id,
        "artifact_id": link.artifact_id,
        "task_id": link.task_id,
        "run_id": link.run_id,
        "status": link.status,
        "created_by_user_id": link.created_by_user_id,
        "approved_by_user_id": link.approved_by_user_id,
        "created_at": f"{link.created_at.isoformat()}Z",
        "updated_at": f"{link.updated_at.isoformat()}Z",
    }


async def share_artifact(
    *,
    org_id: str,
    room_id: str,
    artifact_id: str,
    task_id: Optional[str],
    run_id: Optional[str],
    created_by_user_id: str,
    approved_by_user_id: Optional[str],
) -> dict[str, Any]:
    """Link a deliverable to a room. Idempotent for at-least-once delivery."""
    now = datetime.utcnow()
    async with async_session() as session:
        existing = (
            await session.execute(
                select(WorkroomArtifact).where(
                    WorkroomArtifact.workroom_id == room_id,
                    WorkroomArtifact.artifact_id == artifact_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.status = "shared"
            existing.updated_at = now
            await session.commit()
            return link_dict(existing)

        link = WorkroomArtifact(
            id=str(uuid4()),
            workroom_id=room_id,
            org_id=org_id,
            artifact_id=artifact_id,
            task_id=task_id,
            run_id=run_id,
            status="shared",
            created_by_user_id=created_by_user_id,
            approved_by_user_id=approved_by_user_id,
            created_at=now,
            updated_at=now,
        )
        session.add(link)
        await session.commit()
        return link_dict(link)


async def list_room_artifacts(org_id: str, room_id: str) -> list[dict[str, Any]]:
    """Shared deliverables for one room, with their approval metadata."""
    async with async_session() as session:
        links = (
            await session.execute(
                select(WorkroomArtifact)
                .where(
                    WorkroomArtifact.org_id == org_id,
                    WorkroomArtifact.workroom_id == room_id,
                    WorkroomArtifact.status == "shared",
                )
                .order_by(WorkroomArtifact.created_at.desc())
            )
        ).scalars().all()

        results: list[dict[str, Any]] = []
        for link in links:
            artifact = await session.get(GeneratedArtifact, link.artifact_id)
            if artifact is None or artifact.org_id != org_id:
                continue
            approver = (
                await session.get(User, link.approved_by_user_id)
                if link.approved_by_user_id
                else None
            )
            results.append({
                **link_dict(link),
                "title": artifact.title,
                "artifact_type": artifact.artifact_type,
                "topic": artifact.topic,
                "language": artifact.language,
                "source_count": len(artifact.sources or []),
                "sources": (artifact.sources or [])[:12],
                "approved_by_name": approver.name if approver else None,
                "artifact_created_at": f"{artifact.created_at.isoformat()}Z",
                "artifact_updated_at": f"{artifact.updated_at.isoformat()}Z",
                "compose_path": f"/create?artifact={artifact.id}",
            })
        return results


async def artifact_sharing(org_id: str, artifact_id: str) -> list[dict[str, Any]]:
    """Which rooms currently share this artifact, for the Compose label."""
    async with async_session() as session:
        links = (
            await session.execute(
                select(WorkroomArtifact, Workroom)
                .join(Workroom, Workroom.id == WorkroomArtifact.workroom_id)
                .where(
                    WorkroomArtifact.org_id == org_id,
                    WorkroomArtifact.artifact_id == artifact_id,
                    WorkroomArtifact.status == "shared",
                )
            )
        ).all()
        return [
            {
                "workroom_id": room.id,
                "workroom_title": room.title,
                "task_id": link.task_id,
                "run_id": link.run_id,
                "approved_by_user_id": link.approved_by_user_id,
                "shared_at": f"{link.created_at.isoformat()}Z",
            }
            for link, room in links
        ]


async def resolve_room_access(
    *,
    org_id: str,
    artifact_id: str,
    user: dict,
    permission: str,
) -> Optional[dict[str, Any]]:
    """Grant access to a shared artifact through Workroom authorization.

    Returns the granting room's details, or ``None`` when no room the caller
    can reach shares this artifact with the required permission.
    """
    async with async_session() as session:
        links = (
            await session.execute(
                select(WorkroomArtifact).where(
                    WorkroomArtifact.org_id == org_id,
                    WorkroomArtifact.artifact_id == artifact_id,
                    WorkroomArtifact.status == "shared",
                )
            )
        ).scalars().all()
        if not links:
            return None

        for link in links:
            room = await session.get(Workroom, link.workroom_id)
            # Cross-organization access is impossible by construction.
            if room is None or room.org_id != org_id:
                continue
            membership = (
                await session.execute(
                    select(WorkroomMember).where(
                        WorkroomMember.workroom_id == room.id,
                        WorkroomMember.user_id == user["id"],
                    )
                )
            ).scalar_one_or_none()
            role = effective_room_role(
                room,
                membership,
                department_ids=user.get("department_ids") or [],
                access_all=bool(user.get("access_all_departments")),
                org_role=user.get("role", "member"),
            )
            if role is not None and room_can(role, permission):
                return {
                    "workroom_id": room.id,
                    "workroom_title": room.title,
                    "room_role": role,
                    "task_id": link.task_id,
                    "run_id": link.run_id,
                    "link_id": link.id,
                }
        return None


async def get_org_artifact(org_id: str, artifact_id: str) -> Optional[GeneratedArtifact]:
    """Load an artifact by organization alone. Callers must authorize first."""
    async with async_session() as session:
        artifact = await session.get(GeneratedArtifact, artifact_id)
        if artifact is None or artifact.org_id != org_id:
            return None
        return artifact


async def unshare_artifact(
    org_id: str, room_id: str, artifact_id: str
) -> Optional[dict[str, Any]]:
    """Withdraw a deliverable from a room without destroying it.

    The artifact itself survives and stays with its creator, matching how
    Workrooms archive rather than delete elsewhere.
    """
    async with async_session() as session:
        link = (
            await session.execute(
                select(WorkroomArtifact).where(
                    WorkroomArtifact.org_id == org_id,
                    WorkroomArtifact.workroom_id == room_id,
                    WorkroomArtifact.artifact_id == artifact_id,
                    WorkroomArtifact.status == "shared",
                )
            )
        ).scalar_one_or_none()
        if link is None:
            return None
        link.status = "archived"
        link.updated_at = datetime.utcnow()
        await session.commit()
        return link_dict(link)
