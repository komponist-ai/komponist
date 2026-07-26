"""Persistence primitives for shared human-and-agent Workrooms."""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import func, select, update as sql_update

from database import (
    OrganizationMembership,
    User,
    Workroom,
    WorkroomEvent,
    WorkroomMember,
    WorkroomRun,
    WorkroomTask,
    async_session,
)


ROOM_ROLES = ("owner", "editor", "approver", "viewer")
ROOM_VISIBILITIES = ("organization", "departments", "private")

# Room roles are not a simple ladder — an approver signs off on outputs but
# does not edit the plan — so permissions are listed explicitly.
ROOM_PERMISSIONS: dict[str, set[str]] = {
    "owner": {"view", "comment", "edit", "approve", "manage"},
    "editor": {"view", "comment", "edit"},
    "approver": {"view", "comment", "approve"},
    "viewer": {"view", "comment"},
}


def room_visible(
    room: Workroom, department_ids: list[str], access_all: bool
) -> bool:
    """Whether the room's department scope is covered by the user's access."""
    required = set(room.department_ids or [])
    return access_all or required.issubset(set(department_ids))


def effective_room_role(
    room: Workroom,
    membership: Optional[WorkroomMember],
    *,
    department_ids: list[str],
    access_all: bool,
    org_role: str = "member",
) -> Optional[str]:
    """The caller's role in this room, or ``None`` when they cannot see it.

    An explicit membership always wins. Otherwise visibility decides whether
    the caller is an implicit viewer. Organization admins may administer rooms
    they can already see, but a private room still requires membership — being
    an org admin must never silently reveal a private room or widen the
    knowledge the agent may read.
    """
    if membership is not None and membership.status == "active":
        return membership.room_role

    visibility = room.visibility or "organization"
    if visibility == "private":
        return None
    if visibility == "departments" and not room_visible(
        room, department_ids, access_all
    ):
        return None
    if org_role in {"owner", "admin"}:
        return "owner"
    return "viewer"


def room_can(role: Optional[str], permission: str) -> bool:
    return permission in ROOM_PERMISSIONS.get(role or "", set())


def member_dict(member: WorkroomMember, user: Optional[User]) -> dict[str, Any]:
    return {
        "id": member.id,
        "workroom_id": member.workroom_id,
        "user_id": member.user_id,
        "name": user.name if user else "Team member",
        "email": user.email if user else None,
        "room_role": member.room_role,
        "status": member.status,
        "invited_by_user_id": member.invited_by_user_id,
        "created_at": f"{member.created_at.isoformat()}Z",
        "updated_at": f"{member.updated_at.isoformat()}Z",
    }


def room_dict(room: Workroom) -> dict[str, Any]:
    return {
        "id": room.id,
        "title": room.title,
        "objective": room.objective,
        "status": room.status,
        "visibility": room.visibility or "organization",
        "department_ids": room.department_ids or [],
        "created_by_user_id": room.created_by_user_id,
        "created_at": f"{room.created_at.isoformat()}Z",
        "updated_at": f"{room.updated_at.isoformat()}Z",
    }


def task_dict(task: WorkroomTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "workroom_id": task.workroom_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "assignee_type": task.assignee_type,
        "assignee_name": task.assignee_name,
        "assignee_user_id": task.assignee_user_id,
        "position": task.position,
        "client_key": task.client_key,
        "plan_version_id": task.plan_version_id,
        "depends_on": task.depends_on or [],
        "requires_approval": bool(task.requires_approval),
        "archived_at": (
            f"{task.archived_at.isoformat()}Z" if task.archived_at else None
        ),
        "artifact_id": task.artifact_id,
        "created_by_user_id": task.created_by_user_id,
        "created_at": f"{task.created_at.isoformat()}Z",
        "updated_at": f"{task.updated_at.isoformat()}Z",
    }


def run_dict(run: WorkroomRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "workroom_id": run.workroom_id,
        "task_id": run.task_id,
        "agent_name": run.agent_name,
        "instruction": run.instruction,
        "status": run.status,
        "current_step": run.current_step,
        "context_snapshot": run.context_snapshot or {},
        "result": run.result or {},
        "redirected_from_run_id": run.redirected_from_run_id,
        "created_by_user_id": run.created_by_user_id,
        "approved_by_user_id": run.approved_by_user_id,
        "created_at": f"{run.created_at.isoformat()}Z",
        "updated_at": f"{run.updated_at.isoformat()}Z",
    }


