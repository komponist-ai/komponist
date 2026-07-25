"""Contract checks for the durable Workroom job queue.

These exercise the queue primitives directly against Postgres: single-claim
safety, idempotency, lease recovery, bounded retries, and restart survival.
The synthetic job type is deliberately one no worker handles, so a running
worker container never interferes with these assertions.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

from sqlalchemy import delete, select

import workroom_queue as queue
from database import WorkroomJob, WorkroomWorker, async_session, init_db


TEST_JOB_TYPE = "test.noop"
ORG_ID = f"queue-e2e-{uuid4().hex[:12]}"
ROOM_ID = f"room-{uuid4().hex[:12]}"

# A stable marker so a restart check can find its own seeded row again.
RESTART_KEY = "workroom-queue-e2e-restart"


async def cleanup(org_id: str = ORG_ID) -> None:
    async with async_session() as session:
        await session.execute(
            delete(WorkroomJob).where(WorkroomJob.job_type == TEST_JOB_TYPE)
        )
        await session.execute(
            delete(WorkroomWorker).where(WorkroomWorker.id.like("queue-e2e-%"))
        )
        await session.commit()


async def _enqueue(key: str, **overrides) -> dict:
    return await queue.enqueue(
        org_id=ORG_ID,
        workroom_id=ROOM_ID,
        job_type=TEST_JOB_TYPE,
        idempotency_key=key,
        **overrides,
    )


async def check_idempotent_enqueue() -> None:
    key = f"idem-{uuid4().hex}"
    first = await _enqueue(key)
    second = await _enqueue(key)
    assert first["id"] == second["id"], (first, second)

    async with async_session() as session:
        rows = (
            await session.execute(
                select(WorkroomJob).where(WorkroomJob.idempotency_key == key)
            )
        ).scalars().all()
    assert len(rows) == 1, rows
    print("✓ duplicate idempotency key does not duplicate work")


async def check_single_claim() -> None:
    key = f"claim-{uuid4().hex}"
    job = await _enqueue(key)

    # Concurrent workers: SKIP LOCKED must hand this row to exactly one.
    claims = await asyncio.gather(*[
        queue.claim(f"queue-e2e-{index}", job_types=[TEST_JOB_TYPE])
        for index in range(4)
    ])
    winners = [claim for claim in claims if claim and claim["id"] == job["id"]]
    assert len(winners) == 1, claims
    assert winners[0]["attempt_count"] == 1, winners[0]
    assert winners[0]["status"] == "running", winners[0]
    print("✓ a queued job is claimed exactly once")


async def check_lease_recovery() -> None:
    key = f"lease-{uuid4().hex}"
    job = await _enqueue(key)
    claimed = await queue.claim("queue-e2e-doomed", job_types=[TEST_JOB_TYPE])
    assert claimed and claimed["id"] == job["id"], claimed

    # Simulate a worker that died without releasing its lease.
    async with async_session() as session:
        row = await session.get(WorkroomJob, job["id"])
        row.lease_expires_at = datetime.utcnow() - timedelta(seconds=5)
        await session.commit()

    recovered = await queue.recover_expired_leases()
    assert recovered >= 1, recovered

    state = await queue.get_job(job["id"])
    assert state["status"] == "queued", state
    assert state["lease_owner"] is None, state
    assert state["error_code"] == "lease_expired", state

    # A heartbeat from the dead worker must not resurrect its claim.
    assert not await queue.heartbeat(job["id"], "queue-e2e-doomed")
    print("✓ an expired lease returns the job to the queue")


async def check_retry_budget() -> None:
    key = f"retry-{uuid4().hex}"
    job = await _enqueue(key, max_attempts=2)

    first = await queue.claim("queue-e2e-a", job_types=[TEST_JOB_TYPE])
    assert first["id"] == job["id"], first
    state = await queue.fail(
        job["id"], "queue-e2e-a", error_code="boom", error_message="first failure"
    )
    assert state["will_retry"] is True, state
    assert state["status"] == "queued", state

    # Make the backoff delay elapse so the retry is claimable.
    async with async_session() as session:
        row = await session.get(WorkroomJob, job["id"])
        row.available_at = datetime.utcnow() - timedelta(seconds=1)
        await session.commit()

    second = await queue.claim("queue-e2e-b", job_types=[TEST_JOB_TYPE])
    assert second["id"] == job["id"], second
    assert second["attempt_count"] == 2, second
    state = await queue.fail(
        job["id"], "queue-e2e-b", error_code="boom", error_message="second failure"
    )
    assert state["will_retry"] is False, state
    assert state["status"] == "failed", state

    exhausted = await queue.get_job(job["id"])
    assert exhausted["status"] == "failed", exhausted
    assert exhausted["completed_at"] is not None, exhausted

    # An exhausted job is never claimed again.
    assert await queue.claim("queue-e2e-c", job_types=[TEST_JOB_TYPE]) is None
    print("✓ retries stop after max attempts")


async def check_idempotent_completion() -> None:
    key = f"complete-{uuid4().hex}"
    job = await _enqueue(key)
    claimed = await queue.claim("queue-e2e-done", job_types=[TEST_JOB_TYPE])
    assert claimed["id"] == job["id"], claimed

    assert await queue.complete(job["id"], "queue-e2e-done") is True
    # Completing twice must not reopen or double-count the job.
    assert await queue.complete(job["id"], "queue-e2e-done") is False
    final = await queue.get_job(job["id"])
    assert final["status"] == "completed", final
    print("✓ completion is idempotent")


async def check_backoff_is_bounded() -> None:
    assert queue.retry_delay_seconds(1) == queue.BASE_RETRY_SECONDS
    assert queue.retry_delay_seconds(2) == queue.BASE_RETRY_SECONDS * 2
    assert queue.retry_delay_seconds(50) == queue.MAX_RETRY_SECONDS
    print("✓ retry backoff grows and stays bounded")


async def run_all() -> None:
    await init_db()
    await cleanup()
    try:
        await check_idempotent_enqueue()
        await check_single_claim()
        await check_lease_recovery()
        await check_retry_budget()
        await check_idempotent_completion()
        await check_backoff_is_bounded()
    finally:
        await cleanup()


async def seed_restart() -> None:
    """Queue work, then leave it for a restarted process to find."""
    await init_db()
    async with async_session() as session:
        await session.execute(
            delete(WorkroomJob).where(WorkroomJob.idempotency_key == RESTART_KEY)
        )
        await session.commit()
    job = await queue.enqueue(
        org_id=ORG_ID,
        workroom_id=ROOM_ID,
        job_type=TEST_JOB_TYPE,
        idempotency_key=RESTART_KEY,
        payload={"seeded": True},
    )
    assert job["status"] == "queued", job
    print("Workroom queue restart seed: OK")


async def verify_restart() -> None:
    """The queued job must still be claimable after the process restarted."""
    await init_db()
    async with async_session() as session:
        row = (
            await session.execute(
                select(WorkroomJob).where(
                    WorkroomJob.idempotency_key == RESTART_KEY
                )
            )
        ).scalar_one_or_none()
    assert row is not None, "The queued job did not survive the restart"
    assert row.status == "queued", row.status
    assert (row.payload or {}).get("seeded") is True, row.payload

    claimed = await queue.claim("queue-e2e-restart", job_types=[TEST_JOB_TYPE])
    assert claimed is not None and claimed["id"] == row.id, claimed
    await queue.complete(row.id, "queue-e2e-restart")

    async with async_session() as session:
        await session.execute(
            delete(WorkroomJob).where(WorkroomJob.idempotency_key == RESTART_KEY)
        )
        await session.commit()
    print("Workroom queue restart verify: OK")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "seed-restart":
        asyncio.run(seed_restart())
    elif mode == "verify-restart":
        asyncio.run(verify_restart())
    else:
        asyncio.run(run_all())
        print("Workroom queue E2E: OK")
