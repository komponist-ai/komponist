"""Executes Canvas data bindings against the graph, safely.

The model never writes a query. It picks one from a fixed catalog and supplies
typed arguments; everything below is hand-written Cypher.

Two invariants hold for every query in this module:

* **The server owns the scope.** Organization, department visibility and
  confirmed-only status are injected here, never taken from the spec. A
  binding can therefore only ever narrow what the viewer could already see
  through Chat, Graph or Sources — never widen it.
* **Values are parameters, never syntax.** Filter values reach Neo4j as bound
  parameters. The only strings interpolated into a query come from closed
  enums validated by :mod:`canvas_spec`, so a filter cannot carry a query.

* **Nothing is shown uncited.** Every query that presents a fact requires at
  least one piece of evidence the viewer can actually open. A confirmed entity
  whose only evidence sits in a department they cannot read drops out entirely
  rather than appearing as an unsourced claim.

Aggregates are computed *after* scoping, so a count cannot be used to infer
the existence of knowledge the viewer may not read. They are also computed
over cited entities only, so a number never counts something the reader
cannot verify.
"""

import asyncio
import re
from typing import Any, Optional

from core.graph import GraphClient


# Cypher fragments for each allowlisted filter field. The alias is supplied by
# this module, never by the spec.
_FILTER_PROPERTY = {
    "entity_type": "entity_type",
    "confidence": "confidence",
    "title": "statement",
    "created_at": "created_at",
    "updated_at": "updated_at",
}
_SORT_PROPERTY = {
    "created_at": "created_at",
    "updated_at": "updated_at",
    "confirmed_at": "confirmed_at",
    "title": "statement",
    "entity_type": "entity_type",
    "confidence": "confidence",
}
_DATE_FIELDS = {"created_at", "updated_at", "confirmed_at"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ].*)?$")

# A whole canvas must not be able to pull an unbounded slice of the graph.
CANVAS_ROW_BUDGET = 400


def _scope_params(user: dict) -> dict[str, Any]:
    """Department scope taken from the caller, never from the spec."""
    return {
        "access_all_departments": bool(user.get("access_all_departments")),
        "department_ids": user.get("department_ids") or [],
    }


def _knowledge_scope(alias: str) -> str:
    # Mirrors the predicate used by Chat and Compose. Kept as one expression
    # so Canvas can never drift into a laxer definition of "visible".
    return (
        f"($access_all_departments OR size(coalesce({alias}.department_ids, [])) = 0 "
        f"OR any(department_id IN coalesce({alias}.department_ids, []) "
        "WHERE department_id IN $department_ids))"
    )


def _evidence_scope(alias: str) -> str:
    return (
        f"($access_all_departments OR {alias}.department_id IS NULL "
        f"OR {alias}.department_id IN $department_ids)"
    )


def _entity_filters(binding: Any, alias: str) -> tuple[list[str], dict[str, Any]]:
    """Translate typed filters into parameterized Cypher fragments."""
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if binding.entity_type:
        clauses.append(f"toLower({alias}.entity_type) = toLower($binding_entity_type)")
        params["binding_entity_type"] = binding.entity_type

    for index, item in enumerate(binding.filters):
        if item.field == "department_id":
            # Never a way to widen scope: this can only narrow within the
            # departments the knowledge-scope predicate already permits.
            clauses.append(
                f"any(department_id IN coalesce({alias}.department_ids, []) "
                f"WHERE department_id = $filter_{index})"
            )
            params[f"filter_{index}"] = item.value
            continue

        property_name = _FILTER_PROPERTY.get(item.field)
        if property_name is None or not item.value:
            continue

        parameter = f"filter_{index}"
        if item.field in _DATE_FIELDS:
            # A malformed date would make the whole query fail, so an
            # unusable value is dropped rather than passed to Neo4j.
            if not _ISO_DATE.match(item.value) or item.op not in {"gt", "lt"}:
                continue
            operator = ">" if item.op == "gt" else "<"
            clauses.append(
                f"{alias}.{property_name} IS NOT NULL AND "
                f"{alias}.{property_name} {operator} datetime(${parameter})"
            )
            params[parameter] = item.value
            continue

        if item.op == "eq":
            clauses.append(f"toLower({alias}.{property_name}) = toLower(${parameter})")
        elif item.op == "neq":
            clauses.append(
                f"coalesce(toLower({alias}.{property_name}), '') <> toLower(${parameter})"
            )
        elif item.op == "contains":
            clauses.append(
                f"toLower(coalesce({alias}.{property_name}, '')) "
                f"CONTAINS toLower(${parameter})"
            )
        else:
            continue
        params[parameter] = item.value

    return clauses, params


