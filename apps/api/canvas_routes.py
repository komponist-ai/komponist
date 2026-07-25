"""HTTP surface for Canvas.

Kept in its own module so the Canvas authorization rules sit in one readable
place. Every render path revalidates the stored specification before it
resolves anything, so a spec altered in the database — or arriving through a
future import — can never reach the renderer unchecked.
"""

from datetime import datetime, timedelta
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from canvas_data import resolve_spec
from canvas_examples import EXAMPLE_SUMMARIES, EXAMPLES
from canvas_generate import (
    CanvasGenerationError,
    generate_canvas,
    refine_canvas,
)
from canvas_spec import CanvasValidationError, validate_spec
from canvas_store import (
    CANVAS_VISIBILITIES,
    append_version,
    canvas_dict,
    canvas_visible,
    count_recent_versions,
    create_canvas,
    get_canvas_record,
    get_current_version,
    get_version_record,
    list_canvases,
    list_versions,
    update_canvas_settings,
    version_dict,
)


router = APIRouter(prefix="/canvases", tags=["canvas"])

# Generation is a paid call and "change this view" invites fast iteration.
GENERATION_WINDOW = timedelta(hours=1)
GENERATION_BUDGET = 40


class CanvasCreateRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=1200)
    title: str = Field(default="", max_length=160)
    visibility: Literal["organization", "departments", "private"] = "private"
    department_ids: List[str] = Field(default_factory=list, max_length=12)


class CanvasExampleRequest(BaseModel):
    example: str = Field(min_length=1, max_length=80)
    visibility: Literal["organization", "departments", "private"] = "private"


class CanvasRefineRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=1200)


class CanvasSettingsRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=400)
    visibility: Optional[Literal["organization", "departments", "private"]] = None
    department_ids: Optional[List[str]] = Field(default=None, max_length=12)


async def _viewer(request: Request, org_id: str, *, write: bool = False) -> dict:
    import main

    return await main._authorized_org_user(request, org_id, write=write)


async def _readable_canvas(request: Request, org_id: str, canvas_id: str):
    """Load a Canvas the caller may see, or 404 without disclosing it exists."""
    user = await _viewer(request, org_id)
    canvas = await get_canvas_record(org_id, canvas_id)
    if canvas is None or not canvas_visible(
        canvas,
        user_id=user["id"],
        department_ids=user.get("department_ids") or [],
        access_all=bool(user.get("access_all_departments")),
    ):
        raise HTTPException(status_code=404, detail="Canvas not found")
    return user, canvas


async def _owned_canvas(request: Request, org_id: str, canvas_id: str):
    """Only the creator may change a Canvas or its specification."""
    user, canvas = await _readable_canvas(request, org_id, canvas_id)
    if canvas.created_by_user_id != user["id"]:
        raise HTTPException(
            status_code=403, detail="Only the person who created this Canvas can change it"
        )
    return user, canvas


async def _check_budget(org_id: str, user: dict) -> None:
    used = await count_recent_versions(
        org_id, user["id"], since=datetime.utcnow() - GENERATION_WINDOW
    )
    if used >= GENERATION_BUDGET:
        raise HTTPException(
            status_code=429,
            detail=(
                "You have generated a lot of views in the last hour. "
                "Try again shortly."
            ),
        )


async def _validated_departments(org_id: str, user: dict, ids: List[str]) -> list[str]:
    import main

    validated: list[str] = []
    for department_id in dict.fromkeys(ids):
        resolved = await main._validate_department_scope(org_id, user, department_id)
        if resolved:
            validated.append(resolved)
    return validated


async def _render(org_id: str, user: dict, version: Any) -> dict[str, Any]:
    """Revalidate then resolve. Never render a spec that was only checked once."""
    try:
        spec = validate_spec(version.spec or {})
    except CanvasValidationError as error:
        raise HTTPException(
            status_code=422,
            detail=f"This saved view is no longer valid: {error}",
        ) from error
    data = await resolve_spec(org_id, user, spec)
    return {"spec": spec.model_dump(), "data": data}


