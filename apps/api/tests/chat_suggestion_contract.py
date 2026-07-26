"""Fast contract checks for human-readable graph-derived starter questions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def run() -> None:
    row = {
        "id": "campus-forum-project",
        "entity_type": "Project",
        "statement": (
            "The Campus Forum project runs for 6 weeks and ends with the event "
            "on 14 November 2026."
        ),
        "detail": "",
        "reference": "upload:08-campus-forum-plan-v2.md:demo",
    }
    suggestion = main._chat_suggestion_from_entity(row)
    assert suggestion["prompt"] == "How long does the Campus Forum project run?"
    assert "runs for and ends" not in suggestion["prompt"]

    constraint = main._chat_suggestion_from_entity({
        "id": "reimbursement-window",
        "entity_type": "Constraint",
        "statement": (
            "Reimbursement requests must include a receipt and be submitted "
            "within one week."
        ),
        "detail": "",
        "reference": "upload:04-budget-policy.md:demo",
    })
    assert constraint["title"] == "Key constraint"
    assert constraint["prompt"] == (
        "Which constraint is documented in Budget Policy?"
    )
    print("Chat suggestion contract: OK")


if __name__ == "__main__":
    run()