def _order_clause(binding: Any, alias: str) -> str:
    # Both halves come from validated enums, so this interpolation carries no
    # caller-controlled text.
    property_name = _SORT_PROPERTY.get(binding.sort_field, "updated_at")
    direction = "ASC" if binding.sort_direction == "asc" else "DESC"
    return f"ORDER BY {alias}.{property_name} {direction}"


def _entity_row(record: dict) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "entity_type": record.get("entity_type") or "Fact",
        "statement": record.get("statement") or "",
        "detail": record.get("detail") or "",
        "confidence": record.get("confidence") or "",
        "department_ids": record.get("department_ids") or [],
        "created_at": str(record["created_at"]) if record.get("created_at") else None,
        "source_ids": [item for item in (record.get("source_ids") or []) if item],
    }


def _source_row(record: dict, org_id: str) -> dict[str, Any]:
    from artifacts import source_deep_link_path

    return {
        "id": record.get("id"),
        "title": record.get("title") or "Source",
        "reference": record.get("reference") or "",
        "excerpt": record.get("excerpt") or "",
        "page": record.get("page"),
        "line_start": record.get("line_start"),
        "line_end": record.get("line_end"),
        # A deep link into Komponist itself, not an external URL.
        "komponist_path": source_deep_link_path(org_id, record.get("id") or ""),
    }


async def _run(query: str, params: dict[str, Any]) -> list[dict]:
    return await GraphClient.run_query(query, params) or []


# ------------------------------------------------------- project scope ----

# Evidence projection reused by every query, so a row can never be returned
# without the shape needed to cite it.
_EVIDENCE_PROJECTION = """[item IN evidence WHERE item IS NOT NULL | {
                   id: item.id, title: item.title, reference: item.reference,
                   excerpt: item.excerpt, page: item.page,
                   line_start: item.line_start, line_end: item.line_end
               }]"""


def _project_scope(binding: Any, alias: str) -> tuple[str, dict[str, Any]]:
    """Restrict a query to knowledge belonging to one named project.

    Uses the same relationship vocabulary as the project-scoped queries in
    packages/core/queries.py so Canvas cannot drift into a second, laxer
    notion of "belongs to this project".

    Extracted knowledge does not always carry an explicit project edge, so a
    statement naming the project counts too. That is a looser match than an
    edge, but the alternative — a project dashboard that silently shows
    unrelated company data — is worse.
    """
    if not binding.project:
        return "", {}
    clause = f"""
          AND (
            toLower(coalesce({alias}.statement, '')) CONTAINS toLower($project_name)
            OR EXISTS {{
                MATCH ({alias})-[:AFFECTS|RELATES_TO|ADVANCES|CONSTRAINS]-(p:Project)
                WHERE p.org_id = $org_id
                  AND toLower(coalesce(p.statement, '')) CONTAINS toLower($project_name)
            }}
          )"""
    return clause, {"project_name": binding.project}


def _entity_where(binding: Any, alias: str) -> tuple[str, dict[str, Any]]:
    """The full server-owned WHERE tail: filters plus project scope."""
    clauses, params = _entity_filters(binding, alias)
    project_clause, project_params = _project_scope(binding, alias)
    where = ("AND " + " AND ".join(clauses)) if clauses else ""
    return f"{where}{project_clause}", {**params, **project_params}


# ------------------------------------------------------------- queries ----


