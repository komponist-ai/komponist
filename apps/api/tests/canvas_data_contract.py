"""Deterministic contract checks for Canvas fact selection and dates."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

from canvas_data import (  # noqa: E402
    _deduplicate_records,
    _explicit_fact_date,
    _fact_relevance,
)


def check_semantic_fact_binding() -> None:
    admission = {
        "statement": "Admission to the Campus Forum is free.",
        "detail": "",
        "evidence": [{"excerpt": "Students enter free of charge."}],
    }
    venue = {
        "statement": "The Campus Forum venue is Forum Hall.",
        "detail": "",
        "evidence": [{"excerpt": "Forum Hall is reserved for the event."}],
    }
    approved_date = {
        "statement": "The Campus Forum is scheduled for 14 November 2026.",
        "detail": "",
        "evidence": [{"excerpt": "Approved event date: 14 November 2026."}],
    }

    assert _fact_relevance(admission, "Campus Forum", "venue") < 0
    assert _fact_relevance(venue, "Campus Forum", "venue") > 0
    assert _fact_relevance(admission, "Campus Forum", "approved date") < 0
    assert _fact_relevance(approved_date, "Campus Forum", "approved date") > 0
    assert _fact_relevance(
        {
            "statement": (
                "The board approves a maximum Campus Forum budget of €4,800."
            ),
        },
        "Campus Forum",
        "approved date",
    ) < 0
    assert _fact_relevance(
        {
            "statement": (
                "Admission to the Campus Forum is free for partner organizations."
            ),
        },
        "Campus Forum",
        "sponsor",
    ) < 0
    print("✓ a shared project name cannot bind the wrong field")


def check_asserted_dates() -> None:
    record = {
        "statement": "The Campus Forum is scheduled for 14 November 2026.",
        "detail": "",
        "evidence": [{
            "excerpt": "The approved date is 14 November 2026.",
            "source_date": "2026-07-25T10:00:00Z",
        }],
    }
    assert _explicit_fact_date(record).startswith("2026-11-14")

    no_event = {
        "statement": "Admission is free.",
        "detail": "",
        "evidence": [{"source_date": "2026-07-25T10:00:00Z"}],
    }
    assert _explicit_fact_date(no_event) is None
    print("✓ timelines use asserted dates, not import or review timestamps")


def check_duplicate_suppression() -> None:
    records = [
        {"id": "v2", "entity_type": "Goal",
         "statement": "Recruit 120 volunteers for the Campus Forum."},
        {"id": "copy", "entity_type": "Goal",
         "statement": "Recruit 120 volunteers for Campus Forum"},
        {"id": "other", "entity_type": "Constraint",
         "statement": "Recruit 120 volunteers for the Campus Forum."},
    ]
    deduplicated = _deduplicate_records(records)
    assert [record["id"] for record in deduplicated] == ["v2", "other"]
    print("✓ near-identical facts collapse without merging different types")


if __name__ == "__main__":
    check_semantic_fact_binding()
    check_asserted_dates()
    check_duplicate_suppression()
    print("Canvas data contract: OK")
