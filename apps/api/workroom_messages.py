"""The shared Workroom conversation.

A focused thread around one objective — not a chat replacement. Conversation
and activity stay separate on purpose:

* ``workroom_messages`` is what people and agents deliberately said.
* ``workroom_events`` is the immutable record of what happened.

A message never drives the agent by itself. Redirecting a run is an explicit
action a person takes, so a passing remark can never silently change what the
agent is doing.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import and_, func, or_, select

from database import (
    DepartmentMembership,
    OrganizationMembership,
    Workroom,
    WorkroomMember,
    WorkroomMessage,
    async_session,
)


ALLOWED_REFERENCE_KINDS = {"task", "run", "source", "artifact"}
MAX_REFERENCES = 8
MAX_MENTIONS = 12


def message_dict(message: WorkroomMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "workroom_id": message.workroom_id,
        "author_type": message.author_type,
        "author_user_id": message.author_user_id,
        "author_name": message.author_name,
        # A deleted message keeps its place in the thread without its content.
        "body": "" if message.deleted_at else message.body,
        "reply_to_message_id": message.reply_to_message_id,
        "references": message.references or [],
        "mentions": message.mentions or [],
        "edited_at": (
            f"{message.edited_at.isoformat()}Z" if message.edited_at else None
        ),
        "deleted": message.deleted_at is not None,
        "created_at": f"{message.created_at.isoformat()}Z",
    }


def normalize_references(raw: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Keep only well-formed pointers to things that live in this product."""
    references: list[dict[str, str]] = []
    for item in raw[:MAX_REFERENCES]:
        kind = str(item.get("kind", "")).strip()
        reference_id = str(item.get("id", "")).strip()
        if kind in ALLOWED_REFERENCE_KINDS and reference_id:
            references.append({
                "kind": kind,
                "id": reference_id[:120],
                "label": str(item.get("label") or "")[:200],
            })
    return references


async def resolve_mentions(
    org_id: str, room_id: str, user_ids: list[str]
) -> list[str]:
    """Keep only mentions of people who can actually see this room.

    That is broader than explicit membership — an organization-visible room
    has implicit viewers who are worth notifying — but never broader than the
    room's own visibility rules. Mentioning someone must not tell them a
    private room exists.
    """
    candidates = list(dict.fromkeys(user_ids))[:MAX_MENTIONS]
    if not candidates:
        return []

    async with async_session() as session:
        room = await session.get(Workroom, room_id)
        if room is None or room.org_id != org_id:
            return []

        explicit = {
            member.user_id: member
            for member in (
                await session.execute(
                    select(WorkroomMember).where(
                        WorkroomMember.workroom_id == room_id,
                        WorkroomMember.user_id.in_(candidates),
                    )
                )
            ).scalars().all()
        }
        org_members = set((
            await session.execute(
                select(OrganizationMembership.user_id).where(
                    OrganizationMembership.org_id == org_id,
                    OrganizationMembership.status == "active",
                    OrganizationMembership.user_id.in_(candidates),
                )
            )
        ).scalars().all())

        required_departments = set(room.department_ids or [])
        department_access: dict[str, set[str]] = {}
        if required_departments:
            rows = (
                await session.execute(
                    select(
                        DepartmentMembership.user_id,
                        DepartmentMembership.department_id,
                    ).where(
                        DepartmentMembership.org_id == org_id,
                        DepartmentMembership.user_id.in_(candidates),
                    )
                )
            ).all()
            for user_id, department_id in rows:
                department_access.setdefault(user_id, set()).add(department_id)

    visibility = room.visibility or "organization"
    resolved: list[str] = []
    for user_id in candidates:
        member = explicit.get(user_id)
        if member is not None and member.status == "active":
            resolved.append(user_id)
            continue
        # Everything below still requires organization membership.
        if user_id not in org_members:
            continue
        if visibility == "private":
            continue
        if visibility == "departments" and not required_departments.issubset(
            department_access.get(user_id, set())
        ):
            continue
        resolved.append(user_id)
    return sorted(set(resolved))