async def _entity_list(org_id: str, user: dict, binding: Any) -> dict[str, Any]:
    where, params = _entity_where(binding, "e")
    id_clause = "AND e.id IN $entity_ids" if binding.entity_ids else ""

    records = await _run(
        f"""
        MATCH (e:Entity)
        WHERE e.org_id = $org_id AND e.status = 'confirmed'
          AND {_knowledge_scope('e')}
          {where}
          {id_clause}
        OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
        WHERE ev.org_id = $org_id AND {_evidence_scope('ev')}
        WITH e, collect(DISTINCT ev) AS evidence
        WHERE size(evidence) > 0
        {_order_clause(binding, 'e')}
        LIMIT $limit
        RETURN e.id AS id, e.entity_type AS entity_type, e.statement AS statement,
               e.detail AS detail, e.confidence AS confidence,
               e.department_ids AS department_ids, e.created_at AS created_at,
               [item IN evidence WHERE item IS NOT NULL | item.id] AS source_ids,
               {_EVIDENCE_PROJECTION} AS evidence
        """,
        {
            "org_id": org_id,
            "limit": binding.limit,
            "entity_ids": binding.entity_ids,
            **_scope_params(user),
            **params,
        },
    )

    rows = [_entity_row(record) for record in records]
    sources: dict[str, dict] = {}
    for record in records:
        for item in record.get("evidence") or []:
            if item and item.get("id"):
                sources.setdefault(item["id"], _source_row(item, org_id))
    return {"rows": rows, "sources": list(sources.values())}


async def _entity_count(org_id: str, user: dict, binding: Any) -> dict[str, Any]:
    """A count, plus the evidence behind the things counted.

    A number is a factual claim too, so it carries the same traceability as a
    statement rather than appearing as an unsourced figure.
    """
    where, params = _entity_where(binding, "e")
    records = await _run(
        f"""
        MATCH (e:Entity)
        WHERE e.org_id = $org_id AND e.status = 'confirmed'
          AND {_knowledge_scope('e')}
          {where}
        OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
        WHERE ev.org_id = $org_id AND {_evidence_scope('ev')}
        WITH e, collect(DISTINCT ev) AS ev_list
        WHERE size(ev_list) > 0
        UNWIND ev_list AS ev
        WITH collect(DISTINCT e.id) AS entity_ids, collect(DISTINCT ev) AS evidence
        RETURN size(entity_ids) AS value, entity_ids AS entity_ids,
               [item IN evidence WHERE item IS NOT NULL | item.id] AS source_ids,
               {_EVIDENCE_PROJECTION} AS evidence
        """,
        {"org_id": org_id, **_scope_params(user), **params},
    )
    if not records:
        return {"value": 0, "rows": [], "sources": []}

    record = records[0]
    sources = [
        _source_row(item, org_id)
        for item in (record.get("evidence") or [])[:12]
        if item and item.get("id")
    ]
    return {
        "value": record.get("value") or 0,
        "rows": [],
        "sources": sources,
        "entity_ids": record.get("entity_ids") or [],
        "source_ids": record.get("source_ids") or [],
    }


async def _entity_fact(org_id: str, user: dict, binding: Any) -> dict[str, Any]:
    """The confirmed fact that answers a question, with its evidence.

    Deliberately not a lookup of an arbitrary property name: the graph stores
    statements, so inventing a `duration` field would return nothing useful.
    """
    where, params = _entity_where(binding, "e")
    terms = " ".join(part for part in [binding.entity_name, binding.field] if part)
    records = await _run(
        f"""
        MATCH (e:Entity)
        WHERE e.org_id = $org_id AND e.status = 'confirmed'
          AND {_knowledge_scope('e')}
          AND toLower(coalesce(e.statement, '')) CONTAINS toLower($subject)
          {where}
        OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
        WHERE ev.org_id = $org_id AND {_evidence_scope('ev')}
        WITH e, collect(DISTINCT ev) AS evidence,
             CASE WHEN toLower(coalesce(e.statement, '')) CONTAINS toLower($terms)
                  THEN 1 ELSE 0 END AS exact
        WHERE size(evidence) > 0
        ORDER BY exact DESC, e.confirmed_at DESC
        LIMIT 1
        RETURN e.id AS id, e.entity_type AS entity_type, e.statement AS statement,
               e.detail AS detail, e.confidence AS confidence,
               e.department_ids AS department_ids, e.created_at AS created_at,
               [item IN evidence WHERE item IS NOT NULL | item.id] AS source_ids,
               {_EVIDENCE_PROJECTION} AS evidence
        """,
        {
            "org_id": org_id,
            "subject": binding.entity_name,
            "terms": terms,
            **_scope_params(user),
            **params,
        },
    )
    if not records:
        return {"value": None, "rows": [], "sources": []}
    row = _entity_row(records[0])
    sources = [
        _source_row(item, org_id)
        for item in (records[0].get("evidence") or [])
        if item and item.get("id")
    ]
    return {"value": row["statement"], "rows": [row], "sources": sources}


