"""Hand-written Canvas specifications.

These exist for two reasons. They give the empty state something real to
offer, and — more importantly — they let the renderer, the bindings, the
citations and the permission scope be proven end to end before a model is
involved at all. If generation ever regresses, the feature still works.
"""

from typing import Any


def _binding(query: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "query": query,
        "entity_type": "",
        "entity_name": "",
        "field": "",
        "project": "",
        "filters": [],
        "sort_field": "updated_at",
        "sort_direction": "desc",
        "limit": 20,
        "entity_ids": [],
    }
    return {**base, **overrides}


def _options(**overrides: Any) -> dict[str, Any]:
    return {
        "show_sources": True,
        "empty_text": "",
        "accent": "neutral",
        **overrides,
    }


NORTHSTAR_COMMAND_CENTER: dict[str, Any] = {
    "schema_version": "1",
    "title": "Northstar Pilot Command Center",
    "description": (
        "Milestones, decisions, constraints and the evidence behind them for "
        "the Northstar pilot."
    ),
    "components": [
        {
            "id": "pilot-duration",
            "type": "metric",
            "title": "Pilot duration",
            "description": "From the confirmed pilot scope.",
            "narrative": "",
            "position": {"row": 0, "column": 0, "width": 4},
            "binding": _binding(
                "entity_fact", entity_name="pilot", field="weeks duration"
            ),
            "options": _options(
                accent="info", empty_text="No confirmed pilot scope in your view."
            ),
        },
        {
            "id": "confirmed-decisions",
            "type": "metric",
            "title": "Confirmed decisions",
            "description": "",
            "narrative": "",
            "position": {"row": 0, "column": 4, "width": 4},
            "binding": _binding("entity_count", entity_type="Decision"),
            "options": _options(accent="positive"),
        },
        {
            "id": "knowledge-mix",
            "type": "metric",
            "title": "Knowledge by type",
            "description": "Confirmed facts available to you.",
            "narrative": "",
            "position": {"row": 0, "column": 8, "width": 4},
            "binding": _binding("aggregate_by_type", limit=6),
            "options": _options(),
        },
        {
            "id": "narrow-this-view",
            "type": "filter_bar",
            "title": "Narrow this view",
            "description": (
                "Filters the lists, timeline and passages below. They only hide "
                "what is already shown to you."
            ),
            "narrative": "",
            "position": {"row": 1, "column": 0, "width": 12},
            "binding": _binding("none"),
            "options": _options(),
        },
        {
            "id": "milestones",
            "type": "timeline",
            "title": "Milestones",
            "description": "Confirmed events, most recent first.",
            "narrative": "",
            "position": {"row": 2, "column": 0, "width": 7},
            "binding": _binding("timeline_events", limit=12),
            "options": _options(
                empty_text="No confirmed dated facts are visible to you yet."
            ),
        },
        {
            "id": "open-constraints",
            "type": "status_board",
            "title": "Constraints and risks by confidence",
            "description": "",
            "narrative": "",
            "position": {"row": 2, "column": 7, "width": 5},
            "binding": _binding("entity_list", entity_type="Constraint", limit=10),
            "options": _options(
                accent="warning", empty_text="No confirmed constraints in your view."
            ),
        },
        {
            "id": "decision-log",
            "type": "entity_list",
            "title": "Decision log",
            "description": "",
            "narrative": "",
            "position": {"row": 3, "column": 0, "width": 6},
            "binding": _binding("entity_list", entity_type="Decision", limit=10),
            "options": _options(empty_text="No confirmed decisions in your view."),
        },
        {
            "id": "how-things-connect",
            "type": "relationship_table",
            "title": "How decisions support goals",
            "description": "",
            "narrative": "",
            "position": {"row": 3, "column": 6, "width": 6},
            "binding": _binding("relationship_list", limit=12),
            "options": _options(
                empty_text="No confirmed relationships are visible to you."
            ),
        },
        {
            "id": "supporting-evidence",
            "type": "evidence_list",
            "title": "Supporting passages",
            "description": "Every claim above traces back to one of these.",
            "narrative": "",
            "position": {"row": 4, "column": 0, "width": 12},
            "binding": _binding("source_passages", limit=12),
            "options": _options(
                empty_text="No source passages are visible to you yet."
            ),
        },
    ],
}


EXAMPLES: dict[str, dict[str, Any]] = {
    "northstar-command-center": NORTHSTAR_COMMAND_CENTER,
}

EXAMPLE_SUMMARIES = [
    {
        "key": "northstar-command-center",
        "title": NORTHSTAR_COMMAND_CENTER["title"],
        "description": NORTHSTAR_COMMAND_CENTER["description"],
        "component_count": len(NORTHSTAR_COMMAND_CENTER["components"]),
    },
]