async def list_messages(
    org_id: str,
    room_id: str,
    *,
    after_id: Optional[str] = None,
    before_id: Optional[str] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return a bounded keyset page.

    Initial and ``before`` requests read backwards from the newest messages,
    while ``after`` remains an ascending incremental-update cursor.
    """
    async with async_session() as session:
        filters = [
            WorkroomMessage.org_id == org_id,
            WorkroomMessage.workroom_id == room_id,
        ]
        anchor = None
        if after_id:
            anchor = await session.get(WorkroomMessage, after_id)
        elif before_id:
            anchor = await session.get(WorkroomMessage, before_id)
        if anchor is not None and (
            anchor.org_id != org_id or anchor.workroom_id != room_id
        ):
            anchor = None

        if after_id and anchor is not None:
            filters.append(or_(
                WorkroomMessage.created_at > anchor.created_at,
                and_(
                    WorkroomMessage.created_at == anchor.created_at,
                    WorkroomMessage.id > anchor.id,
                ),
            ))
            rows = (
                await session.execute(
                    select(WorkroomMessage)
                    .where(*filters)
                    .order_by(WorkroomMessage.created_at, WorkroomMessage.id)
                    .limit(limit + 1)
                )
            ).scalars().all()
            has_more = len(rows) > limit
            messages = rows[:limit]
            next_after = messages[-1].id if has_more and messages else None
            next_before = None
        else:
            if before_id and anchor is not None:
                filters.append(or_(
                    WorkroomMessage.created_at < anchor.created_at,
                    and_(
                        WorkroomMessage.created_at == anchor.created_at,
                        WorkroomMessage.id < anchor.id,
                    ),
                ))
            rows = (
                await session.execute(
                    select(WorkroomMessage)
                    .where(*filters)
                    .order_by(
                        WorkroomMessage.created_at.desc(),
                        WorkroomMessage.id.desc(),
                    )
                    .limit(limit + 1)
                )
            ).scalars().all()
            has_more = len(rows) > limit
            messages = list(reversed(rows[:limit]))
            next_before = messages[0].id if has_more and messages else None
            next_after = None

        total = int((
            await session.execute(
                select(func.count())
                .select_from(WorkroomMessage)
                .where(
                    WorkroomMessage.org_id == org_id,
                    WorkroomMessage.workroom_id == room_id,
                )
            )
        ).scalar_one())
        return {
            "messages": [message_dict(message) for message in messages],
            "total": total,
            "has_more": has_more,
            "next_before": next_before,
            "next_after": next_after,
        }


async def create_message(
    *,
    org_id: str,
    room_id: str,
    author_type: str,
    author_user_id: Optional[str],
    author_name: str,
    body: str,
    reply_to_message_id: Optional[str],
    references: list[dict[str, Any]],
    mentions: list[str],
) -> Optional[dict[str, Any]]:
    now = datetime.utcnow()
    async with async_session() as session:
        room = await session.get(Workroom, room_id)
        if room is None or room.org_id != org_id:
            return None
        if reply_to_message_id:
            parent = await session.get(WorkroomMessage, reply_to_message_id)
            # A reply may only point at a message in the same room.
            if (
                parent is None
                or parent.workroom_id != room_id
                or parent.org_id != org_id
            ):
                reply_to_message_id = None

        message = WorkroomMessage(
            id=str(uuid4()),
            workroom_id=room_id,
            org_id=org_id,
            author_type=author_type,
            author_user_id=author_user_id,
            author_name=author_name[:120],
            body=body,
            reply_to_message_id=reply_to_message_id,
            references=references,
            mentions=mentions,
            created_at=now,
        )
        session.add(message)
        room.updated_at = now
        await session.commit()
        return message_dict(message)


async def edit_message(
    org_id: str, room_id: str, message_id: str, *, user_id: str, body: str
) -> Optional[dict[str, Any]]:
    """Only the author may edit, and only their own human message."""
    async with async_session() as session:
        message = await session.get(WorkroomMessage, message_id)
        if (
            message is None
            or message.org_id != org_id
            or message.workroom_id != room_id
            or message.deleted_at is not None
            or message.author_type != "human"
            or message.author_user_id != user_id
        ):
            return None
        message.body = body
        message.edited_at = datetime.utcnow()
        await session.commit()
        return message_dict(message)


async def delete_message(
    org_id: str, room_id: str, message_id: str, *, user_id: str, can_manage: bool
) -> Optional[dict[str, Any]]:
    """Redact content while leaving the thread's shape intact."""
    async with async_session() as session:
        message = await session.get(WorkroomMessage, message_id)
        if (
            message is None
            or message.org_id != org_id
            or message.workroom_id != room_id
            or message.deleted_at is not None
        ):
            return None
        if not can_manage and message.author_user_id != user_id:
            return None
        message.deleted_at = datetime.utcnow()
        await session.commit()
        return message_dict(message)
