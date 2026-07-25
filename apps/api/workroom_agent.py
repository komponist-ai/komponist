"""The Workroom run state machine and the durable job handlers behind it.

This module is imported by both the API (for the state machine and its
vocabulary) and the worker process (which actually executes the work). The API
only ever enqueues; nothing here runs inside a request.

Honest pause semantics
----------------------
An in-flight call to an external model provider cannot be interrupted. "Pause"
therefore means *pause after the current safe step*: a human request moves the
run to ``pause_requested``, and the worker settles it to ``paused`` at the next
boundary between steps, preserving whatever context has been gathered so far.
The same is true for cancellation.
"""

import asyncio
import os
from typing import Any, Callable, Optional

import workroom_queue as queue
from artifacts import source_deep_link_path
from workroom_context import (
    apply_context_pack,
    build_context_snapshot,
    list_context_items,
)
from workroom_artifacts import share_artifact
from workroom_messages import create_message
from workrooms import (
    append_event,
    get_room_record,
    get_run,
    transition_run,
    update_run,
    update_task,
)


AGENT_NAME = "Komponist Analyst"

# Every state a run can occupy. Anything else is a bug, not a new feature.
RUN_STATES = {
    "queued",
    "running",
    "pause_requested",
    "paused",
    "cancel_requested",
    "cancelled",
    "awaiting_approval",
    "completed",
    "failed",
    "redirected",
}

TERMINAL_STATES = {"completed", "cancelled", "failed", "redirected"}

# A run may only move along these edges. Transitions are applied with an
# atomic conditional UPDATE, so a stale client loses the race and gets a 409.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {
        "running", "pause_requested", "paused", "cancel_requested",
        "cancelled", "redirected", "failed",
    },
    "running": {
        "awaiting_approval", "pause_requested", "paused", "cancel_requested",
        "cancelled", "completed", "failed", "redirected",
    },
    "pause_requested": {
        "paused", "running", "cancel_requested", "cancelled",
        "awaiting_approval", "completed", "failed", "redirected",
    },
    "paused": {
        "queued", "running", "awaiting_approval", "cancel_requested",
        "cancelled", "redirected", "failed",
    },
    "cancel_requested": {"cancelled", "completed", "failed", "redirected"},
    "awaiting_approval": {
        "running", "pause_requested", "paused", "cancel_requested",
        "cancelled", "redirected", "failed",
    },
    "failed": {"queued", "running", "cancelled", "redirected"},
    "completed": set(),
    "cancelled": set(),
    "redirected": set(),
}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


async def _say(
    org_id: str,
    room_id: str,
    body: str,
    references: Optional[list[dict[str, str]]] = None,
) -> None:
    """Let the agent speak in the shared conversation, not only in the log."""
    await create_message(
        org_id=org_id,
        room_id=room_id,
        author_type="agent",
        author_user_id=None,
        author_name=AGENT_NAME,
        body=body,
        reply_to_message_id=None,
        references=references or [],
        mentions=[],
    )


async def _control_signal(org_id: str, run_id: str) -> Optional[str]:
    """Read the human control requested for this run, if any."""
    run = await get_run(org_id, run_id)
    if run is None:
        return "gone"
    if run["status"] in {"cancel_requested", "cancelled"}:
        return "cancel"
    if run["status"] in {"pause_requested", "paused"}:
        return "pause"
    if run["status"] in TERMINAL_STATES:
        return "gone"
    return None


async def _settle_control(
    org_id: str, room_id: str, run_id: str, signal: str, *, step: str,
    context_snapshot: Optional[dict] = None, result: Optional[dict] = None,
) -> None:
    """Honour a pause or cancel at a safe boundary, preserving gathered work."""
    # Only settle from the explicitly requested state. If a human withdrew the
    # request while the current step ran, the run is back to "running" and the
    # worker must carry on rather than stop on a stale signal.
    if signal == "cancel":
        settled = await transition_run(
            org_id,
            run_id,
            from_statuses=["cancel_requested"],
            status="cancelled",
            current_step="cancelled",
            context_snapshot=context_snapshot,
            result=result,
        )
        if settled:
            await append_event(
                org_id=org_id,
                room_id=room_id,
                run_id=run_id,
                actor_type="agent",
                actor_name=AGENT_NAME,
                event_type="run_cancelled",
                message="Stopped at a safe step because cancellation was requested.",
            )
        return

    settled = await transition_run(
        org_id,
        run_id,
        from_statuses=["pause_requested"],
        status="paused",
        current_step=step,
        context_snapshot=context_snapshot,
        result=result,
    )
    if settled:
        await append_event(
            org_id=org_id,
            room_id=room_id,
            run_id=run_id,
            actor_type="agent",
            actor_name=AGENT_NAME,
            event_type="run_paused",
            message="Paused at a safe step. Any work completed so far is kept.",
        )


