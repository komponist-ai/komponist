"""Contract checks for deterministic, organization-safe demo graph IDs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def run() -> None:
    first = main._scoped_demo_facts("org-first")
    repeated = main._scoped_demo_facts("org-first")
    second = main._scoped_demo_facts("org-second")

    assert first == repeated
    assert {fact["id"] for fact in first}.isdisjoint(
        {fact["id"] for fact in second}
    )
    assert {fact["evidence_id"] for fact in first}.isdisjoint(
        {fact["evidence_id"] for fact in second}
    )
    assert {fact["demo_id"] for fact in first} == {
        fact["id"] for fact in main._DEMO_FACTS
    }
    print("Demo workspace contract: OK")


if __name__ == "__main__":
    run()
