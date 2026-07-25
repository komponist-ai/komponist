"""Versioned, human-approved Workroom plans generated through the LLM provider.

Model output is never trusted directly. It is produced under a strict JSON
Schema (OpenAI Structured Outputs), then re-validated application-side with
Pydantic plus graph checks — unique keys, resolvable dependencies, and no
cycles — before a person ever sees it, and again before it becomes the
active plan.

No chain-of-thought is requested or stored. Provider, model, and token usage
are recorded because they are operational metadata, not model reasoning.
"""

import os
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import func, select

from core.llm import get_llm
from database import (
    Workroom,
    WorkroomPlanVersion,
    WorkroomTask,
    async_session,
)


MAX_PLAN_TASKS = 12

# Strict Structured Outputs schema: every property is required and no extra
# properties are allowed, which is what OpenAI's strict mode demands.
PLAN_SCHEMA: dict[str, Any] = {
    "title": "komponist_workroom_plan",
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "tasks"],
    "properties": {
        "summary": {
            "type": "string",
            "description": "One or two sentences describing the execution strategy.",
        },
        "tasks": {
            "type": "array",
            "description": f"Between 1 and {MAX_PLAN_TASKS} ordered tasks.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "client_key",
                    "title",
                    "description",
                    "assignee_type",
                    "depends_on",
                    "requires_approval",
                ],
                "properties": {
                    "client_key": {
                        "type": "string",
                        "description": "Short stable kebab-case identifier, unique in this plan.",
                    },
                    "title": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "What to actually do. Actionable, not a restatement of the title.",
                    },
                    "assignee_type": {
                        "type": "string",
                        "enum": ["agent", "human"],
                    },
                    "depends_on": {
                        "type": "array",
                        "description": "client_key values of tasks that must finish first.",
                        "items": {"type": "string"},
                    },
                    "requires_approval": {"type": "boolean"},
                },
            },
        },
    },
}


class PlanTaskSpec(BaseModel):
    client_key: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=3, max_length=1200)
    assignee_type: Literal["agent", "human"] = "agent"
    depends_on: list[str] = Field(default_factory=list, max_length=MAX_PLAN_TASKS)
    requires_approval: bool = False

    @field_validator("client_key")
    @classmethod
    def _normalize_key(cls, value: str) -> str:
        key = "-".join(value.strip().lower().split())
        cleaned = "".join(
            character for character in key if character.isalnum() or character == "-"
        ).strip("-")
        if not cleaned:
            raise ValueError("client_key must contain letters or digits")
        return cleaned[:60]

    @field_validator("title", "description")
    @classmethod
    def _collapse_whitespace(cls, value: str) -> str:
        return " ".join(value.split())