async def handle_research(job: dict[str, Any], keep_lease: Callable[[], bool]) -> None:
    """Gather confirmed, cited context for a run and request human approval."""
    import main  # Imported lazily: main imports the queue, not the handlers.

    org_id = job["org_id"]
    run_id = job["run_id"]
    if not run_id:
        return
    run = await get_run(org_id, run_id)
    if run is None or run["status"] in TERMINAL_STATES:
        return  # Nothing to do; completing the job stays idempotent.
    room = await get_room_record(org_id, run["workroom_id"])
    if room is None:
        return

    signal = await _control_signal(org_id, run_id)
    if signal == "gone":
        return
    if signal:
        await _settle_control(org_id, room.id, run_id, signal, step="paused_before_start")
        return

    claimed = await transition_run(
        org_id,
        run_id,
        from_statuses=["queued"],
        status="running",
        current_step="searching_company_brain",
    )
    if claimed is None:
        return  # Another worker or a human already moved this run.
    run = claimed

    await append_event(
        org_id=org_id,
        room_id=room.id,
        run_id=run_id,
        actor_type="agent",
        actor_name=run["agent_name"],
        event_type="agent_started",
        message="Started researching confirmed company context.",
    )

    # The agent sees the room's scope, never the starting user's wider access.
    scoped_user = {
        "id": job["payload"].get("user_id"),
        "name": job["payload"].get("user_name", "Team member"),
        "access_all_departments": False,
        "department_ids": room.department_ids or [],
    }
    topic = " ".join(
        value for value in [room.objective, run["instruction"]] if value
    )

    entities, sources = await main._artifact_context(org_id, scoped_user, topic)
    for source in sources:
        source["komponist_path"] = source_deep_link_path(org_id, source["id"])

    # Retrieval above is already permission-scoped; the context pack only
    # narrows and reorders it, so it can never widen what the agent reads.
    context_items = await list_context_items(org_id, room.id)
    entities, sources, applied_pack = apply_context_pack(
        entities, sources, context_items
    )

    if not entities or not sources:
        failed = await transition_run(
            org_id,
            run_id,
            from_statuses=["running", "pause_requested", "cancel_requested"],
            status="failed",
            current_step="insufficient_context",
            result={
                "summary": (
                    "No confirmed, cited knowledge was available in this "
                    "Workroom's permission scope."
                ),
                "finding_count": 0,
                "source_count": 0,
            },
        )
        if failed is None:
            return
        if run.get("task_id"):
            await update_task(org_id, run["task_id"], status="todo")
        await append_event(
            org_id=org_id,
            room_id=room.id,
            run_id=run_id,
            actor_type="agent",
            actor_name=run["agent_name"],
            event_type="run_failed",
            message=(
                "Could not find confirmed, cited knowledge in the room scope. "
                "Review source facts or change the direction."
            ),
        )
        return

    snapshot = build_context_snapshot(
        entities=entities,
        sources=sources,
        room=room,
        applied=applied_pack,
        scope={
            "visibility": room.visibility or "organization",
            "department_ids": room.department_ids or [],
            "access_all_departments": False,
        },
    )
    findings = snapshot["findings"]
    snapshot_sources = snapshot["sources"]
    lead_findings = [
        finding["statement"] for finding in findings if finding["statement"]
    ][:3]
    summary = (
        f"Found {len(entities)} confirmed facts across {len(sources)} cited "
        "source passages."
    )
    if lead_findings:
        summary += " Key evidence: " + " ".join(lead_findings)

    result = {
        "summary": summary,
        "finding_count": len(entities),
        "source_count": len(sources),
        "suggested_output": "briefing",
    }

    # Safe boundary: the external retrieval finished, so a pause or cancel
    # requested during it can now be honoured without losing the findings.
    signal = await _control_signal(org_id, run_id)
    if signal == "gone":
        return
    if signal:
        await _settle_control(
            org_id, room.id, run_id, signal,
            step="paused_after_research",
            context_snapshot=snapshot,
            result=result,
        )
        return
    if not keep_lease():
        # The lease expired; another worker will redo this attempt cleanly.
        raise RuntimeError("Lost the job lease during research")

    ready = await transition_run(
        org_id,
        run_id,
        from_statuses=["running"],
        status="awaiting_approval",
        current_step="approval_required",
        context_snapshot=snapshot,
        result=result,
    )
    if ready is None:
        return

    await append_event(
        org_id=org_id,
        room_id=room.id,
        run_id=run_id,
        actor_type="agent",
        actor_name=run["agent_name"],
        event_type="research_completed",
        message=(
            f"Found {len(entities)} confirmed facts from {len(sources)} "
            "source passages."
        ),
        payload={"sources": snapshot_sources[:6]},
    )
    await append_event(
        org_id=org_id,
        room_id=room.id,
        run_id=run_id,
        actor_type="agent",
        actor_name=run["agent_name"],
        event_type="approval_required",
        message="Ready to create a cited briefing in Compose. Approval required.",
    )
    await _say(
        org_id,
        room.id,
        (
            f"I found {len(entities)} confirmed facts across {len(sources)} cited "
            "passages for this objective. I need approval before turning them "
            "into a shared briefing."
        ),
        references=[{"kind": "run", "id": run_id, "label": "Research attempt"}],
    )


