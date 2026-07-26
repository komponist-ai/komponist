"""Fast checks for task-specific Workroom agent inputs."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

from workroom_agent import _deliverable_topic, _task_topic  # noqa: E402


if __name__ == "__main__":
    room = SimpleNamespace(objective="Prepare the Campus Forum")
    run = {"instruction": "Focus on blockers"}
    task = {
        "title": "Audit privacy, DPA, legal, and financial blockers",
        "description": "Find confirmed processor agreements and approval limits.",
    }

    retrieval = _task_topic(room, run, task)
    assert retrieval.startswith(task["title"])
    assert task["description"] in retrieval
    assert "Focus on blockers" in retrieval
    assert retrieval.endswith(room.objective)

    deliverable = _deliverable_topic(room, task)
    assert task["title"] in deliverable
    assert task["description"] in deliverable
    assert room.objective in deliverable
    print("✓ Workroom retrieval and Compose handoff are task-specific")
    print("Workroom agent contract: OK")