async def _aggregate(
    org_id: str, user: dict, binding: Any, *, dimension: str
) -> dict[str, Any]:
    """Group confirmed knowledge by a fixed dimension.

    Grouping happens after the scope predicate, so a bucket count can never
    reveal that knowledge exists which the viewer may not read. Each bucket
    carries the evidence behind it, so no number is shown uncited.
    """
    where, params = _entity_where(binding, "e")
    property_name = "entity_type" if dimension == "type" else "confidence"
    records = await _run(
        f"""
        MATCH (e:Entity)
        WHERE e.org_id = $org_id AND e.status = 'confirmed'
          AND {_knowledge_scope('e')}
          {where}
        OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
        WHERE ev.org_id = $org_id AND {_evidence_scope('ev')}
        WITH e, collect(DISTINCT ev) AS ev_list
        WHERE size(ev_list) > 0
        UNWIND ev_list AS ev
        WITH coalesce(e.{property_name}, 'unspecified') AS bucket,
             e.id AS entity_id, ev
        WITH bucket, collect(DISTINCT entity_id) AS entity_ids,
             collect(DISTINCT ev) AS evidence
        RETURN bucket AS bucket, size(entity_ids) AS total,
               entity_ids AS entity_ids,
               [item IN evidence WHERE item IS NOT NULL | item.id] AS source_ids,
               {_EVIDENCE_PROJECTION} AS evidence
        ORDER BY total DESC
        LIMIT $limit
        """,
        {
            "org_id": org_id,
            "limit": binding.limit,
            **_scope_params(user),
            **params,
        },
    )

    rows = []
    sources: dict[str, dict] = {}
    for record in records:
        rows.append({
            "label": record["bucket"],
            "value": record["total"],
            "entity_ids": record.get("entity_ids") or [],
            "source_ids": record.get("source_ids") or [],
        })
        for item in record.get("evidence") or []:
            if item and item.get("id"):
                sources.setdefault(item["id"], _source_row(item, org_id))
    return {
        "rows": rows,
        "sources": list(sources.values()),
        "value": sum(row["value"] for row in rows),
    }


async def _relationship_list(org_id: str, user: dict, binding: Any) -> dict[str, Any]:
    """Relationships between confirmed facts, cited from both endpoints."""
    where, params = _entity_where(binding, "a")
    records = await _run(
        f"""
        MATCH (a:Entity)-[r]->(b:Entity)
        WHERE a.org_id = $org_id AND b.org_id = $org_id
          AND a.status = 'confirmed' AND b.status = 'confirmed'
          AND {_knowledge_scope('a')} AND {_knowledge_scope('b')}
          {where}
        WITH a, r, b
        OPTIONAL MATCH (a)-[:CITED_BY]->(ea:Evidence)
        WHERE ea.org_id = $org_id AND {_evidence_scope('ea')}
        WITH a, r, b, collect(DISTINCT ea) AS from_evidence
        OPTIONAL MATCH (b)-[:CITED_BY]->(eb:Evidence)
        WHERE eb.org_id = $org_id AND {_evidence_scope('eb')}
        WITH a, r, b, from_evidence, collect(DISTINCT eb) AS to_evidence
        WHERE size(from_evidence) > 0 AND size(to_evidence) > 0
        WITH a, r, b, from_evidence + to_evidence AS evidence
        LIMIT $limit
        RETURN a.id AS from_id, a.statement AS from_statement,
               a.entity_type AS from_type, type(r) AS relation,
               b.id AS to_id, b.statement AS to_statement,
               b.entity_type AS to_type,
               [item IN evidence WHERE item IS NOT NULL | item.id] AS source_ids,
               {_EVIDENCE_PROJECTION} AS evidence
        """,
        {
            "org_id": org_id,
            "limit": binding.limit,
            **_scope_params(user),
            **params,
        },
    )
    rows = []
    sources: dict[str, dict] = {}
    for record in records:
        rows.append({
            "from_id": record["from_id"],
            "from_statement": record["from_statement"] or "",
            "from_type": record["from_type"] or "Fact",
            "relation": (record["relation"] or "RELATED").replace("_", " ").title(),
            "to_id": record["to_id"],
            "to_statement": record["to_statement"] or "",
            "to_type": record["to_type"] or "Fact",
            "source_ids": list(dict.fromkeys(record.get("source_ids") or [])),
        })
        for item in record.get("evidence") or []:
            if item and item.get("id"):
                sources.setdefault(item["id"], _source_row(item, org_id))
    return {"rows": rows, "sources": list(sources.values())}