async def handle_finalize(job: dict[str, Any], keep_lease: Callable[[], bool]) -> None:
    """Create the approved Compose deliverable exactly once."""
    import main

    org_id = job["org_id"]
    run_id = job["run_id"]
    if not run_id:
        return
    run = await get_run(org_id, run_id)
    if run is None:
        return
    room = await get_room_record(org_id, run["workroom_id"])
    if room is None:
        return

    # At-least-once delivery means this job can arrive twice. One approved run
    # yields one deliverable, so an existing artifact ends the job quietly.
    existing_artifact = (run.get("result") or {}).get("artifact_id")
    if existing_artifact:
        return
    if run["status"] in TERMINAL_STATES:
        return

    await append_event(
        org_id=org_id,
        room_id=room.id,
        run_id=run_id,
        actor_type="agent",
        actor_name=run["agent_name"],
        event_type="compose_started",
        message="Approval received. Creating the grounded briefing in Compose.",
    )

    scoped_user = {
        "id": job["payload"].get("user_id"),
        "name": job["payload"].get("user_name", "Team member"),
        "access_all_departments": False,
        "department_ids": room.department_ids or [],
    }
    artifact = await main._create_grounded_artifact(
        org_id=org_id,
        user=scoped_user,
        artifact_type="briefing",
        topic=room.objective,
        audience="Project team",
        instructions=(
            f"Workroom direction: {run['instruction']}. "
            "Produce an action-oriented handoff brief with open questions, "
            "constraints, decisions, and next steps only when supported."
        ),
        language="english",
    )
    # Link before recording the result: the deliverable is the room's, not
    # the approving user's private copy. share_artifact is idempotent, so an
    # at-least-once retry cannot create a second link.
    await share_artifact(
        org_id=org_id,
        room_id=room.id,
        artifact_id=artifact["id"],
        task_id=run.get("task_id"),
        run_id=run_id,
        created_by_user_id=run["created_by_user_id"],
        approved_by_user_id=run.get("approved_by_user_id"),
    )
    result = {
        **(run.get("result") or {}),
        "artifact_id": artifact["id"],
        "artifact_title": artifact["title"],
        "compose_path": f"/create?artifact={artifact['id']}",
        "shared_with_workroom": True,
    }
    # Record the task outcome *before* the run reports completed. "Completed"
    # is what watchers poll on, so it must not become visible while the task
    # it finished still looks in progress.
    if run.get("task_id"):
        await update_task(
            org_id,
            run["task_id"],
            status="completed",
            artifact_id=artifact["id"],
        )
    await update_run(
        org_id,
        run_id,
        status="completed",
        current_step="completed",
        result=result,
    )
    await append_event(
        org_id=org_id,
        room_id=room.id,
        run_id=run_id,
        actor_type="agent",
        actor_name=run["agent_name"],
        event_type="artifact_created",
        message=f"Created “{artifact['title']}” and handed it to Compose.",
        payload={
            "artifact_id": artifact["id"],
            "artifact_title": artifact["title"],
            "compose_path": f"/create?artifact={artifact['id']}",
        },
    )
    await _say(
        org_id,
        room.id,
        f"“{artifact['title']}” is ready and shared with this Workroom.",
        references=[
            {
                "kind": "artifact",
                "id": artifact["id"],
                "label": artifact["title"][:200],
            }
        ],
    )


HANDLERS: dict[str, Callable] = {
    "workroom.research": handle_research,
    "workroom.finalize": handle_finalize,
}


async def _mark_run_failed(job: dict[str, Any], error: Exception, will_retry: bool) -> None:
    """Surface an exhausted job as a failed run people can retry or redirect."""
    org_id = job["org_id"]
    run_id = job.get("run_id")
    if not run_id or will_retry:
        return
    run = await get_run(org_id, run_id)
    if run is None or run["status"] in TERMINAL_STATES:
        return
    failed = await transition_run(
        org_id,
        run_id,
        from_statuses=[
            "queued", "running", "pause_requested", "cancel_requested",
            "paused", "awaiting_approval",
        ],
        status="failed",
        current_step="failed",
        result={
            **(run.get("result") or {}),
            "summary": (run.get("result") or {}).get("summary")
            or "The agent run failed.",
            "error": str(error)[:500],
        },
    )
    if failed is None:
        return
    if run.get("task_id"):
        await update_task(org_id, run["task_id"], status="todo")
    await append_event(
        org_id=org_id,
        room_id=job["workroom_id"],
        run_id=run_id,
        actor_type="system",
        actor_name="Komponist",
        event_type="run_failed",
        message="The agent run failed. You can retry it or change its direction.",
    )


