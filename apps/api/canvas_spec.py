"""The Canvas contract: what a generated interface is allowed to be.

A Canvas is a declarative description of a read-only view over confirmed
company knowledge. The model never writes JavaScript, JSX, HTML, SQL or
Cypher — it writes only a ``CanvasSpec``, and the server owns every query
behind it.

Three rules make this safe, and all three are enforced here rather than in a
prompt:

1. **Closed vocabulary.** Only registered component types and only queries
   from a fixed catalog. An unknown value is rejected, never passed through.
2. **No free expressions.** Filters are ``(field, op, value)`` triples whose
   field names come from an allowlist, so a value can only ever reach Cypher
   as a bound parameter.
3. **No outbound references.** No component may carry a URL. External images
   and links would leak a viewer's IP and could encode data for exfiltration,
   so they are rejected in the spec *and* blocked again in the renderer.

The JSON Schema below is deliberately flat: every component shares one shape
with a ``type`` discriminator instead of a polymorphic ``anyOf``. OpenAI's
strict mode requires closed objects with every property required, and a flat
shape keeps the schema inside the subset this codebase already validates.
Which ``type`` may use which ``query`` is then checked in Python, where the
rule can be expressed properly.
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


SCHEMA_VERSION = "1"

MAX_COMPONENTS = 12
# The model may request any limit; the server clamps to this regardless.
MAX_ROWS = 100
MAX_ENTITY_IDS = 50
MAX_FILTERS = 6

COMPONENT_TYPES = (
    "metric",
    "entity_list",
    "relationship_table",
    "status_board",
    "timeline",
    "evidence_list",
    "markdown_narrative",
    "filter_bar",
)

QUERY_TYPES = (
    "none",
    "entity_count",
    "entity_list",
    "entity_fact",
    "aggregate_by_type",
    "aggregate_by_confidence",
    "relationship_list",
    "timeline_events",
    "evidence_list",
    "source_passages",
)

# A component may only pull data in ways that make sense for how it renders.
# This is what stops a "metric" from quietly returning 100 rows of evidence.
COMPATIBLE_QUERIES: dict[str, set[str]] = {
    "metric": {"entity_count", "entity_fact", "aggregate_by_type", "aggregate_by_confidence"},
    "entity_list": {"entity_list"},
    "relationship_table": {"relationship_list"},
    "status_board": {"aggregate_by_confidence", "entity_list"},
    "timeline": {"timeline_events"},
    "evidence_list": {"evidence_list", "source_passages"},
    "markdown_narrative": {"entity_list"},
    "filter_bar": {"none"},
}

# Filter fields are an allowlist because each one maps to a known property in
# a hand-written Cypher fragment. Anything else has no safe translation.
FILTER_FIELDS = (
    "entity_type",
    "confidence",
    "department_id",
    "title",
    "created_at",
    "updated_at",
)
FILTER_OPS = ("eq", "neq", "contains", "gt", "lt")

SORT_FIELDS = (
    "created_at", "updated_at", "confirmed_at", "title", "entity_type",
    "confidence",
)

# Matches an absolute URL, a protocol-relative URL, or a data/javascript URI.
_URL_PATTERN = re.compile(
    r"(?i)\b(?:https?:|ftp:|file:|data:|javascript:|vbscript:)|(?:^|\s)//\w",
)
# Markdown image/link syntax pointing anywhere at all.
_MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\([^)]*\)")


def _reject_urls(value: str, field_name: str) -> str:
    """Refuse any outbound reference in model-authored text."""
    if _URL_PATTERN.search(value):
        raise ValueError(f"{field_name} must not contain a URL")
    if _MARKDOWN_LINK_PATTERN.search(value):
        raise ValueError(f"{field_name} must not contain Markdown links or images")
    return value


# --------------------------------------------------------------- schema ----

# Strict Structured Outputs: every object is closed and every property is
# required. Fields that do not apply to a component carry an empty value.
CANVAS_SCHEMA: dict[str, Any] = {
    "title": "komponist_canvas_spec",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "title", "description", "components"],
    "properties": {
        "schema_version": {"type": "string", "description": "Always \"1\"."},
        "title": {"type": "string"},
        "description": {
            "type": "string",
            "description": "One sentence on what this view answers.",
        },
        "components": {
            "type": "array",
            "description": f"Between 1 and {MAX_COMPONENTS} components.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id", "type", "title", "description", "narrative",
                    "position", "binding", "options",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Short stable kebab-case id, unique in this canvas.",
                    },
                    "type": {"type": "string", "enum": list(COMPONENT_TYPES)},
                    "title": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "Short helper text. Empty string when not needed.",
                    },
                    "narrative": {
                        "type": "string",
                        "description": (
                            "Only for markdown_narrative. Plain Markdown without "
                            "links or images. Empty string for every other type."
                        ),
                    },
                    "position": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["row", "column", "width"],
                        "properties": {
                            "row": {"type": "integer"},
                            "column": {"type": "integer"},
                            "width": {
                                "type": "integer",
                                "description": "Columns spanned in a 12-column grid.",
                            },
                        },
                    },
                    "binding": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "query", "entity_type", "entity_name", "field",
                            "project", "filters", "sort_field",
                            "sort_direction", "limit", "entity_ids",
                        ],
                        "properties": {
                            "query": {"type": "string", "enum": list(QUERY_TYPES)},
                            "entity_type": {
                                "type": "string",
                                "description": "Decision, Goal, Constraint, Project, or empty.",
                            },
                            "entity_name": {
                                "type": "string",
                                "description": "Subject entity for entity_fact. Empty otherwise.",
                            },
                            "field": {
                                "type": "string",
                                "description": (
                                    "Extra search term for entity_fact, such as "
                                    "\"duration\". Empty otherwise."
                                ),
                            },
                            "project": {"type": "string"},
                            "filters": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["field", "op", "value"],
                                    "properties": {
                                        "field": {
                                            "type": "string",
                                            "enum": list(FILTER_FIELDS),
                                        },
                                        "op": {"type": "string", "enum": list(FILTER_OPS)},
                                        "value": {"type": "string"},
                                    },
                                },
                            },
                            "sort_field": {"type": "string", "enum": list(SORT_FIELDS)},
                            "sort_direction": {"type": "string", "enum": ["asc", "desc"]},
                            "limit": {"type": "integer"},
                            "entity_ids": {
                                "type": "array",
                                "description": (
                                    "Required for markdown_narrative: the confirmed "
                                    "facts the text is based on."
                                ),
                                "items": {"type": "string"},
                            },
                        },
                    },
                    "options": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["show_sources", "empty_text", "accent"],
                        "properties": {
                            "show_sources": {"type": "boolean"},
                            "empty_text": {
                                "type": "string",
                                "description": "Shown when the viewer may see no matching data.",
                            },
                            "accent": {
                                "type": "string",
                                "enum": ["neutral", "positive", "warning", "danger", "info"],
                            },
                        },
                    },
                },
            },
        },
    },
}


# ------------------------------------------------------------- contract ----


class CanvasFilter(BaseModel):
    field: Literal[FILTER_FIELDS] = "entity_type"  # type: ignore[valid-type]
    op: Literal[FILTER_OPS] = "eq"  # type: ignore[valid-type]
    value: str = Field(default="", max_length=200)

    @field_validator("value")
    @classmethod
    def _clean_value(cls, value: str) -> str:
        # The value only ever travels as a bound Cypher parameter, but keeping
        # it plain removes any temptation to interpolate it later.
        return " ".join(value.split())[:200]


class CanvasBinding(BaseModel):
    query: Literal[QUERY_TYPES] = "none"  # type: ignore[valid-type]
    entity_type: str = Field(default="", max_length=60)
    entity_name: str = Field(default="", max_length=200)
    field: str = Field(default="", max_length=60)
    project: str = Field(default="", max_length=200)
    filters: list[CanvasFilter] = Field(default_factory=list, max_length=MAX_FILTERS)
    sort_field: Literal[SORT_FIELDS] = "updated_at"  # type: ignore[valid-type]
    sort_direction: Literal["asc", "desc"] = "desc"
    limit: int = 20
    entity_ids: list[str] = Field(default_factory=list, max_length=MAX_ENTITY_IDS)

    @field_validator("limit")
    @classmethod
    def _clamp_limit(cls, value: int) -> int:
        # Clamped rather than rejected: an over-eager limit is not an attack,
        # but it must never reach the database.
        return max(1, min(int(value), MAX_ROWS))

    @field_validator("entity_ids")
    @classmethod
    def _clean_ids(cls, value: list[str]) -> list[str]:
        return [item.strip()[:120] for item in value if item and item.strip()][
            :MAX_ENTITY_IDS
        ]


class CanvasPosition(BaseModel):
    row: int = Field(default=0, ge=0, le=64)
    column: int = Field(default=0, ge=0, le=11)
    width: int = Field(default=12, ge=1, le=12)


class CanvasOptions(BaseModel):
    show_sources: bool = True
    empty_text: str = Field(default="", max_length=200)
    accent: Literal["neutral", "positive", "warning", "danger", "info"] = "neutral"

    @field_validator("empty_text")
    @classmethod
    def _no_urls(cls, value: str) -> str:
        return _reject_urls(" ".join(value.split()), "empty_text")


class CanvasComponent(BaseModel):
    id: str = Field(min_length=1, max_length=60)
    type: Literal[COMPONENT_TYPES] = "entity_list"  # type: ignore[valid-type]
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=400)
    narrative: str = Field(default="", max_length=2000)
    position: CanvasPosition = Field(default_factory=CanvasPosition)
    binding: CanvasBinding = Field(default_factory=CanvasBinding)
    options: CanvasOptions = Field(default_factory=CanvasOptions)

    @field_validator("id")
    @classmethod
    def _normalize_id(cls, value: str) -> str:
        slug = "-".join(value.strip().lower().split())
        cleaned = "".join(
            character for character in slug if character.isalnum() or character == "-"
        ).strip("-")
        if not cleaned:
            raise ValueError("component id must contain letters or digits")
        return cleaned[:60]

    @field_validator("title", "description")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return _reject_urls(" ".join(value.split()), "text")

    @field_validator("narrative")
    @classmethod
    def _clean_narrative(cls, value: str) -> str:
        return _reject_urls(value.strip(), "narrative")

    @model_validator(mode="after")
    def _check_component(self) -> "CanvasComponent":
        allowed = COMPATIBLE_QUERIES[self.type]
        if self.binding.query not in allowed:
            raise ValueError(
                f"component type {self.type} cannot use query {self.binding.query}"
            )

        if self.type == "markdown_narrative":
            # The one place a model writes prose about facts. It must name the
            # confirmed facts it rests on, so the reader can check every claim.
            if not self.narrative.strip():
                raise ValueError("markdown_narrative needs narrative text")
            if not self.binding.entity_ids:
                raise ValueError(
                    "markdown_narrative must cite the confirmed facts it is based on"
                )
        elif self.narrative.strip():
            raise ValueError(f"{self.type} must not carry narrative text")

        if self.binding.query == "entity_fact" and not self.binding.entity_name:
            raise ValueError("entity_fact needs an entity_name to look up")
        return self


class CanvasSpec(BaseModel):
    schema_version: Literal["1"] = "1"
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=400)
    components: list[CanvasComponent] = Field(min_length=1, max_length=MAX_COMPONENTS)

    @field_validator("title", "description")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return _reject_urls(" ".join(value.split()), "text")

    @field_validator("components")
    @classmethod
    def _unique_ids(cls, components: list[CanvasComponent]) -> list[CanvasComponent]:
        ids = [component.id for component in components]
        if len(set(ids)) != len(ids):
            raise ValueError("component ids must be unique within a canvas")
        return components

    @model_validator(mode="after")
    def _check_budget(self) -> "CanvasSpec":
        # A canvas must not be able to pull an unbounded amount of the graph
        # in one render, however its individual components are shaped.
        total_rows = sum(
            component.binding.limit
            for component in self.components
            if component.binding.query != "none"
        )
        if total_rows > MAX_COMPONENTS * MAX_ROWS:
            raise ValueError("the canvas requests too much data in one view")
        return self


class CanvasValidationError(Exception):
    """A spec was rejected. The message is safe to show a person."""


def validate_spec(raw: Any) -> CanvasSpec:
    """Validate an untrusted spec.

    Called on generation *and* again before every render, so a spec altered
    in the database or arriving through a future import can never be rendered
    unchecked.
    """
    from pydantic import ValidationError

    try:
        return CanvasSpec.model_validate(raw)
    except ValidationError as error:
        problems = error.errors()
        first = problems[0] if problems else {}
        location = ".".join(str(part) for part in first.get("loc", ()))
        message = str(first.get("msg", "is not valid")).removeprefix("Value error, ")
        raise CanvasValidationError(
            f"{location or 'canvas'}: {message}"
        ) from error