class PlanSpec(BaseModel):
    summary: str = Field(min_length=3, max_length=1200)
    tasks: list[PlanTaskSpec] = Field(min_length=1, max_length=MAX_PLAN_TASKS)

    @field_validator("summary")
    @classmethod
    def _collapse_summary(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("tasks")
    @classmethod
    def _check_graph(cls, tasks: list[PlanTaskSpec]) -> list[PlanTaskSpec]:
        keys = [task.client_key for task in tasks]
        if len(set(keys)) != len(keys):
            raise ValueError("Task keys must be unique within a plan")

        known = set(keys)
        for task in tasks:
            # Self-dependency is the degenerate cycle; reject it early.
            if task.client_key in task.depends_on:
                raise ValueError(f"Task {task.client_key} cannot depend on itself")
            for dependency in task.depends_on:
                if dependency not in known:
                    raise ValueError(
                        f"Task {task.client_key} depends on unknown task {dependency}"
                    )

        # Depth-first search over the dependency graph rejects any cycle.
        edges = {task.client_key: list(task.depends_on) for task in tasks}
        visiting: set[str] = set()
        done: set[str] = set()

        def visit(node: str) -> None:
            if node in done:
                return
            if node in visiting:
                raise ValueError("The plan contains a dependency cycle")
            visiting.add(node)
            for dependency in edges.get(node, []):
                visit(dependency)
            visiting.discard(node)
            done.add(node)

        for key in keys:
            visit(key)
        return tasks


class PlanGenerationError(Exception):
    """A plan could not be produced or did not survive validation."""

    def __init__(self, message: str, *, code: str = "plan_generation_failed"):
        super().__init__(message)
        self.code = code


def build_plan_prompt(
    *, objective: str, title: str, context_lines: list[str], guidance: str
) -> tuple[str, str]:
    """Compose the plan prompt. Facts come only from supplied context."""
    context_block = "\n".join(f"- {line}" for line in context_lines[:24])
    if not context_block:
        context_block = (
            "- (No confirmed company facts are in scope for this Workroom yet.)"
        )

    prompt = (
        f"Workroom: {title}\n"
        f"Objective: {objective}\n\n"
        "Confirmed company context available to this Workroom:\n"
        f"{context_block}\n\n"
        + (f"Additional direction from the team: {guidance}\n\n" if guidance else "")
        + "Produce an execution plan of at most "
        f"{MAX_PLAN_TASKS} tasks that moves this objective forward."
    )
    system = (
        "You plan collaborative work for a team that shares a governed company "
        "knowledge base. Produce concrete, actionable tasks a person or an "
        "agent could start immediately.\n"
        "Rules:\n"
        "- Never state a company fact that is not present in the supplied "
        "context. Write tasks that go and find out instead.\n"
        "- Assign research and drafting over the knowledge base to 'agent'.\n"
        "- Assign decisions, approvals, and outside conversations to 'human'.\n"
        "- Use depends_on only for genuine ordering constraints.\n"
        "- Set requires_approval when a task produces something published or "
        "shared outside the room.\n"
        "- Do not include reasoning, commentary, or Markdown."
    )
    return prompt, system


async def generate_plan_spec(
    *, objective: str, title: str, context_lines: list[str], guidance: str = ""
) -> tuple[PlanSpec, dict[str, Any]]:
    """Ask the configured provider for a plan and validate it thoroughly.

    Returns the validated plan and provider metadata. Raises
    :class:`PlanGenerationError` with a message safe to show a user.
    """
    prompt, system = build_plan_prompt(
        objective=objective, title=title, context_lines=context_lines, guidance=guidance
    )
    client = get_llm()
    model = getattr(client, "default_model", None)
    provider = os.getenv("KOMPONIST_LLM_PROVIDER", "openai")
    if os.getenv("KOMPONIST_AI_MODE", "live").lower() == "mock":
        provider = "mock"

    try:
        raw = await client.call_json(
            prompt=prompt,
            system=system,
            max_tokens=4000,
            schema=PLAN_SCHEMA,
        )
    except ValueError as error:
        # The client raises ValueError for refusals, incomplete responses, and
        # unparseable output. Keep provider wording out of the user's face.
        message = str(error)
        if "refused" in message.lower():
            raise PlanGenerationError(
                "The model declined to plan this objective. Rephrase the "
                "objective and try again.",
                code="refusal",
            ) from error
        if "status is" in message or "incomplete" in message.lower():
            raise PlanGenerationError(
                "The model response was cut off before a full plan arrived. "
                "Try again, or shorten the objective.",
                code="incomplete",
            ) from error
        raise PlanGenerationError(
            "The model returned a plan this workspace could not read.",
            code="unreadable",
        ) from error
    except Exception as error:  # noqa: BLE001 - surfaced as a friendly message
        detail = str(error).lower()
        if "api key" in detail or "authentication" in detail or "401" in detail:
            raise PlanGenerationError(
                "Plan generation is not configured: the workspace's model "
                "credentials were rejected. Ask an administrator to check them.",
                code="provider_unauthorized",
            ) from error
        if "model" in detail and ("not found" in detail or "does not exist" in detail):
            raise PlanGenerationError(
                "The configured model is unavailable for this workspace. Ask "
                "an administrator to check the model setting.",
                code="provider_model_invalid",
            ) from error
        raise PlanGenerationError(
            "The planning service is unavailable right now. Try again shortly.",
            code="provider_unavailable",
        ) from error

    try:
        spec = PlanSpec.model_validate(raw)
    except ValidationError as error:
        raise PlanGenerationError(
            "The generated plan did not meet this workspace's rules "
            f"({error.error_count()} problems). Try generating it again.",
            code="schema_rejected",
        ) from error

    return spec, {"provider": provider, "model": model}


def plan_dict(version: WorkroomPlanVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "workroom_id": version.workroom_id,
        "version": version.version,
        "status": version.status,
        "summary": version.summary,
        "spec": version.spec or {},
        "provider": version.provider,
        "model": version.model,
        "usage": version.usage or {},
        "created_by_user_id": version.created_by_user_id,
        "approved_by_user_id": version.approved_by_user_id,
        "created_at": f"{version.created_at.isoformat()}Z",
        "updated_at": f"{version.updated_at.isoformat()}Z",
        "approved_at": (
            f"{version.approved_at.isoformat()}Z" if version.approved_at else None
        ),
    }


async def create_plan_version(
    *,
    org_id: str,
    room_id: str,
    spec: PlanSpec,
    provider: Optional[str],
    model: Optional[str],
    usage: Optional[dict[str, Any]],
    created_by_user_id: str,
) -> dict[str, Any]:
    """Store a new draft. Any previous draft is superseded, never overwritten."""
    now = datetime.utcnow()
    async with async_session() as session:
        highest = (
            await session.execute(
                select(func.max(WorkroomPlanVersion.version)).where(
                    WorkroomPlanVersion.workroom_id == room_id
                )
            )
        ).scalar_one()

        previous_drafts = (
            await session.execute(
                select(WorkroomPlanVersion).where(
                    WorkroomPlanVersion.workroom_id == room_id,
                    WorkroomPlanVersion.status == "draft",
                )
            )
        ).scalars().all()
        for draft in previous_drafts:
            draft.status = "superseded"
            draft.updated_at = now

        version = WorkroomPlanVersion(
            id=str(uuid4()),
            workroom_id=room_id,
            org_id=org_id,
            version=int(highest or 0) + 1,
            status="draft",
            summary=spec.summary,
            spec=spec.model_dump(),
            provider=provider,
            model=model,
            usage=usage or {},
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        session.add(version)
        await session.commit()
        return plan_dict(version)


async def list_plan_versions(org_id: str, room_id: str) -> list[dict[str, Any]]:
    async with async_session() as session:
        versions = (
            await session.execute(
                select(WorkroomPlanVersion)
                .where(
                    WorkroomPlanVersion.org_id == org_id,
                    WorkroomPlanVersion.workroom_id == room_id,
                )
                .order_by(WorkroomPlanVersion.version.desc())
            )
        ).scalars().all()
        return [plan_dict(version) for version in versions]


async def get_plan_version(
    org_id: str, room_id: str, plan_id: str
) -> Optional[WorkroomPlanVersion]:
    async with async_session() as session:
        version = await session.get(WorkroomPlanVersion, plan_id)
        if (
            version is None
            or version.org_id != org_id
            or version.workroom_id != room_id
        ):
            return None
        return version


async def replace_draft_spec(
    org_id: str, room_id: str, plan_id: str, spec: PlanSpec
) -> Optional[dict[str, Any]]:
    """Save a human's edits to a draft. Only drafts are editable."""
    async with async_session() as session:
        version = await session.get(WorkroomPlanVersion, plan_id)
        if (
            version is None
            or version.org_id != org_id
            or version.workroom_id != room_id
            or version.status != "draft"
        ):
            return None
        version.spec = spec.model_dump()
        version.summary = spec.summary
        version.updated_at = datetime.utcnow()
        await session.commit()
        return plan_dict(version)


async def reject_draft(
    org_id: str, room_id: str, plan_id: str
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        version = await session.get(WorkroomPlanVersion, plan_id)
        if (
            version is None
            or version.org_id != org_id
            or version.workroom_id != room_id
            or version.status != "draft"
        ):
            return None
        version.status = "rejected"
        version.updated_at = datetime.utcnow()
        await session.commit()
        return plan_dict(version)


async def approve_draft(
    *, org_id: str, room_id: str, plan_id: str, user_id: str
) -> Optional[tuple[dict[str, Any], list[str]]]:
    """Approve a draft and materialise its tasks in one transaction.

    Tasks already linked to a plan key are updated in place so run history and
    deliverables stay attached. Tasks that the new plan drops are archived
    rather than deleted, and tasks a person added by hand are left alone.
    """
    now = datetime.utcnow()
    async with async_session() as session:
        version = await session.get(WorkroomPlanVersion, plan_id)
        if (
            version is None
            or version.org_id != org_id
            or version.workroom_id != room_id
            or version.status != "draft"
        ):
            return None

        room = await session.get(Workroom, room_id)
        if room is None or room.org_id != org_id:
            return None

        spec = PlanSpec.model_validate(version.spec or {})

        existing = (
            await session.execute(
                select(WorkroomTask).where(WorkroomTask.workroom_id == room_id)
            )
        ).scalars().all()
        by_key = {
            task.client_key: task for task in existing if task.client_key
        }

        # First pass: create or update every task so keys resolve to ids.
        resolved: dict[str, WorkroomTask] = {}
        for position, task_spec in enumerate(spec.tasks):
            task = by_key.get(task_spec.client_key)
            if task is None:
                task = WorkroomTask(
                    id=str(uuid4()),
                    workroom_id=room_id,
                    org_id=org_id,
                    client_key=task_spec.client_key,
                    title=task_spec.title[:180],
                    description=task_spec.description,
                    status="todo",
                    assignee_type=task_spec.assignee_type,
                    assignee_name=(
                        "Komponist Analyst"
                        if task_spec.assignee_type == "agent"
                        else "Unassigned"
                    ),
                    position=position,
                    requires_approval=task_spec.requires_approval,
                    depends_on=[],
                    plan_version_id=version.id,
                    created_by_user_id=user_id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(task)
            else:
                task.title = task_spec.title[:180]
                task.description = task_spec.description
                task.position = position
                task.requires_approval = task_spec.requires_approval
                task.plan_version_id = version.id
                task.archived_at = None
                # Never silently reassign work someone already picked up.
                if task.assignee_user_id is None:
                    task.assignee_type = task_spec.assignee_type
                    if task_spec.assignee_type == "agent":
                        task.assignee_name = "Komponist Analyst"
                task.updated_at = now
            resolved[task_spec.client_key] = task

        # Second pass: dependencies as task ids, now that all ids exist.
        for task_spec in spec.tasks:
            resolved[task_spec.client_key].depends_on = [
                resolved[dependency].id
                for dependency in task_spec.depends_on
                if dependency in resolved
            ]

        planned_keys = {task_spec.client_key for task_spec in spec.tasks}
        for task in existing:
            # Only plan-owned tasks are archived; hand-made tasks survive.
            if task.client_key and task.client_key not in planned_keys:
                task.archived_at = now
                task.updated_at = now

        version.status = "approved"
        version.approved_by_user_id = user_id
        version.approved_at = now
        version.updated_at = now
        room.updated_at = now

        await session.commit()
        return plan_dict(version), [
            resolved[task_spec.client_key].id for task_spec in spec.tasks
        ]
