"""Optional live check that plan generation really works against OpenAI.

This is never part of normal CI: it makes a paid request. It runs only when
both are set:

    OPENAI_API_KEY=<centrally managed key>
    RUN_LIVE_AI_TESTS=1

Run it with the same central configuration production uses:

    KOMPONIST_AI_MODE=live KOMPONIST_LLM_PROVIDER=openai \\
    KOMPONIST_OPENAI_STORE=false RUN_LIVE_AI_TESTS=1 \\
    python tests/workroom_plans_live_ai.py

The model is taken from KOMPONIST_LLM_MODEL through the central provider
configuration; it is deliberately not hard-coded here.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

from workroom_plans import MAX_PLAN_TASKS, generate_plan_spec


def should_run() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) and os.getenv("RUN_LIVE_AI_TESTS") == "1"


async def run() -> None:
    spec, metadata = await generate_plan_spec(
        objective="Prepare the Northstar pilot launch for design partners",
        title="Northstar launch room",
        context_lines=[
            "Decision: The Northstar pilot launches in September.",
            "Goal: The pilot runs for four weeks with ten design partners.",
            "Constraint: Every extracted fact needs human review before use.",
        ],
        guidance="Prioritise what must happen before the first partner is onboarded.",
    )

    assert 1 <= len(spec.tasks) <= MAX_PLAN_TASKS, len(spec.tasks)
    assert spec.summary.strip(), spec.summary

    keys = [task.client_key for task in spec.tasks]
    assert len(set(keys)) == len(keys), keys
    for task in spec.tasks:
        assert task.title.strip(), task
        assert task.description.strip(), task
        assert task.assignee_type in {"agent", "human"}, task
        for dependency in task.depends_on:
            assert dependency in set(keys), (task.client_key, dependency)

    print(f"Provider: {metadata['provider']} / model: {metadata['model']}")
    print(f"Summary: {spec.summary}")
    for task in spec.tasks:
        marker = "→" if task.depends_on else "•"
        print(f"  {marker} [{task.assignee_type}] {task.client_key}: {task.title}")


if __name__ == "__main__":
    if not should_run():
        print(
            "Live AI plan test skipped: set OPENAI_API_KEY and RUN_LIVE_AI_TESTS=1 "
            "to run it."
        )
        raise SystemExit(0)
    asyncio.run(run())
    print("Workroom plans live AI: OK")