@router.get("")
async def get_canvases(
    request: Request,
    org_id: str = Query(...),
    include_archived: bool = Query(False),
):
    user = await _viewer(request, org_id)
    canvases = await list_canvases(
        org_id,
        user_id=user["id"],
        department_ids=user.get("department_ids") or [],
        access_all=bool(user.get("access_all_departments")),
        include_archived=include_archived,
    )
    return {
        "canvases": canvases,
        "total": len(canvases),
        "examples": EXAMPLE_SUMMARIES,
    }


@router.post("/examples", status_code=201)
async def create_canvas_from_example(
    payload: CanvasExampleRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Create a Canvas from a hand-written example.

    No model involved, so the feature is usable with nothing but the local
    test documents already in the graph.
    """
    user = await _viewer(request, org_id, write=True)
    raw = EXAMPLES.get(payload.example)
    if raw is None:
        raise HTTPException(status_code=404, detail="Unknown example")
    spec = validate_spec(raw)
    created = await create_canvas(
        org_id=org_id,
        user_id=user["id"],
        title=spec.title,
        description=spec.description,
        spec=spec.model_dump(),
        prompt=f"Example: {payload.example}",
        origin="example",
        visibility=payload.visibility,
        context_summary={"source": "built-in example"},
    )
    return created


async def _scope_summary(org_id: str, user: dict) -> tuple[list[str], list[str]]:
    """A short, permission-scoped picture of what this user can actually see.

    Only what the caller may already read reaches the prompt, so the model
    cannot be steered toward knowledge outside their scope.
    """
    import main

    try:
        entities, _ = await main._artifact_context(org_id, user, "company overview")
    except Exception:  # noqa: BLE001 - a bare canvas beats a broken request
        return [], []

    lines: list[str] = []
    types: list[str] = []
    for entity in entities[:20]:
        statement = entity.get("statement") or entity.get("detail")
        entity_type = entity.get("entity_type") or "Fact"
        if entity_type not in types:
            types.append(entity_type)
        if statement:
            lines.append(f"{entity_type}: {statement}")
    return lines, types


@router.post("", status_code=201)
async def generate_canvas_view(
    payload: CanvasCreateRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Describe a view in words; the model returns a spec the server validates."""
    user = await _viewer(request, org_id, write=True)
    await _check_budget(org_id, user)

    departments = await _validated_departments(org_id, user, payload.department_ids)
    if payload.visibility == "departments" and not departments:
        raise HTTPException(
            status_code=400,
            detail="Choose at least one department for a department-scoped Canvas",
        )

    context_lines, entity_types = await _scope_summary(org_id, user)
    try:
        spec, metadata = await generate_canvas(
            request=payload.prompt,
            context_lines=context_lines,
            entity_types=entity_types,
        )
    except CanvasGenerationError as error:
        status = 422 if error.code in {"schema_rejected", "unreadable"} else 502
        raise HTTPException(status_code=status, detail=str(error)) from error

    created = await create_canvas(
        org_id=org_id,
        user_id=user["id"],
        title=" ".join(payload.title.split()) or spec.title,
        description=spec.description,
        spec=spec.model_dump(),
        prompt=" ".join(payload.prompt.split()),
        origin="generated",
        visibility=payload.visibility,
        department_ids=departments,
        provider=metadata.get("provider"),
        model=metadata.get("model"),
        context_summary={
            "entity_types": entity_types,
            "fact_count": len(context_lines),
        },
    )
    return created


@router.post("/{canvas_id}/refine", status_code=201)
async def refine_canvas_view(
    canvas_id: str,
    payload: CanvasRefineRequest,
    request: Request,
    org_id: str = Query(...),
):
    """Change a view by describing the change. The result is a new version."""
    user, _ = await _owned_canvas(request, org_id, canvas_id)
    await _check_budget(org_id, user)

    current = await get_current_version(org_id, canvas_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Canvas version not found")

    context_lines, entity_types = await _scope_summary(org_id, user)
    try:
        spec, metadata = await refine_canvas(
            instruction=payload.instruction,
            current=current.spec or {},
            context_lines=context_lines,
            entity_types=entity_types,
        )
    except CanvasGenerationError as error:
        status = 422 if error.code in {"schema_rejected", "unreadable"} else 502
        raise HTTPException(status_code=status, detail=str(error)) from error

    appended = await append_version(
        org_id=org_id,
        canvas_id=canvas_id,
        user_id=user["id"],
        spec=spec.model_dump(),
        prompt=" ".join(payload.instruction.split()),
        origin="refined",
        provider=metadata.get("provider"),
        model=metadata.get("model"),
        context_summary={
            "entity_types": entity_types,
            "fact_count": len(context_lines),
        },
        title=spec.title,
        description=spec.description,
    )
    if appended is None:
        raise HTTPException(status_code=404, detail="Canvas not found")
    return appended


@router.get("/{canvas_id}")
async def get_canvas(
    canvas_id: str,
    request: Request,
    org_id: str = Query(...),
    version: Optional[str] = Query(None),
):
    """Render a Canvas against the caller's own permissions."""
    user, canvas = await _readable_canvas(request, org_id, canvas_id)
    record = (
        await get_version_record(org_id, canvas_id, version)
        if version
        else await get_current_version(org_id, canvas_id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Canvas version not found")

    rendered = await _render(org_id, user, record)
    return {
        **canvas_dict(canvas),
        "is_owner": canvas.created_by_user_id == user["id"],
        "version": version_dict(record),
        **rendered,
    }


@router.get("/{canvas_id}/versions")
async def get_canvas_versions(
    canvas_id: str, request: Request, org_id: str = Query(...)
):
    await _readable_canvas(request, org_id, canvas_id)
    versions = await list_versions(org_id, canvas_id)
    return {"versions": versions, "total": len(versions)}


@router.post("/{canvas_id}/versions/{version_id}/restore", status_code=201)
async def restore_canvas_version(
    canvas_id: str,
    version_id: str,
    request: Request,
    org_id: str = Query(...),
):
    """Restore an earlier version by appending it again as the newest one."""
    user, _ = await _owned_canvas(request, org_id, canvas_id)
    record = await get_version_record(org_id, canvas_id, version_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Canvas version not found")
    try:
        spec = validate_spec(record.spec or {})
    except CanvasValidationError as error:
        raise HTTPException(
            status_code=422, detail=f"That version is no longer valid: {error}"
        ) from error

    appended = await append_version(
        org_id=org_id,
        canvas_id=canvas_id,
        user_id=user["id"],
        spec=spec.model_dump(),
        prompt=f"Restored version {record.version}",
        origin="restored",
        restored_from_version=record.version,
        title=spec.title,
        description=spec.description,
    )
    if appended is None:
        raise HTTPException(status_code=404, detail="Canvas not found")
    return appended


@router.patch("/{canvas_id}")
async def update_canvas(
    canvas_id: str,
    payload: CanvasSettingsRequest,
    request: Request,
    org_id: str = Query(...),
):
    user, canvas = await _owned_canvas(request, org_id, canvas_id)
    departments: Optional[list[str]] = None
    if payload.department_ids is not None:
        departments = await _validated_departments(org_id, user, payload.department_ids)

    visibility = payload.visibility or canvas.visibility
    effective = departments if departments is not None else (canvas.department_ids or [])
    if visibility == "departments" and not effective:
        raise HTTPException(
            status_code=400,
            detail="Choose at least one department for a department-scoped Canvas",
        )

    updated = await update_canvas_settings(
        org_id,
        canvas_id,
        title=" ".join(payload.title.split()) if payload.title else None,
        description=(
            " ".join(payload.description.split())
            if payload.description is not None
            else None
        ),
        visibility=payload.visibility,
        department_ids=departments,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Canvas not found")
    return updated


@router.post("/{canvas_id}/archive")
async def archive_canvas(
    canvas_id: str, request: Request, org_id: str = Query(...)
):
    await _owned_canvas(request, org_id, canvas_id)
    updated = await update_canvas_settings(org_id, canvas_id, status="archived")
    if updated is None:
        raise HTTPException(status_code=404, detail="Canvas not found")
    return updated
