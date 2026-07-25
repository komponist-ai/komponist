"""A durable, Postgres-owned job queue for Workroom agent work.

Postgres is the only coordination point, which keeps the Coolify deployment to
one database instead of adding Redis. Delivery is at-least-once with
idempotent handlers:

* ``enqueue`` deduplicates on ``idempotency_key`` so a retried request, a
  double-clicked button, or a replayed webhook produces exactly one job.
* ``claim`` uses ``FOR UPDATE SKIP LOCKED`` so concurrent workers never take
  the same row and never block one another.
* A claim grants a time-boxed lease. The worker renews it with ``heartbeat``;
  if the worker dies, ``recover_expired_leases`` returns the job to the queue.
* Failures back off with bounded exponential delay until ``max_attempts``.
"""

import os
import socket
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import func, select, update as sql_update
from sqlalchemy.exc import IntegrityError

from database import WorkroomJob, WorkroomWorker, async_session


# A lease must outlive the slowest safe step (an external model call) but stay
# short enough that a crashed worker's job is retried promptly.
LEASE_SECONDS = int(os.getenv("KOMPONIST_WORKROOM_LEASE_SECONDS", "120"))
HEARTBEAT_SECONDS = int(os.getenv("KOMPONIST_WORKROOM_HEARTBEAT_SECONDS", "20"))
MAX_ATTEMPTS = int(os.getenv("KOMPONIST_WORKROOM_MAX_ATTEMPTS", "3"))
BASE_RETRY_SECONDS = int(os.getenv("KOMPONIST_WORKROOM_RETRY_SECONDS", "5"))
MAX_RETRY_SECONDS = int(os.getenv("KOMPONIST_WORKROOM_MAX_RETRY_SECONDS", "300"))
# A worker is considered offline once it misses several heartbeats.
WORKER_STALE_SECONDS = int(os.getenv("KOMPONIST_WORKROOM_WORKER_STALE_SECONDS", "90"))


def default_worker_id() -> str:
    """Return an ID shared by the worker process and its health probe.

    A container hostname is unique per replica, while an explicit environment
    value lets operators provide a stable name when desired. Keeping this
    deterministic allows a separate Docker healthcheck process to inspect the
    heartbeat of the exact worker running in the same container.
    """
    return os.getenv("KOMPONIST_WORKER_ID") or socket.gethostname()[:200]


def job_dict(job: WorkroomJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "org_id": job.org_id,
        "workroom_id": job.workroom_id,
        "run_id": job.run_id,
        "job_type": job.job_type,
        "status": job.status,
        "idempotency_key": job.idempotency_key,
        "payload": job.payload or {},
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "available_at": f"{job.available_at.isoformat()}Z",
        "lease_owner": job.lease_owner,
        "lease_expires_at": (
            f"{job.lease_expires_at.isoformat()}Z" if job.lease_expires_at else None
        ),
        "last_heartbeat_at": (
            f"{job.last_heartbeat_at.isoformat()}Z" if job.last_heartbeat_at else None
        ),
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": f"{job.created_at.isoformat()}Z",
        "updated_at": f"{job.updated_at.isoformat()}Z",
        "completed_at": (
            f"{job.completed_at.isoformat()}Z" if job.completed_at else None
        ),
    }


def retry_delay_seconds(attempt_count: int) -> int:
    """Bounded exponential backoff: 5s, 10s, 20s, ... capped."""
    delay = BASE_RETRY_SECONDS * (2 ** max(0, attempt_count - 1))
    return int(min(delay, MAX_RETRY_SECONDS))