async def _timeline_events(org_id: str, user: dict, binding: Any) -> dict[str, Any]:
    where, params = _entity_where(binding, "e")
    records = await _run(
        f"""
        MATCH (e:Entity)
        WHERE e.org_id = $org_id AND e.status = 'confirmed'
          AND {_knowledge_scope('e')}
          AND coalesce(e.confirmed_at, e.created_at) IS NOT NULL
          {where}
        OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
        WHERE ev.org_id = $org_id AND {_evidence_scope('ev')}
        WITH e, collect(DISTINCT ev) AS evidence,
             coalesce(e.confirmed_at, e.created_at) AS occurred_at
        WHERE size(evidence) > 0
        ORDER BY occurred_at DESC
        LIMIT $limit
        RETURN e.id AS id, e.entity_type AS entity_type, e.statement AS statement,
               occurred_at AS occurred_at,
               [item IN evidence WHERE item IS NOT NULL | item.id] AS source_ids,
               {_EVIDENCE_PROJECTION} AS evidence
        """,
        {
            "org_id": org_id,
            "limit": binding.limit,
            **_scope_params(user),
            **params,
        },
    )
    rows = [
        {
            "id": record["id"],
            "entity_type": record["entity_type"] or "Fact",
            "statement": record["statement"] or "",
            "occurred_at": str(record["occurred_at"]) if record["occurred_at"] else None,
            "source_ids": [item for item in (record.get("source_ids") or []) if item],
        }
        for record in records
    ]
    sources: dict[str, dict] = {}
    for record in records:
        for item in record.get("evidence") or []:
            if item and item.get("id"):
                sources.setdefault(item["id"], _source_row(item, org_id))
    return {"rows": rows, "sources": list(sources.values())}


async def _evidence_list(
    org_id: str, user: dict, binding: Any, *, group_by_source: bool
) -> dict[str, Any]:
    """Evidence reachable from confirmed, visible knowledge.

    Requiring a confirmed entity keeps Canvas consistent with Chat: a passage
    is only shown when it actually backs a trusted fact.
    """
    where, params = _entity_where(binding, "e")
    records = await _run(
        f"""
        MATCH (e:Entity)-[:CITED_BY]->(ev:Evidence)
        WHERE e.org_id = $org_id AND e.status = 'confirmed'
          AND {_knowledge_scope('e')}
          AND ev.org_id = $org_id AND {_evidence_scope('ev')}
          {where}
        WITH DISTINCT ev, e
        ORDER BY ev.source_date DESC
        LIMIT $limit
        RETURN ev.id AS id, ev.title AS title, ev.reference AS reference,
               ev.excerpt AS excerpt, ev.page AS page,
               ev.line_start AS line_start, ev.line_end AS line_end,
               e.statement AS supports
        """,
        {
            "org_id": org_id,
            "limit": binding.limit,
            **_scope_params(user),
            **params,
        },
    )

    sources = []
    seen: set[str] = set()
    for record in records:
        if not record.get("id") or record["id"] in seen:
            continue
        seen.add(record["id"])
        sources.append({
            **_source_row(record, org_id),
            "supports": record.get("supports") or "",
            # A passage is its own citation.
            "source_ids": [record["id"]],
        })

    if not group_by_source:
        return {"rows": sources, "sources": sources}

    grouped: dict[str, dict[str, Any]] = {}
    for source in sources:
        key = source["reference"] or source["title"]
        bucket = grouped.setdefault(
            key,
            {
                "reference": key,
                "title": source["title"],
                "passages": [],
                "source_ids": [],
            },
        )
        bucket["passages"].append(source)
        bucket["source_ids"].append(source["id"])
    return {"rows": list(grouped.values()), "sources": sources}


