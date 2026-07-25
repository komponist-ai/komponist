"""Governed context packs: what the Workroom agent is allowed to read.

The effective context for a run is:

    authorized knowledge in the room's scope
      MINUS explicitly excluded items
      with explicitly pinned items guaranteed present and ranked first

One deliberate deviation from a naive reading of "INTERSECT included": pinning
a single source does **not** discard everything else. Pins are additive
emphasis, not a whitelist, because a destructive "pin" would silently starve
the agent of context a person never meant to drop. Exclusions are absolute.

Nothing here can widen access. Pins are filtered against the permission-scoped
retrieval result, so pinning an id the room may not read has no effect, and
the preview never reveals the title or existence of an inaccessible source.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import delete, select

from database import WorkroomContextItem, async_session


def context_item_dict(item: WorkroomContextItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "workroom_id": item.workroom_id,
        "item_kind": item.item_kind,
        "reference_id": item.reference_id,
        "mode": item.mode,
        "label": item.label,
        "added_by_user_id": item.added_by_user_id,
        "created_at": f"{item.created_at.isoformat()}Z",
        "updated_at": f"{item.updated_at.isoformat()}Z",
    }


async def list_context_items(org_id: str, room_id: str) -> list[WorkroomContextItem]:
    async with async_session() as session:
        return list((
            await session.execute(
                select(WorkroomContextItem)
                .where(
                    WorkroomContextItem.org_id == org_id,
                    WorkroomContextItem.workroom_id == room_id,
                )
                .order_by(WorkroomContextItem.created_at)
            )
        ).scalars().all())


async def set_context_item(
    *,
    org_id: str,
    room_id: str,
    item_kind: str,
    reference_id: str,
    mode: str,
    label: Optional[str],
    user_id: str,
) -> dict[str, Any]:
    """Pin or exclude one item. Re-setting the same item flips its mode."""
    now = datetime.utcnow()
    async with async_session() as session:
        existing = (
            await session.execute(
                select(WorkroomContextItem).where(
                    WorkroomContextItem.workroom_id == room_id,
                    WorkroomContextItem.item_kind == item_kind,
                    WorkroomContextItem.reference_id == reference_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.mode = mode
            existing.label = label
            existing.updated_at = now
            item = existing
        else:
            item = WorkroomContextItem(
                id=str(uuid4()),
                workroom_id=room_id,
                org_id=org_id,
                item_kind=item_kind,
                reference_id=reference_id,
                mode=mode,
                label=label,
                added_by_user_id=user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(item)
        await session.commit()
        return context_item_dict(item)


async def remove_context_item(
    org_id: str, room_id: str, item_id: str
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        item = await session.get(WorkroomContextItem, item_id)
        if (
            item is None
            or item.org_id != org_id
            or item.workroom_id != room_id
        ):
            return None
        snapshot = context_item_dict(item)
        await session.execute(
            delete(WorkroomContextItem).where(WorkroomContextItem.id == item_id)
        )
        await session.commit()
        return snapshot


def split_context_items(
    items: list[WorkroomContextItem],
) -> tuple[set[str], set[str], set[str], set[str]]:
    """Return (pinned entities, pinned sources, excluded entities, excluded sources)."""
    pinned_entities = {
        item.reference_id
        for item in items
        if item.mode == "include" and item.item_kind == "entity"
    }
    pinned_sources = {
        item.reference_id
        for item in items
        if item.mode == "include" and item.item_kind == "source"
    }
    excluded_entities = {
        item.reference_id
        for item in items
        if item.mode == "exclude" and item.item_kind == "entity"
    }
    excluded_sources = {
        item.reference_id
        for item in items
        if item.mode == "exclude" and item.item_kind == "source"
    }
    return pinned_entities, pinned_sources, excluded_entities, excluded_sources


def apply_context_pack(
    entities: list[dict],
    sources: list[dict],
    items: list[WorkroomContextItem],
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    """Filter permission-scoped retrieval down to the room's context pack.

    ``entities`` and ``sources`` must already be permission-scoped: this
    function only removes and reorders, so it can never widen access.
    """
    pinned_entities, pinned_sources, excluded_entities, excluded_sources = (
        split_context_items(items)
    )

    kept_entities = [
        entity for entity in entities if entity["id"] not in excluded_entities
    ]
    # Dropping a source also drops it as a citation on any fact that used it.
    for entity in kept_entities:
        if entity.get("evidence"):
            entity["evidence"] = [
                evidence
                for evidence in entity["evidence"]
                if evidence.get("id") not in excluded_sources
            ]
    kept_entities = [entity for entity in kept_entities if entity.get("evidence")]
    kept_sources = [
        source for source in sources if source["id"] not in excluded_sources
    ]

    def rank(items_to_rank: list[dict], pinned: set[str]) -> list[dict]:
        # Stable partition keeps relevance order inside each group.
        return (
            [item for item in items_to_rank if item["id"] in pinned]
            + [item for item in items_to_rank if item["id"] not in pinned]
        )

    ordered_entities = rank(kept_entities, pinned_entities)
    ordered_sources = rank(kept_sources, pinned_sources)

    applied = {
        "pinned_entity_ids": sorted(
            pinned_entities & {entity["id"] for entity in ordered_entities}
        ),
        "pinned_source_ids": sorted(
            pinned_sources & {source["id"] for source in ordered_sources}
        ),
        "excluded_entity_ids": sorted(excluded_entities),
        "excluded_source_ids": sorted(excluded_sources),
        "excluded_entity_count": len(entities) - len(kept_entities),
        "excluded_source_count": len(sources) - len(kept_sources),
        # Pins the room cannot actually read are reported as a count only.
        "unresolved_pin_count": len(
            (pinned_entities - {entity["id"] for entity in ordered_entities})
            | (pinned_sources - {source["id"] for source in ordered_sources})
        ),
    }
    return ordered_entities, ordered_sources, applied


def build_context_snapshot(
    *,
    entities: list[dict],
    sources: list[dict],
    room: Any,
    applied: dict[str, Any],
    scope: dict[str, Any],
) -> dict[str, Any]:
    """An immutable record of exactly what the agent read, and under what scope."""
    findings = [
        {
            "id": entity["id"],
            "type": entity.get("entity_type") or "Fact",
            "statement": entity.get("statement") or entity.get("detail") or "",
            "source_ids": [
                evidence["id"]
                for evidence in (entity.get("evidence") or [])
                if evidence.get("id")
            ],
        }
        for entity in entities[:12]
    ]
    snapshot_sources = [
        {
            key: source.get(key)
            for key in (
                "id", "title", "reference", "excerpt", "page",
                "line_start", "line_end", "komponist_path", "source_date",
            )
        }
        for source in sources[:12]
    ]
    return {
        "findings": findings,
        "sources": snapshot_sources,
        "entity_ids": [entity["id"] for entity in entities],
        "evidence_ids": [source["id"] for source in sources],
        "context_pack": applied,
        # The exact permission scope this run was executed under.
        "permission_scope": scope,
        "captured_at": f"{datetime.utcnow().isoformat()}Z",
    }


async def build_context_preview(
    *,
    org_id: str,
    room: Any,
    entities: list[dict],
    sources: list[dict],
    items: list[WorkroomContextItem],
    accessible_department_ids: list[str],
) -> dict[str, Any]:
    """What the agent would see right now, without starting a run."""
    ordered_entities, ordered_sources, applied = apply_context_pack(
        entities, sources, items
    )
    last_update = max(
        (item.updated_at for item in items), default=None
    )

    return {
        "workroom_id": room.id,
        "visibility": room.visibility or "organization",
        "department_ids": room.department_ids or [],
        # Departments the room is scoped to that the viewer can also reach.
        "included_department_ids": sorted(
            set(room.department_ids or []) & set(accessible_department_ids)
        ),
        "confirmed_fact_count": len(ordered_entities),
        "accessible_source_count": len(ordered_sources),
        "pinned": [
            context_item_dict(item) for item in items if item.mode == "include"
        ],
        "excluded": [
            context_item_dict(item) for item in items if item.mode == "exclude"
        ],
        "excluded_fact_count": applied["excluded_entity_count"],
        "excluded_source_count": applied["excluded_source_count"],
        # Only a count. Naming an inaccessible source would leak its existence.
        "omitted_inaccessible_count": applied["unresolved_pin_count"],
        "last_context_update_at": (
            f"{last_update.isoformat()}Z" if last_update else None
        ),
        "sources": [
            {
                "id": source["id"],
                "title": source.get("title"),
                "reference": source.get("reference"),
                "excerpt": source.get("excerpt"),
                "komponist_path": source.get("komponist_path"),
                "pinned": source["id"] in set(applied["pinned_source_ids"]),
            }
            for source in ordered_sources[:20]
        ],
    }