async def enqueue(
    *,
    org_id: str,
    workroom_id: str,
    job_type: str,
    idempotency_key: str,
    run_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    available_in_seconds: int = 0,
    max_attempts: int = MAX_ATTEMPTS,
) -> dict[str, Any]:
    """Persist one job, returning the existing job when the key repeats."""
    now = datetime.utcnow()
    job = WorkroomJob(
        id=str(uuid4()),
        org_id=org_id,
        workroom_id=workroom_id,
        run_id=run_id,
        job_type=job_type,
        status="queued",
        idempotency_key=idempotency_key[:200],
        payload=payload or {},
        attempt_count=0,
        max_attempts=max_attempts,
        available_at=now + timedelta(seconds=available_in_seconds),
        created_at=now,
        updated_at=now,
    )
    async with async_session() as session:
        session.add(job)
        try:
            await session.commit()
        except IntegrityError:
            # The unique idempotency key already claimed this unit of work.
            await session.rollback()
            existing = (
                await session.execute(
                    select(WorkroomJob).where(
                        WorkroomJob.idempotency_key == idempotency_key[:200]
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                raise
            return job_dict(existing)
    return job_dict(job)


async def claim(
    lease_owner: str,
    *,
    lease_seconds: int = LEASE_SECONDS,
    job_types: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    """Atomically take one ready job. Returns ``None`` when the queue is idle.

    ``job_types`` restricts the claim to handlers this process understands, so
    an older worker never swallows a job type introduced by a newer release.
    """
    now = datetime.utcnow()
    conditions = [
        WorkroomJob.status == "queued",
        WorkroomJob.available_at <= now,
    ]
    if job_types is not None:
        conditions.append(WorkroomJob.job_type.in_(job_types))

    async with async_session() as session:
        async with session.begin():
            candidate = (
                await session.execute(
                    select(WorkroomJob)
                    .where(*conditions)
                    .order_by(WorkroomJob.available_at, WorkroomJob.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if candidate is None:
                return None
            candidate.status = "running"
            candidate.attempt_count += 1
            candidate.lease_owner = lease_owner
            candidate.lease_expires_at = now + timedelta(seconds=lease_seconds)
            candidate.last_heartbeat_at = now
            candidate.updated_at = now
            claimed = job_dict(candidate)
    return claimed


async def heartbeat(
    job_id: str, lease_owner: str, *, lease_seconds: int = LEASE_SECONDS
) -> bool:
    """Renew a lease. ``False`` means the lease was lost and work must stop."""
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            sql_update(WorkroomJob)
            .where(
                WorkroomJob.id == job_id,
                WorkroomJob.lease_owner == lease_owner,
                WorkroomJob.status == "running",
            )
            .values(
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                last_heartbeat_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        return result.rowcount == 1


async def complete(job_id: str, lease_owner: str) -> bool:
    """Mark a job done. Idempotent: a second call simply reports ``False``."""
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            sql_update(WorkroomJob)
            .where(
                WorkroomJob.id == job_id,
                WorkroomJob.lease_owner == lease_owner,
                WorkroomJob.status == "running",
            )
            .values(
                status="completed",
                completed_at=now,
                updated_at=now,
                lease_owner=None,
                lease_expires_at=None,
                error_code=None,
                error_message=None,
            )
        )
        await session.commit()
        return result.rowcount == 1


async def release(job_id: str, lease_owner: str, *, reason: str = "paused") -> bool:
    """Hand a claimed job back without consuming an attempt.

    Used when a human pauses or cancels between safe steps, so resuming does
    not count against the retry budget.
    """
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            sql_update(WorkroomJob)
            .where(
                WorkroomJob.id == job_id,
                WorkroomJob.lease_owner == lease_owner,
                WorkroomJob.status == "running",
            )
            .values(
                status="cancelled",
                completed_at=now,
                updated_at=now,
                lease_owner=None,
                lease_expires_at=None,
                error_code=reason,
            )
        )
        await session.commit()
        return result.rowcount == 1


async def fail(
    job_id: str,
    lease_owner: str,
    *,
    error_code: str,
    error_message: str,
    retryable: bool = True,
) -> dict[str, Any]:
    """Record a failure, then either schedule a retry or exhaust the job."""
    now = datetime.utcnow()
    async with async_session() as session:
        job = await session.get(WorkroomJob, job_id)
        if job is None or job.lease_owner != lease_owner or job.status != "running":
            return {"status": "lost", "will_retry": False}
        exhausted = not retryable or job.attempt_count >= job.max_attempts
        job.error_code = error_code[:60]
        job.error_message = error_message[:2000]
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = now
        if exhausted:
            job.status = "failed"
            job.completed_at = now
        else:
            job.status = "queued"
            job.available_at = now + timedelta(
                seconds=retry_delay_seconds(job.attempt_count)
            )
        state = {
            "status": job.status,
            "will_retry": not exhausted,
            "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts,
        }
        await session.commit()
    return state


async def recover_expired_leases() -> int:
    """Requeue jobs whose worker died mid-flight.

    A job that has already used its attempt budget is failed instead of
    looping forever.
    """
    now = datetime.utcnow()
    async with async_session() as session:
        expired = (
            await session.execute(
                select(WorkroomJob).where(
                    WorkroomJob.status == "running",
                    WorkroomJob.lease_expires_at.is_not(None),
                    WorkroomJob.lease_expires_at < now,
                )
            )
        ).scalars().all()
        for job in expired:
            job.lease_owner = None
            job.lease_expires_at = None
            job.updated_at = now
            job.error_code = "lease_expired"
            job.error_message = "The worker holding this job stopped responding."
            if job.attempt_count >= job.max_attempts:
                job.status = "failed"
                job.completed_at = now
            else:
                job.status = "queued"
                job.available_at = now + timedelta(
                    seconds=retry_delay_seconds(job.attempt_count)
                )
        await session.commit()
        return len(expired)


async def cancel_jobs_for_run(run_id: str, *, reason: str = "cancelled") -> int:
    """Stop queued work for a run. Running jobs stop at their next safe step."""
    now = datetime.utcnow()
    async with async_session() as session:
        result = await session.execute(
            sql_update(WorkroomJob)
            .where(WorkroomJob.run_id == run_id, WorkroomJob.status == "queued")
            .values(
                status="cancelled",
                completed_at=now,
                updated_at=now,
                error_code=reason,
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        await session.commit()
        return result.rowcount


async def count_jobs_for_run(run_id: str, job_type: str) -> int:
    """How many times this kind of work has been enqueued for a run.

    Used as an attempt epoch in idempotency keys so resuming or retrying a run
    creates genuinely new work, while two concurrent resume clicks still
    collapse to one job.
    """
    async with async_session() as session:
        return int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(WorkroomJob)
                    .where(
                        WorkroomJob.run_id == run_id,
                        WorkroomJob.job_type == job_type,
                    )
                )
            ).scalar_one()
        )


async def get_job(job_id: str) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        job = await session.get(WorkroomJob, job_id)
        return job_dict(job) if job else None


async def register_worker(worker_id: str) -> None:
    async with async_session() as session:
        worker = await session.get(WorkroomWorker, worker_id)
        now = datetime.utcnow()
        if worker is None:
            session.add(
                WorkroomWorker(
                    id=worker_id,
                    hostname=socket.gethostname()[:200],
                    started_at=now,
                    last_heartbeat_at=now,
                    claimed_total=0,
                )
            )
        else:
            worker.last_heartbeat_at = now
        await session.commit()


async def worker_heartbeat(worker_id: str, *, claimed: int = 0) -> None:
    async with async_session() as session:
        worker = await session.get(WorkroomWorker, worker_id)
        if worker is None:
            await session.rollback()
            await register_worker(worker_id)
            return
        worker.last_heartbeat_at = datetime.utcnow()
        worker.claimed_total += claimed
        await session.commit()


async def worker_is_healthy(
    worker_id: str,
    *,
    stale_seconds: int = WORKER_STALE_SECONDS,
) -> bool:
    """Check whether one specific worker has sent a recent heartbeat."""
    stale_before = datetime.utcnow() - timedelta(seconds=stale_seconds)
    async with async_session() as session:
        live_worker = (
            await session.execute(
                select(func.count())
                .select_from(WorkroomWorker)
                .where(
                    WorkroomWorker.id == worker_id,
                    WorkroomWorker.last_heartbeat_at >= stale_before,
                )
            )
        ).scalar_one()
    return bool(live_worker)


async def queue_health() -> dict[str, Any]:
    """Queue depth and worker liveness for the health endpoint and the UI."""
    now = datetime.utcnow()
    stale_before = now - timedelta(seconds=WORKER_STALE_SECONDS)
    async with async_session() as session:
        counts = dict(
            (
                await session.execute(
                    select(WorkroomJob.status, func.count()).group_by(
                        WorkroomJob.status
                    )
                )
            ).all()
        )
        live_workers = (
            await session.execute(
                select(func.count()).select_from(WorkroomWorker).where(
                    WorkroomWorker.last_heartbeat_at >= stale_before
                )
            )
        ).scalar_one()
        last_heartbeat = (
            await session.execute(select(func.max(WorkroomWorker.last_heartbeat_at)))
        ).scalar_one()
        oldest_queued = (
            await session.execute(
                select(func.min(WorkroomJob.available_at)).where(
                    WorkroomJob.status == "queued"
                )
            )
        ).scalar_one()

    return {
        # Report "idle" rather than "healthy" when nothing has ever been
        # queued, so an unstarted worker is not mistaken for a working one.
        "status": "healthy" if live_workers else (
            "idle" if not counts.get("queued") else "degraded"
        ),
        "workers_online": int(live_workers),
        "queued": int(counts.get("queued", 0)),
        "running": int(counts.get("running", 0)),
        "failed": int(counts.get("failed", 0)),
        "completed": int(counts.get("completed", 0)),
        "cancelled": int(counts.get("cancelled", 0)),
        "last_worker_heartbeat_at": (
            f"{last_heartbeat.isoformat()}Z" if last_heartbeat else None
        ),
        "oldest_queued_at": (
            f"{oldest_queued.isoformat()}Z" if oldest_queued else None
        ),
    }
