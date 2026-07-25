"""Persistence and authorization for saved Canvases.

Visibility reuses the Workroom vocabulary — organization, departments,
private — so there is one mental model for "who can see this" across the
product, and one place where that decision is wrong if it is wrong.

A Canvas stores a question, not an answer. Sharing one never shares data:
every render re-resolves the bindings against the viewer's own permissions,
so two people can legitimately see different numbers in the same view.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import func, select

from database import Canvas, CanvasVersion, User, async_session


CANVAS_VISIBILITIES = ("organization", "departments", "private")


def canvas_dict(canvas: Canvas, creator: Optional[User] = None) -> dict[str, Any]:
    return {
        "id": canvas.id,
        "title": canvas.title,
        "description": canvas.description,
        "visibility": canvas.visibility,
        "department_ids": canvas.department_ids or [],
        "current_version": canvas.current_version,
        "current_version_id": canvas.current_version_id,
        "status": canvas.status,
        "created_by_user_id": canvas.created_by_user_id,
        "creator_name": creator.name if creator else None,
        "created_at": f"{canvas.created_at.isoformat()}Z",
        "updated_at": f"{canvas.updated_at.isoformat()}Z",
    }


def version_dict(
    version: CanvasVersion, *, include_spec: bool = True
) -> dict[str, Any]:
    payload = {
        "id": version.id,
        "canvas_id": version.canvas_id,
        "version": version.version,
        "prompt": version.prompt,
        "origin": version.origin,
        "provider": version.provider,
        "model": version.model,
        "restored_from_version": version.restored_from_version,
        "context_summary": version.context_summary or {},
        "created_by_user_id": version.created_by_user_id,
        "created_at": f"{version.created_at.isoformat()}Z",
    }
    if include_spec:
        payload["spec"] = version.spec or {}
    return payload


def canvas_visible(
    canvas: Canvas,
    *,
    user_id: str,
    department_ids: list[str],
    access_all: bool,
) -> bool:
    """Whether this viewer may see the Canvas at all.

    The creator always keeps access to their own view. Otherwise visibility
    decides, and a private Canvas is invisible — callers turn that into a 404
    rather than a 403 so its existence is not disclosed.
    """
    if canvas.created_by_user_id == user_id:
        return True
    if canvas.visibility == "private":
        return False
    if canvas.visibility == "departments":
        required = set(canvas.department_ids or [])
        return access_all or required.issubset(set(department_ids))
    return True


async def create_canvas(
    *,
    org_id: str,
    user_id: str,
    title: str,
    description: str,
    spec: dict[str, Any],
    prompt: str,
    origin: str,
    visibility: str = "private",
    department_ids: Optional[list[str]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    context_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create a Canvas together with its first immutable version."""
    now = datetime.utcnow()
    canvas_id = str(uuid4())
    version = CanvasVersion(
        id=str(uuid4()),
        canvas_id=canvas_id,
        org_id=org_id,
        version=1,
        prompt=prompt,
        origin=origin,
        spec=spec,
        context_summary=context_summary or {},
        provider=provider,
        model=model,
        created_by_user_id=user_id,
        created_at=now,
    )
    canvas = Canvas(
        id=canvas_id,
        org_id=org_id,
        title=title[:160],
        description=description,
        visibility=visibility,
        department_ids=department_ids or [],
        current_version_id=version.id,
        current_version=1,
        status="active",
        created_by_user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    async with async_session() as session:
        session.add_all([canvas, version])
        await session.commit()
        creator = await session.get(User, user_id)
        return {
            **canvas_dict(canvas, creator),
            "version": version_dict(version),
        }


async def append_version(
    *,
    org_id: str,
    canvas_id: str,
    user_id: str,
    spec: dict[str, Any],
    prompt: str,
    origin: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    context_summary: Optional[dict[str, Any]] = None,
    restored_from_version: Optional[int] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Append a revision. Earlier versions are never modified."""
    now = datetime.utcnow()
    async with async_session() as session:
        canvas = await session.get(Canvas, canvas_id)
        if canvas is None or canvas.org_id != org_id:
            return None

        highest = (
            await session.execute(
                select(func.max(CanvasVersion.version)).where(
                    CanvasVersion.canvas_id == canvas_id
                )
            )
        ).scalar_one()
        version = CanvasVersion(
            id=str(uuid4()),
            canvas_id=canvas_id,
            org_id=org_id,
            version=int(highest or 0) + 1,
            prompt=prompt,
            origin=origin,
            spec=spec,
            context_summary=context_summary or {},
            provider=provider,
            model=model,
            restored_from_version=restored_from_version,
            created_by_user_id=user_id,
            created_at=now,
        )
        session.add(version)
        canvas.current_version_id = version.id
        canvas.current_version = version.version
        if title:
            canvas.title = title[:160]
        if description is not None:
            canvas.description = description
        canvas.updated_at = now
        await session.commit()
        return version_dict(version)


async def get_canvas_record(org_id: str, canvas_id: str) -> Optional[Canvas]:
    async with async_session() as session:
        canvas = await session.get(Canvas, canvas_id)
        if canvas is None or canvas.org_id != org_id:
            return None
        return canvas


async def get_version_record(
    org_id: str, canvas_id: str, version_id: str
) -> Optional[CanvasVersion]:
    async with async_session() as session:
        version = await session.get(CanvasVersion, version_id)
        if (
            version is None
            or version.org_id != org_id
            or version.canvas_id != canvas_id
        ):
            return None
        return version


async def get_current_version(
    org_id: str, canvas_id: str
) -> Optional[CanvasVersion]:
    async with async_session() as session:
        canvas = await session.get(Canvas, canvas_id)
        if canvas is None or canvas.org_id != org_id:
            return None
        if canvas.current_version_id:
            version = await session.get(CanvasVersion, canvas.current_version_id)
            if version is not None:
                return version
        return (
            await session.execute(
                select(CanvasVersion)
                .where(CanvasVersion.canvas_id == canvas_id)
                .order_by(CanvasVersion.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()


async def list_versions(org_id: str, canvas_id: str) -> list[dict[str, Any]]:
    async with async_session() as session:
        versions = (
            await session.execute(
                select(CanvasVersion)
                .where(
                    CanvasVersion.org_id == org_id,
                    CanvasVersion.canvas_id == canvas_id,
                )
                .order_by(CanvasVersion.version.desc())
            )
        ).scalars().all()
        # The list is for history navigation; specs are fetched per version.
        return [version_dict(version, include_spec=False) for version in versions]


async def list_canvases(
    org_id: str,
    *,
    user_id: str,
    department_ids: list[str],
    access_all: bool,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    async with async_session() as session:
        canvases = (
            await session.execute(
                select(Canvas)
                .where(Canvas.org_id == org_id)
                .order_by(Canvas.updated_at.desc())
            )
        ).scalars().all()

        result: list[dict[str, Any]] = []
        for canvas in canvases:
            if canvas.status == "archived" and not include_archived:
                continue
            if not canvas_visible(
                canvas,
                user_id=user_id,
                department_ids=department_ids,
                access_all=access_all,
            ):
                continue
            creator = await session.get(User, canvas.created_by_user_id)
            result.append({
                **canvas_dict(canvas, creator),
                "is_owner": canvas.created_by_user_id == user_id,
            })
        return result


async def update_canvas_settings(
    org_id: str,
    canvas_id: str,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    visibility: Optional[str] = None,
    department_ids: Optional[list[str]] = None,
    status: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        canvas = await session.get(Canvas, canvas_id)
        if canvas is None or canvas.org_id != org_id:
            return None
        if title is not None:
            canvas.title = title[:160]
        if description is not None:
            canvas.description = description
        if visibility is not None:
            canvas.visibility = visibility
        if department_ids is not None:
            canvas.department_ids = department_ids
        if status is not None:
            canvas.status = status
        canvas.updated_at = datetime.utcnow()
        await session.commit()
        creator = await session.get(User, canvas.created_by_user_id)
        return canvas_dict(canvas, creator)


async def count_recent_versions(org_id: str, user_id: str, *, since: datetime) -> int:
    """How many versions this person has generated lately.

    Generation is a paid call and refinement invites rapid iteration, so the
    API uses this to apply a per-user budget.
    """
    async with async_session() as session:
        return int((
            await session.execute(
                select(func.count())
                .select_from(CanvasVersion)
                .where(
                    CanvasVersion.org_id == org_id,
                    CanvasVersion.created_by_user_id == user_id,
                    CanvasVersion.created_at >= since,
                    CanvasVersion.origin.in_(("generated", "refined")),
                )
            )
        ).scalar_one())