async def process_job(job: dict[str, Any], lease_owner: str) -> str:
    """Execute one claimed job, keeping its lease alive while it runs."""
    handler = HANDLERS.get(job["job_type"])
    if handler is None:
        await queue.fail(
            job["id"],
            lease_owner,
            error_code="unknown_job_type",
            error_message=f"No handler for {job['job_type']}",
            retryable=False,
        )
        return "failed"

    lease_held = True

    async def renew() -> None:
        nonlocal lease_held
        while lease_held:
            await asyncio.sleep(queue.HEARTBEAT_SECONDS)
            if not lease_held:
                return
            if not await queue.heartbeat(job["id"], lease_owner):
                lease_held = False
                return

    renewal = asyncio.create_task(renew())
    try:
        await handler(job, lambda: lease_held)
        await queue.complete(job["id"], lease_owner)
        return "completed"
    except Exception as error:  # noqa: BLE001 - the queue records every failure
        state = await queue.fail(
            job["id"],
            lease_owner,
            error_code=type(error).__name__,
            error_message=str(error),
        )
        await _mark_run_failed(job, error, bool(state.get("will_retry")))
        return "failed"
    finally:
        lease_held = False
        renewal.cancel()
        try:
            await renewal
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


async def run_worker_loop(
    *,
    worker_id: Optional[str] = None,
    stop_event: Optional[asyncio.Event] = None,
    poll_seconds: float = 1.0,
    max_jobs: Optional[int] = None,
) -> int:
    """Claim and process jobs until stopped.

    ``max_jobs`` bounds the loop for tests; production leaves it unset.
    """
    worker_id = worker_id or queue.default_worker_id()
    stop_event = stop_event or asyncio.Event()
    await queue.register_worker(worker_id)

    heartbeat_stop = asyncio.Event()

    async def maintain_liveness() -> None:
        """Keep worker liveness fresh even while one long job is running."""
        while not heartbeat_stop.is_set():
            await queue.worker_heartbeat(worker_id)
            try:
                await asyncio.wait_for(
                    heartbeat_stop.wait(),
                    timeout=queue.HEARTBEAT_SECONDS,
                )
            except asyncio.TimeoutError:
                pass

    liveness = asyncio.create_task(maintain_liveness())
    processed = 0
    idle_ticks = 0
    try:
        while not stop_event.is_set():
            if max_jobs is not None and processed >= max_jobs:
                break
            # Recover abandoned work roughly once per lease window.
            if idle_ticks % max(
                1,
                int(queue.HEARTBEAT_SECONDS / max(poll_seconds, 0.1)),
            ) == 0:
                await queue.recover_expired_leases()

            job = await queue.claim(worker_id, job_types=list(HANDLERS))
            if job is None:
                idle_ticks += 1
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
                except asyncio.TimeoutError:
                    pass
                continue

            idle_ticks = 0
            await process_job(job, worker_id)
            await queue.worker_heartbeat(worker_id, claimed=1)
            processed += 1
    finally:
        heartbeat_stop.set()
        try:
            await liveness
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    return processed


async def _enqueue_for_run(
    *,
    job_type: str,
    prefix: str,
    org_id: str,
    room_id: str,
    run_id: str,
    user_id: str,
    user_name: str,
) -> dict[str, Any]:
    # The epoch keeps a resumed or retried run from matching the idempotency
    # key of the job that already finished, while concurrent duplicate
    # requests still collapse onto one key.
    epoch = await queue.count_jobs_for_run(run_id, job_type) + 1
    return await queue.enqueue(
        org_id=org_id,
        workroom_id=room_id,
        run_id=run_id,
        job_type=job_type,
        idempotency_key=f"{prefix}:{run_id}:{epoch}",
        payload={"user_id": user_id, "user_name": user_name},
    )


async def enqueue_research(
    *, org_id: str, room_id: str, run_id: str, user_id: str, user_name: str
) -> dict[str, Any]:
    return await _enqueue_for_run(
        job_type="workroom.research",
        prefix="research",
        org_id=org_id,
        room_id=room_id,
        run_id=run_id,
        user_id=user_id,
        user_name=user_name,
    )


async def enqueue_finalize(
    *, org_id: str, room_id: str, run_id: str, user_id: str, user_name: str
) -> dict[str, Any]:
    return await _enqueue_for_run(
        job_type="workroom.finalize",
        prefix="finalize",
        org_id=org_id,
        room_id=room_id,
        run_id=run_id,
        user_id=user_id,
        user_name=user_name,
    )