# ------------------------------------------------------------ resolution ----


async def resolve_component(
    org_id: str, user: dict, component: Any, *, row_budget: int
) -> dict[str, Any]:
    """Resolve one component's binding, or explain why it is empty."""
    binding = component.binding
    query = binding.query

    if query == "none":
        return {"kind": "none", "rows": [], "sources": []}

    effective = min(binding.limit, max(0, row_budget))
    if effective <= 0:
        return {
            "kind": query,
            "rows": [],
            "sources": [],
            "truncated": True,
            "note": "This view reached its data budget before this component.",
        }

    # A copy so the stored spec is never mutated by rendering.
    scoped_binding = binding.model_copy(update={"limit": effective})

    try:
        if query == "entity_list":
            payload = await _entity_list(org_id, user, scoped_binding)
        elif query == "entity_count":
            payload = await _entity_count(org_id, user, scoped_binding)
        elif query == "entity_fact":
            payload = await _entity_fact(org_id, user, scoped_binding)
        elif query == "aggregate_by_type":
            payload = await _aggregate(org_id, user, scoped_binding, dimension="type")
        elif query == "aggregate_by_confidence":
            payload = await _aggregate(
                org_id, user, scoped_binding, dimension="confidence"
            )
        elif query == "relationship_list":
            payload = await _relationship_list(org_id, user, scoped_binding)
        elif query == "timeline_events":
            payload = await _timeline_events(org_id, user, scoped_binding)
        elif query == "evidence_list":
            payload = await _evidence_list(
                org_id, user, scoped_binding, group_by_source=False
            )
        elif query == "source_passages":
            payload = await _evidence_list(
                org_id, user, scoped_binding, group_by_source=True
            )
        else:
            # Unreachable while the spec validates, and harmless if reached.
            return {"kind": query, "rows": [], "sources": [], "error": "unsupported query"}
    except Exception as error:  # noqa: BLE001 - one component must not break the page
        return {
            "kind": query,
            "rows": [],
            "sources": [],
            "error": "This component could not be loaded.",
            "detail": str(error)[:200],
        }

    return {
        "kind": query,
        "rows": payload.get("rows", []),
        "sources": payload.get("sources", []) if component.options.show_sources else [],
        "value": payload.get("value"),
        "truncated": len(payload.get("rows", [])) >= effective,
    }


async def resolve_spec(org_id: str, user: dict, spec: Any) -> dict[str, Any]:
    """Resolve every binding in a canvas against the caller's own permissions.

    Components are resolved concurrently but share one row budget, so a wide
    canvas cannot pull an unbounded slice of the graph in a single render.
    """
    budgets: list[int] = []
    remaining = CANVAS_ROW_BUDGET
    for component in spec.components:
        if component.binding.query == "none":
            budgets.append(0)
            continue
        allocation = min(component.binding.limit, remaining)
        budgets.append(max(0, allocation))
        remaining = max(0, remaining - allocation)

    resolved = await asyncio.gather(*[
        resolve_component(org_id, user, component, row_budget=budget)
        for component, budget in zip(spec.components, budgets)
    ])

    data = {
        component.id: payload
        for component, payload in zip(spec.components, resolved)
    }
    all_sources: dict[str, dict] = {}
    for payload in resolved:
        for source in payload.get("sources", []):
            if source.get("id"):
                all_sources.setdefault(source["id"], source)

    return {
        "components": data,
        "sources": list(all_sources.values()),
        "row_budget": CANVAS_ROW_BUDGET,
        # The exact scope this render ran under, so the view is explainable.
        "permission_scope": {
            "access_all_departments": bool(user.get("access_all_departments")),
            "department_ids": user.get("department_ids") or [],
            "confirmed_only": True,
        },
    }
