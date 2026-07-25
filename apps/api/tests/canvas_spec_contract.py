"""Contract checks for the Canvas specification.

Pure and offline: no database, no provider, no network. These pin down the
rules that make a model-authored interface safe to render.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

from canvas_spec import (
    CANVAS_SCHEMA,
    COMPATIBLE_QUERIES,
    MAX_COMPONENTS,
    MAX_ROWS,
    CanvasValidationError,
    validate_spec,
)


def component(**overrides) -> dict:
    base = {
        "id": "open-goals",
        "type": "entity_list",
        "title": "Open goals",
        "description": "",
        "narrative": "",
        "position": {"row": 0, "column": 0, "width": 6},
        "binding": {
            "query": "entity_list",
            "entity_type": "Goal",
            "status": "confirmed",
            "entity_name": "",
            "field": "",
            "project": "",
            "filters": [],
            "sort_field": "updated_at",
            "sort_direction": "desc",
            "limit": 20,
            "entity_ids": [],
        },
        "options": {"show_sources": True, "empty_text": "", "accent": "neutral"},
    }
    binding = {**base["binding"], **overrides.pop("binding", {})}
    return {**base, **overrides, "binding": binding}


def spec(components: list[dict]) -> dict:
    return {
        "schema_version": "1",
        "title": "Pilot view",
        "description": "",
        "components": components,
    }


def rejects(raw: dict, label: str) -> None:
    try:
        validate_spec(raw)
    except CanvasValidationError:
        return
    raise AssertionError(f"validation accepted {label}")


def check_schema_is_strict() -> None:
    """Strict mode needs closed objects with every property required."""

    def walk(node: dict, path: str) -> None:
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, path
            assert set(node.get("required", [])) == set(node.get("properties", {})), path
            for name, child in node.get("properties", {}).items():
                walk(child, f"{path}.{name}")
        if node.get("type") == "array":
            walk(node["items"], f"{path}[]")

    walk(CANVAS_SCHEMA, "$")
    # A flat component shape keeps the schema inside the validated subset.
    assert "anyOf" not in str(CANVAS_SCHEMA), "the schema should avoid anyOf"
    print("✓ the canvas schema satisfies strict structured outputs")


def check_valid_spec_normalises() -> None:
    parsed = validate_spec(spec([component(id="  Open   Goals  ")]))
    assert parsed.components[0].id == "open-goals", parsed.components[0].id
    assert parsed.schema_version == "1"
    print("✓ a valid canvas is accepted and normalised")


def check_closed_vocabulary() -> None:
    rejects(spec([component(type="iframe_embed")]), "an unknown component type")
    rejects(
        spec([component(binding={"query": "raw_cypher"})]),
        "an unknown query",
    )
    rejects(
        spec([component(binding={"filters": [
            {"field": "password", "op": "eq", "value": "x"}
        ]})]),
        "an unknown filter field",
    )
    rejects(
        spec([component(binding={"filters": [
            {"field": "status", "op": "regex", "value": "x"}
        ]})]),
        "an unknown filter operator",
    )
    print("✓ unknown components, queries, fields and operators are rejected")


def check_type_query_compatibility() -> None:
    # A metric must not be able to pull a hundred evidence rows.
    rejects(
        spec([component(type="metric", binding={"query": "evidence_list"})]),
        "a metric bound to evidence_list",
    )
    rejects(
        spec([component(type="filter_bar", binding={"query": "entity_list"})]),
        "a filter bar that fetches data",
    )
    # Every declared pairing is genuinely accepted.
    for component_type, queries in COMPATIBLE_QUERIES.items():
        for query in queries:
            payload = component(
                id=f"{component_type}-{query}",
                type=component_type,
                binding={"query": query},
            )
            if component_type == "markdown_narrative":
                payload["narrative"] = "Grounded summary."
                payload["binding"]["entity_ids"] = ["entity-1"]
            if query == "entity_fact":
                payload["binding"]["entity_name"] = "Northstar Pilot"
                payload["binding"]["field"] = "duration"
            validate_spec(spec([payload]))
    print("✓ component and query pairings are enforced both ways")


def check_no_outbound_references() -> None:
    rejects(spec([component(title="See https://evil.example")]), "a URL in a title")
    rejects(
        spec([component(
            type="markdown_narrative",
            narrative="Pilot summary ![x](http://evil.example/p.png)",
            binding={"query": "entity_list", "entity_ids": ["entity-1"]},
        )]),
        "a remote image in a narrative",
    )
    rejects(
        spec([component(
            type="markdown_narrative",
            narrative="Click [here](javascript:alert(1))",
            binding={"query": "entity_list", "entity_ids": ["entity-1"]},
        )]),
        "a javascript: link",
    )
    rejects(
        spec([component(options={
            "show_sources": True,
            "empty_text": "Visit //cdn.evil.example",
            "accent": "neutral",
        })]),
        "a protocol-relative URL in empty text",
    )
    print("✓ no component may carry an outbound reference")


def check_narrative_must_cite() -> None:
    rejects(
        spec([component(
            type="markdown_narrative",
            narrative="The pilot is going well.",
            binding={"query": "entity_list", "entity_ids": []},
        )]),
        "an uncited narrative",
    )
    rejects(
        spec([component(narrative="Sneaky prose on a list")]),
        "narrative text on a non-narrative component",
    )
    grounded = validate_spec(spec([component(
        type="markdown_narrative",
        narrative="September launch, four-week pilot.",
        binding={"query": "entity_list", "entity_ids": ["ctx-launch"]},
    )]))
    assert grounded.components[0].binding.entity_ids == ["ctx-launch"]
    print("✓ narrative prose must name the confirmed facts behind it")


def check_budgets() -> None:
    rejects(spec([]), "an empty canvas")
    rejects(
        spec([component(id=f"c{index}") for index in range(MAX_COMPONENTS + 1)]),
        "too many components",
    )
    rejects(
        spec([component(id="a"), component(id="a")]),
        "duplicate component ids",
    )
    # An over-eager limit is clamped rather than rejected.
    clamped = validate_spec(spec([component(binding={"limit": 5000})]))
    assert clamped.components[0].binding.limit == MAX_ROWS, (
        clamped.components[0].binding.limit
    )
    zero = validate_spec(spec([component(binding={"limit": 0})]))
    assert zero.components[0].binding.limit == 1
    print("✓ component and row budgets are enforced")


def check_entity_fact_needs_subject() -> None:
    rejects(
        spec([component(type="metric", binding={"query": "entity_fact"})]),
        "entity_fact without a subject",
    )
    print("✓ entity_fact requires an explicit subject and field")


def check_revalidation_of_stored_spec() -> None:
    """A spec altered after storage must not survive a second validation."""
    stored = validate_spec(spec([component()])).model_dump()
    stored["components"][0]["type"] = "script_runner"
    rejects(stored, "a tampered stored spec")
    print("✓ a stored spec is re-validated before it can be rendered")


def run() -> None:
    check_schema_is_strict()
    check_valid_spec_normalises()
    check_closed_vocabulary()
    check_type_query_compatibility()
    check_no_outbound_references()
    check_narrative_must_cite()
    check_budgets()
    check_entity_fact_needs_subject()
    check_revalidation_of_stored_spec()


if __name__ == "__main__":
    run()
    print("Canvas spec contract: OK")