def event_dict(event: WorkroomEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "workroom_id": event.workroom_id,
        "run_id": event.run_id,
        "actor_type": event.actor_type,
        "actor_name": event.actor_name,
        "event_type": event.event_type,
        "message": event.message,
        "payload": event.payload or {},
        "created_at": f"{event.created_at.isoformat()}Z",
    }


async def get_org_member(org_id: str, user_id: str) -> Optional[dict[str, Any]]:
    """Look up an active organization member, who alone may join a Workroom."""
    async with async_session() as session:
        membership = (
            await session.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.org_id == org_id,
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.status == "active",
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            return None
        user = await session.get(User, user_id)
        return {
            "id": user_id,
            "name": user.name if user else "Team member",
            "email": user.email if user else None,
            "role": membership.role,
        }


async def get_membership(
    room_id: str, user_id: str
) -> Optional[WorkroomMember]:
    async with async_session() as session:
        return (
            await session.execute(
                select(WorkroomMember).where(
                    WorkroomMember.workroom_id == room_id,
                    WorkroomMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()


async def list_members(org_id: str, room_id: str) -> list[dict[str, Any]]:
    async with async_session() as session:
        members = (
            await session.execute(
                select(WorkroomMember)
                .where(
                    WorkroomMember.org_id == org_id,
                    WorkroomMember.workroom_id == room_id,
                )
                .order_by(WorkroomMember.created_at)
            )
        ).scalars().all()
        result = []
        for member in members:
            user = await session.get(User, member.user_id)
            result.append(member_dict(member, user))
        return result


async def add_member(
    *,
    org_id: str,
    room_id: str,
    user_id: str,
    room_role: str,
    invited_by_user_id: str,
) -> dict[str, Any]:
    """Add or reactivate a participant. Re-adding a removed person restores them."""
    now = datetime.utcnow()
    async with async_session() as session:
        existing = (
            await session.execute(
                select(WorkroomMember).where(
                    WorkroomMember.workroom_id == room_id,
                    WorkroomMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.room_role = room_role
            existing.status = "active"
            existing.updated_at = now
            member = existing
        else:
            member = WorkroomMember(
                id=str(uuid4()),
                workroom_id=room_id,
                org_id=org_id,
                user_id=user_id,
                room_role=room_role,
                status="active",
                invited_by_user_id=invited_by_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(member)
        await session.commit()
        user = await session.get(User, user_id)
        return member_dict(member, user)


async def set_member_role(
    org_id: str, room_id: str, user_id: str, room_role: str
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        member = (
            await session.execute(
                select(WorkroomMember).where(
                    WorkroomMember.org_id == org_id,
                    WorkroomMember.workroom_id == room_id,
                    WorkroomMember.user_id == user_id,
                    WorkroomMember.status == "active",
                )
            )
        ).scalar_one_or_none()
        if member is None:
            return None
        member.room_role = room_role
        member.updated_at = datetime.utcnow()
        await session.commit()
        user = await session.get(User, user_id)
        return member_dict(member, user)


async def remove_member(
    org_id: str, room_id: str, user_id: str
) -> Optional[dict[str, Any]]:
    """Deactivate rather than delete, so the audit trail stays intact."""
    async with async_session() as session:
        member = (
            await session.execute(
                select(WorkroomMember).where(
                    WorkroomMember.org_id == org_id,
                    WorkroomMember.workroom_id == room_id,
                    WorkroomMember.user_id == user_id,
                    WorkroomMember.status == "active",
                )
            )
        ).scalar_one_or_none()
        if member is None:
            return None
        member.status = "removed"
        member.updated_at = datetime.utcnow()
        await session.commit()
        user = await session.get(User, user_id)
        return member_dict(member, user)


async def count_active_owners(room_id: str) -> int:
    async with async_session() as session:
        return int((
            await session.execute(
                select(func.count())
                .select_from(WorkroomMember)
                .where(
                    WorkroomMember.workroom_id == room_id,
                    WorkroomMember.room_role == "owner",
                    WorkroomMember.status == "active",
                )
            )
        ).scalar_one())


async def update_room_settings(
    org_id: str,
    room_id: str,
    *,
    title: Optional[str] = None,
    objective: Optional[str] = None,
    visibility: Optional[str] = None,
    department_ids: Optional[list[str]] = None,
    status: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        room = await session.get(Workroom, room_id)
        if room is None or room.org_id != org_id:
            return None
        if title is not None:
            room.title = title[:160]
        if objective is not None:
            room.objective = objective
        if visibility is not None:
            room.visibility = visibility
        if department_ids is not None:
            room.department_ids = department_ids
        if status is not None:
            room.status = status
        room.updated_at = datetime.utcnow()
        await session.commit()
        return room_dict(room)


async def create_room(
    *,
    org_id: str,
    user_id: str,
    user_name: str,
    title: str,
    objective: str,
    department_ids: list[str],
    visibility: str = "organization",
) -> dict[str, Any]:
    now = datetime.utcnow()
    room = Workroom(
        id=str(uuid4()),
        org_id=org_id,
        title=title[:160],
        objective=objective,
        status="active",
        visibility=visibility,
        department_ids=department_ids,
        created_by_user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    owner = WorkroomMember(
        id=str(uuid4()),
        workroom_id=room.id,
        org_id=org_id,
        user_id=user_id,
        room_role="owner",
        status="active",
        invited_by_user_id=None,
        created_at=now,
        updated_at=now,
    )
    task = WorkroomTask(
        id=str(uuid4()),
        workroom_id=room.id,
        org_id=org_id,
        title="Research and prepare a grounded briefing",
        description=objective,
        status="todo",
        assignee_type="agent",
        assignee_name="Komponist Analyst",
        position=0,
        created_by_user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    event = WorkroomEvent(
        workroom_id=room.id,
        org_id=org_id,
        actor_type="human",
        actor_name=user_name[:120],
        event_type="room_created",
        message=f"Created the Workroom “{room.title}”.",
        payload={"task_id": task.id},
        created_at=now,
    )
    async with async_session() as session:
        session.add_all([room, owner, task, event])
        await session.commit()
        creator = await session.get(User, user_id)
        members = [member_dict(owner, creator)]
    return {
        **room_dict(room),
        "room_role": "owner",
        "tasks": [task_dict(task)],
        "runs": [],
        "members": members,
        "events": [event_dict(event)],
    }


async def list_rooms(
    org_id: str,
    department_ids: list[str],
    access_all: bool,
    *,
    user_id: str,
    org_role: str = "member",
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    async with async_session() as session:
        rooms = (
            await session.execute(
                select(Workroom)
                .where(Workroom.org_id == org_id)
                .order_by(Workroom.updated_at.desc())
            )
        ).scalars().all()
        memberships = {
            member.workroom_id: member
            for member in (
                await session.execute(
                    select(WorkroomMember).where(
                        WorkroomMember.org_id == org_id,
                        WorkroomMember.user_id == user_id,
                    )
                )
            ).scalars().all()
        }

        visible: list[tuple[Workroom, str]] = []
        for room in rooms:
            if room.status == "archived" and not include_archived:
                continue
            role = effective_room_role(
                room,
                memberships.get(room.id),
                department_ids=department_ids,
                access_all=access_all,
                org_role=org_role,
            )
            if role is not None:
                visible.append((room, role))

        result: list[dict[str, Any]] = []
        for room, role in visible:
            tasks = (
                await session.execute(
                    select(WorkroomTask).where(
                        WorkroomTask.workroom_id == room.id,
                        WorkroomTask.archived_at.is_(None),
                    )
                )
            ).scalars().all()
            runs = (
                await session.execute(
                    select(WorkroomRun)
                    .where(WorkroomRun.workroom_id == room.id)
                    .order_by(WorkroomRun.created_at.desc())
                    .limit(1)
                )
            ).scalars().all()
            creator = await session.get(User, room.created_by_user_id)
            member_count = int((
                await session.execute(
                    select(func.count())
                    .select_from(WorkroomMember)
                    .where(
                        WorkroomMember.workroom_id == room.id,
                        WorkroomMember.status == "active",
                    )
                )
            ).scalar_one())
            result.append({
                **room_dict(room),
                "room_role": role,
                "creator": {
                    "id": room.created_by_user_id,
                    "name": creator.name if creator else "Team member",
                },
                "member_count": member_count,
                "task_count": len(tasks),
                "completed_task_count": sum(task.status == "completed" for task in tasks),
                "latest_run": run_dict(runs[0]) if runs else None,
            })
        return result


async def get_room(
    org_id: str,
    room_id: str,
    department_ids: list[str],
    access_all: bool,
    *,
    user_id: str,
    org_role: str = "member",
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        room = await session.get(Workroom, room_id)
        if room is None or room.org_id != org_id:
            return None
        membership = (
            await session.execute(
                select(WorkroomMember).where(
                    WorkroomMember.workroom_id == room_id,
                    WorkroomMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        role = effective_room_role(
            room,
            membership,
            department_ids=department_ids,
            access_all=access_all,
            org_role=org_role,
        )
        if role is None:
            return None
        tasks = (
            await session.execute(
                select(WorkroomTask)
                .where(
                    WorkroomTask.workroom_id == room_id,
                    WorkroomTask.archived_at.is_(None),
                )
                .order_by(WorkroomTask.position, WorkroomTask.created_at)
            )
        ).scalars().all()
        runs = (
            await session.execute(
                select(WorkroomRun)
                .where(WorkroomRun.workroom_id == room_id)
                .order_by(WorkroomRun.created_at.desc())
            )
        ).scalars().all()
        events = (
            await session.execute(
                select(WorkroomEvent)
                .where(WorkroomEvent.workroom_id == room_id)
                .order_by(WorkroomEvent.id.desc())
                .limit(120)
            )
        ).scalars().all()
        creator = await session.get(User, room.created_by_user_id)
        members = (
            await session.execute(
                select(WorkroomMember)
                .where(
                    WorkroomMember.workroom_id == room_id,
                    WorkroomMember.status == "active",
                )
                .order_by(WorkroomMember.created_at)
            )
        ).scalars().all()
        member_dicts = []
        for member in members:
            member_user = await session.get(User, member.user_id)
            member_dicts.append(member_dict(member, member_user))
        return {
            **room_dict(room),
            "room_role": role,
            "creator": {
                "id": room.created_by_user_id,
                "name": creator.name if creator else "Team member",
            },
            "members": member_dicts,
            "tasks": [task_dict(task) for task in tasks],
            "runs": [run_dict(run) for run in runs],
            "events": [event_dict(event) for event in reversed(events)],
        }


async def get_room_record(org_id: str, room_id: str) -> Optional[Workroom]:
    async with async_session() as session:
        room = await session.get(Workroom, room_id)
        if room is None or room.org_id != org_id:
            return None
        return room


async def create_task(
    *,
    org_id: str,
    room_id: str,
    user_id: str,
    user_name: str,
    title: str,
    description: str,
    assignee_type: str,
    assignee_name: str,
) -> dict[str, Any]:
    now = datetime.utcnow()
    async with async_session() as session:
        room = await session.get(Workroom, room_id)
        if room is None or room.org_id != org_id:
            raise ValueError("Workroom not found")
        existing = (
            await session.execute(
                select(WorkroomTask).where(
                    WorkroomTask.workroom_id == room_id,
                    WorkroomTask.archived_at.is_(None),
                )
            )
        ).scalars().all()
        task = WorkroomTask(
            id=str(uuid4()),
            workroom_id=room_id,
            org_id=org_id,
            title=title[:180],
            description=description,
            status="todo",
            assignee_type=assignee_type,
            assignee_name=assignee_name[:120],
            position=len(existing),
            created_by_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        event = WorkroomEvent(
            workroom_id=room_id,
            org_id=org_id,
            actor_type="human",
            actor_name=user_name[:120],
            event_type="task_created",
            message=f"Added “{task.title}” to the shared plan.",
            payload={"task_id": task.id},
            created_at=now,
        )
        room.updated_at = now
        session.add_all([task, event])
        await session.commit()
        return task_dict(task)


async def create_run(
    *,
    org_id: str,
    room_id: str,
    task_id: Optional[str],
    user_id: str,
    instruction: str,
    redirected_from_run_id: Optional[str] = None,
) -> dict[str, Any]:
    now = datetime.utcnow()
    run = WorkroomRun(
        id=str(uuid4()),
        workroom_id=room_id,
        task_id=task_id,
        org_id=org_id,
        agent_name="Komponist Analyst",
        instruction=instruction,
        status="queued",
        current_step="queued",
        context_snapshot={},
        result={},
        redirected_from_run_id=redirected_from_run_id,
        created_by_user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    async with async_session() as session:
        room = await session.get(Workroom, room_id)
        if room is None or room.org_id != org_id:
            raise ValueError("Workroom not found")
        if task_id:
            task = await session.get(WorkroomTask, task_id)
            if task is None or task.workroom_id != room_id:
                raise ValueError("Task not found")
            task.status = "in_progress"
            task.updated_at = now
        room.updated_at = now
        session.add(run)
        await session.commit()
        return run_dict(run)


async def get_task(org_id: str, task_id: str) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        task = await session.get(WorkroomTask, task_id)
        if task is None or task.org_id != org_id or task.archived_at is not None:
            return None
        return task_dict(task)


async def get_run(org_id: str, run_id: str) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        run = await session.get(WorkroomRun, run_id)
        if run is None or run.org_id != org_id:
            return None
        return run_dict(run)


async def update_run(
    org_id: str,
    run_id: str,
    *,
    status: Optional[str] = None,
    current_step: Optional[str] = None,
    context_snapshot: Optional[dict[str, Any]] = None,
    result: Optional[dict[str, Any]] = None,
    approved_by_user_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        run = await session.get(WorkroomRun, run_id)
        if run is None or run.org_id != org_id:
            return None
        if status is not None:
            run.status = status
        if current_step is not None:
            run.current_step = current_step
        if context_snapshot is not None:
            run.context_snapshot = context_snapshot
        if result is not None:
            run.result = result
        if approved_by_user_id is not None:
            run.approved_by_user_id = approved_by_user_id
        run.updated_at = datetime.utcnow()
        await session.commit()
        return run_dict(run)


async def transition_run(
    org_id: str,
    run_id: str,
    *,
    from_statuses: list[str],
    status: str,
    current_step: str,
    context_snapshot: Optional[dict[str, Any]] = None,
    result: Optional[dict[str, Any]] = None,
    approved_by_user_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Atomically claim a run transition so concurrent controls cannot duplicate work."""
    values: dict[str, Any] = {
        "status": status,
        "current_step": current_step,
        "updated_at": datetime.utcnow(),
    }
    if context_snapshot is not None:
        values["context_snapshot"] = context_snapshot
    if result is not None:
        values["result"] = result
    if approved_by_user_id is not None:
        values["approved_by_user_id"] = approved_by_user_id

    async with async_session() as session:
        transition = await session.execute(
            sql_update(WorkroomRun)
            .where(
                WorkroomRun.id == run_id,
                WorkroomRun.org_id == org_id,
                WorkroomRun.status.in_(from_statuses),
            )
            .values(**values)
        )
        if transition.rowcount != 1:
            await session.rollback()
            return None
        await session.commit()
        run = await session.get(WorkroomRun, run_id)
        return run_dict(run) if run is not None else None


async def update_task(
    org_id: str,
    task_id: str,
    *,
    status: Optional[str] = None,
    artifact_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        task = await session.get(WorkroomTask, task_id)
        if task is None or task.org_id != org_id:
            return None
        if status is not None:
            task.status = status
        if artifact_id is not None:
            task.artifact_id = artifact_id
        task.updated_at = datetime.utcnow()
        await session.commit()
        return task_dict(task)


async def edit_task(
    org_id: str,
    room_id: str,
    task_id: str,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    assignee_type: Optional[str] = None,
    assignee_user_id: Optional[str] = None,
    assignee_name: Optional[str] = None,
    requires_approval: Optional[bool] = None,
    depends_on: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    """Apply a human edit to one task, keeping dependencies inside the room."""
    async with async_session() as session:
        task = await session.get(WorkroomTask, task_id)
        if task is None or task.org_id != org_id or task.workroom_id != room_id:
            return None
        if title is not None:
            task.title = title[:180]
        if description is not None:
            task.description = description
        if status is not None:
            task.status = status
        if assignee_type is not None:
            task.assignee_type = assignee_type
            if assignee_type == "agent":
                task.assignee_user_id = None
                task.assignee_name = "Komponist Analyst"
        if assignee_user_id is not None:
            task.assignee_user_id = assignee_user_id or None
        if assignee_name is not None:
            task.assignee_name = assignee_name[:120]
        if requires_approval is not None:
            task.requires_approval = requires_approval
        if depends_on is not None:
            # A dependency may only reference another live task in this room,
            # and never the task itself.
            siblings = {
                row.id
                for row in (
                    await session.execute(
                        select(WorkroomTask).where(
                            WorkroomTask.workroom_id == room_id,
                            WorkroomTask.archived_at.is_(None),
                        )
                    )
                ).scalars().all()
            }
            task.depends_on = [
                dependency
                for dependency in dict.fromkeys(depends_on)
                if dependency in siblings and dependency != task_id
            ]
        task.updated_at = datetime.utcnow()
        await session.commit()
        return task_dict(task)


async def archive_task(
    org_id: str, room_id: str, task_id: str
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        task = await session.get(WorkroomTask, task_id)
        if task is None or task.org_id != org_id or task.workroom_id != room_id:
            return None
        task.archived_at = datetime.utcnow()
        task.updated_at = task.archived_at
        await session.commit()
        return task_dict(task)


async def reorder_tasks(
    org_id: str, room_id: str, task_ids: list[str]
) -> Optional[list[dict[str, Any]]]:
    """Apply an explicit order. Tasks left out keep their relative order after."""
    async with async_session() as session:
        tasks = (
            await session.execute(
                select(WorkroomTask)
                .where(
                    WorkroomTask.org_id == org_id,
                    WorkroomTask.workroom_id == room_id,
                    WorkroomTask.archived_at.is_(None),
                )
                .order_by(WorkroomTask.position, WorkroomTask.created_at)
            )
        ).scalars().all()
        if not tasks:
            return None
        by_id = {task.id: task for task in tasks}
        ordered = [by_id[task_id] for task_id in task_ids if task_id in by_id]
        ordered += [task for task in tasks if task.id not in set(task_ids)]
        now = datetime.utcnow()
        for position, task in enumerate(ordered):
            task.position = position
            task.updated_at = now
        await session.commit()
        return [task_dict(task) for task in ordered]


async def list_runs_for_task(org_id: str, task_id: str) -> list[dict[str, Any]]:
    """Every attempt made for one task, newest first, including redirects."""
    async with async_session() as session:
        runs = (
            await session.execute(
                select(WorkroomRun)
                .where(WorkroomRun.org_id == org_id, WorkroomRun.task_id == task_id)
                .order_by(WorkroomRun.created_at.desc())
            )
        ).scalars().all()
        return [run_dict(run) for run in runs]


async def append_event(
    *,
    org_id: str,
    room_id: str,
    actor_type: str,
    actor_name: str,
    event_type: str,
    message: str,
    run_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    event = WorkroomEvent(
        workroom_id=room_id,
        run_id=run_id,
        org_id=org_id,
        actor_type=actor_type,
        actor_name=actor_name[:120],
        event_type=event_type,
        message=message,
        payload=payload or {},
        created_at=datetime.utcnow(),
    )
    async with async_session() as session:
        room = await session.get(Workroom, room_id)
        if room:
            room.updated_at = datetime.utcnow()
        session.add(event)
        await session.commit()
        return event_dict(event)


async def list_events_after(
    org_id: str, room_id: str, after_id: int
) -> list[dict[str, Any]]:
    async with async_session() as session:
        events = (
            await session.execute(
                select(WorkroomEvent)
                .where(
                    WorkroomEvent.org_id == org_id,
                    WorkroomEvent.workroom_id == room_id,
                    WorkroomEvent.id > after_id,
                )
                .order_by(WorkroomEvent.id)
                .limit(100)
            )
        ).scalars().all()
        return [event_dict(event) for event in events]
