"""Persistence primitives for shared human-and-agent Workrooms."""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select, update as sql_update

from database import (
    User,
    Workroom,
    WorkroomEvent,
    WorkroomRun,
    WorkroomTask,
    async_session,
)


def room_visible(
    room: Workroom, department_ids: list[str], access_all: bool
) -> bool:
    required = set(room.department_ids or [])
    return access_all or required.issubset(set(department_ids))


def room_dict(room: Workroom) -> dict[str, Any]:
    return {
        "id": room.id,
        "title": room.title,
        "objective": room.objective,
        "status": room.status,
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
        "position": task.position,
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


async def create_room(
    *,
    org_id: str,
    user_id: str,
    user_name: str,
    title: str,
    objective: str,
    department_ids: list[str],
) -> dict[str, Any]:
    now = datetime.utcnow()
    room = Workroom(
        id=str(uuid4()),
        org_id=org_id,
        title=title[:160],
        objective=objective,
        status="active",
        department_ids=department_ids,
        created_by_user_id=user_id,
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
        session.add_all([room, task, event])
        await session.commit()
    return {**room_dict(room), "tasks": [task_dict(task)], "runs": [], "events": [event_dict(event)]}


async def list_rooms(
    org_id: str, department_ids: list[str], access_all: bool
) -> list[dict[str, Any]]:
    async with async_session() as session:
        rooms = (
            await session.execute(
                select(Workroom)
                .where(Workroom.org_id == org_id)
                .order_by(Workroom.updated_at.desc())
            )
        ).scalars().all()
        visible = [room for room in rooms if room_visible(room, department_ids, access_all)]
        result: list[dict[str, Any]] = []
        for room in visible:
            tasks = (
                await session.execute(
                    select(WorkroomTask).where(WorkroomTask.workroom_id == room.id)
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
            result.append({
                **room_dict(room),
                "creator": {
                    "id": room.created_by_user_id,
                    "name": creator.name if creator else "Team member",
                },
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
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        room = await session.get(Workroom, room_id)
        if room is None or room.org_id != org_id or not room_visible(
            room, department_ids, access_all
        ):
            return None
        tasks = (
            await session.execute(
                select(WorkroomTask)
                .where(WorkroomTask.workroom_id == room_id)
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
        return {
            **room_dict(room),
            "creator": {
                "id": room.created_by_user_id,
                "name": creator.name if creator else "Team member",
            },
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
                select(WorkroomTask).where(WorkroomTask.workroom_id == room_id)
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
