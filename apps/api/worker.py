"""Workroom worker process.

Runs the same image and dependencies as the API and claims durable jobs from
Postgres. Because jobs live in the database rather than in an event loop, work
survives an API deploy, a worker crash, and a full stack restart.

Run locally with:

    python worker.py
"""

import asyncio
import os
import signal
import socket
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages"))

from core.graph import GraphClient  # noqa: E402
from database import init_db  # noqa: E402
from workroom_agent import run_worker_loop  # noqa: E402


async def main() -> int:
    worker_id = os.getenv(
        "KOMPONIST_WORKER_ID",
        f"{socket.gethostname()[:40]}-{uuid4().hex[:8]}",
    )
    poll_seconds = float(os.getenv("KOMPONIST_WORKER_POLL_SECONDS", "1"))

    GraphClient.initialize()
    await init_db()
    print(f"✓ Workroom worker {worker_id} ready", flush=True)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in ("SIGTERM", "SIGINT"):
        try:
            loop.add_signal_handler(
                getattr(signal, signal_name), stop_event.set
            )
        except (AttributeError, NotImplementedError):
            # Signal handlers are unavailable on some platforms; the worker
            # still exits when the container stops.
            pass

    try:
        processed = await run_worker_loop(
            worker_id=worker_id,
            stop_event=stop_event,
            poll_seconds=poll_seconds,
        )
        print(f"✓ Worker {worker_id} stopped after {processed} jobs", flush=True)
    finally:
        await GraphClient.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
