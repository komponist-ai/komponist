"""
Write-back loop integration.

Connects executed work back to the brain:
- PR merge events -> WorkPack status updates
- PR bodies -> extraction pipeline
- report_result -> WorkPack relationships
"""

import sys
sys.path.append("../../../packages")

from typing import Dict, Any, Optional
from datetime import datetime

from core.graph import GraphClient
from core.models import SourceItem, SourceType
from pipelines.extract import extract_from_source


async def handle_pr_merged_writeback(pr_data: Dict[str, Any], org_id: str):
    """
    Handle PR merge for write-back loop.

    1. Extract WorkPack ID from PR body/branch (e.g., WP-abc123)
    2. Update WorkPack status
    3. Extract decisions from PR body/comments
    4. Link evidence to WorkPack

    Args:
        pr_data: GitHub PR data
        org_id: Organization ID
    """
    pr_number = pr_data.get("number")
    pr_title = pr_data.get("title", "")
    pr_body = pr_data.get("body", "")
    pr_url = pr_data.get("html_url", "")
    branch_name = pr_data.get("head", {}).get("ref", "")
    merged_at = pr_data.get("merged_at")

    print(f"[Writeback] Processing merged PR#{pr_number}: {pr_title}")

    # 1. Look for WorkPack ID in body or branch
    work_pack_id = None

    # Check PR body for WP-xxx
    import re
    wp_pattern = r'WP-[a-f0-9]{8}'
    matches = re.findall(wp_pattern, pr_body, re.IGNORECASE)
    if matches:
        work_pack_id = matches[0]

    # Check branch name
    if not work_pack_id:
        matches = re.findall(wp_pattern, branch_name, re.IGNORECASE)
        if matches:
            work_pack_id = matches[0]

    # 2. Update WorkPack status if found
    if work_pack_id:
        try:
            update_query = """
            MATCH (w:WorkPack {id: $work_pack_id, org_id: $org_id})
            SET w.status = 'ready_for_review',
                w.pr_number = $pr_number,
                w.pr_url = $pr_url,
                w.completed_at = datetime($merged_at),
                w.updated_at = datetime()
            RETURN w.id as id, w.status as status
            """

            result = await GraphClient.run_query(update_query, {
                "work_pack_id": work_pack_id,
                "org_id": org_id,
                "pr_number": pr_number,
                "pr_url": pr_url,
                "merged_at": merged_at
            })

            if result:
                print(f"[Writeback] Updated WorkPack {work_pack_id} -> ready_for_review")
            else:
                print(f"[Writeback] WorkPack {work_pack_id} not found")

        except Exception as e:
            print(f"[Writeback] Error updating WorkPack: {e}")

    # 3. Extract decisions from PR body
    # Look for decision markers (e.g., "Decision:", "We decided", "Going with")
    decision_indicators = [
        "decision:", "we decided", "going with", "chose to", "opted for",
        "after evaluating", "after discussion"
    ]

    pr_has_decisions = any(indicator in pr_body.lower() for indicator in decision_indicators)

    if pr_has_decisions and len(pr_body) > 100:
        # Create SourceItem for extraction
        source_item = SourceItem(
            org_id=org_id,
            source=SourceType.GITHUB,
            kind="pr_merged",
            title=pr_title,
            body=pr_body,
            author=pr_data.get("user", {}).get("login"),
            url=pr_url,
            reference=f"PR#{pr_number}",
            source_date=datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
        )

        try:
            result = await extract_from_source(source_item)
            if result["success"] and result["entities_created"] > 0:
                print(f"[Writeback] Extracted {result['entities_created']} decisions from PR#{pr_number}")

                # Link extracted entities to WorkPack if we have one
                if work_pack_id and result["entity_ids"]:
                    for entity_id in result["entity_ids"]:
                        link_query = """
                        MATCH (w:WorkPack {id: $work_pack_id, org_id: $org_id})
                        MATCH (e:Entity {id: $entity_id, org_id: $org_id})
                        MERGE (e)-[:DERIVED_FROM]->(w)
                        """
                        await GraphClient.run_query(link_query, {
                            "work_pack_id": work_pack_id,
                            "entity_id": entity_id,
                            "org_id": org_id
                        })
                    print(f"[Writeback] Linked {len(result['entity_ids'])} entities to WorkPack {work_pack_id}")

        except Exception as e:
            print(f"[Writeback] Error extracting from PR: {e}")


async def link_report_result_to_workpack(
    entity_ids: list[str],
    work_pack_id: str,
    org_id: str,
    deviations: Optional[list[str]] = None,
    unresolved_questions: Optional[list[str]] = None
):
    """
    Link report_result entities to WorkPack.

    Args:
        entity_ids: Created entity IDs from report_result
        work_pack_id: WorkPack ID
        org_id: Organization ID
        deviations: Deviations from plan
        unresolved_questions: Questions that came up
    """
    print(f"[Writeback] Linking report to WorkPack {work_pack_id}")

    try:
        # Link entities
        for entity_id in entity_ids:
            link_query = """
            MATCH (w:WorkPack {id: $work_pack_id, org_id: $org_id})
            MATCH (e:Entity {id: $entity_id, org_id: $org_id})
            MERGE (e)-[:REPORTED_IN]->(w)
            """
            await GraphClient.run_query(link_query, {
                "work_pack_id": work_pack_id,
                "entity_id": entity_id,
                "org_id": org_id
            })

        # Store deviations and questions as WorkPack properties
        if deviations or unresolved_questions:
            update_query = """
            MATCH (w:WorkPack {id: $work_pack_id, org_id: $org_id})
            SET w.deviations = $deviations,
                w.unresolved_questions = $unresolved_questions,
                w.updated_at = datetime()
            RETURN w.id as id
            """
            await GraphClient.run_query(update_query, {
                "work_pack_id": work_pack_id,
                "org_id": org_id,
                "deviations": deviations or [],
                "unresolved_questions": unresolved_questions or []
            })

        print(f"[Writeback] Linked {len(entity_ids)} entities to WorkPack")

    except Exception as e:
        print(f"[Writeback] Error linking to WorkPack: {e}")


async def generate_weekly_digest(org_id: str) -> Dict[str, Any]:
    """
    Generate weekly digest of brain activity.

    Returns summary of:
    - Facts confirmed
    - Decisions superseded
    - Violations blocked
    - Work Packs completed

    Args:
        org_id: Organization ID

    Returns:
        Dict with digest data
    """
    print(f"[Writeback] Generating weekly digest for {org_id}")

    try:
        # Facts confirmed this week
        confirmed_query = """
        MATCH (e:Entity {org_id: $org_id, status: 'confirmed'})
        WHERE e.confirmed_at >= datetime() - duration('P7D')
        RETURN
            count(e) as total,
            collect({type: e.entity_type, statement: e.statement})[..10] as recent
        """

        confirmed = await GraphClient.run_query(confirmed_query, {"org_id": org_id})
        confirmed_count = confirmed[0]["total"] if confirmed else 0
        confirmed_recent = confirmed[0]["recent"] if confirmed else []

        # Decisions superseded this week
        superseded_query = """
        MATCH (old:Decision {org_id: $org_id, status: 'superseded'})
        MATCH (new:Decision)-[:SUPERSEDES]->(old)
        WHERE old.updated_at >= datetime() - duration('P7D')
        RETURN
            count(old) as total,
            collect({
                old_statement: old.statement,
                new_statement: new.statement
            })[..5] as recent
        """

        superseded = await GraphClient.run_query(superseded_query, {"org_id": org_id})
        superseded_count = superseded[0]["total"] if superseded else 0
        superseded_recent = superseded[0]["recent"] if superseded else []

        # Violations blocked (from tool_calls table)
        from database import async_session, ToolCall
        from sqlalchemy import select, func
        from datetime import timedelta

        async with async_session() as session:
            week_ago = datetime.utcnow() - timedelta(days=7)

            # Blocked verdicts
            blocked_result = await session.execute(
                select(func.count(ToolCall.id))
                .where(ToolCall.org_id == org_id)
                .where(ToolCall.tool == "check_constraint")
                .where(ToolCall.verdict == "blocked")
                .where(ToolCall.created_at >= week_ago)
            )
            blocked_count = blocked_result.scalar() or 0

            # Approvals required
            approval_result = await session.execute(
                select(func.count(ToolCall.id))
                .where(ToolCall.org_id == org_id)
                .where(ToolCall.tool == "check_constraint")
                .where(ToolCall.verdict == "approval_required")
                .where(ToolCall.created_at >= week_ago)
            )
            approval_count = approval_result.scalar() or 0

        # Work Packs completed
        workpack_query = """
        MATCH (w:WorkPack {org_id: $org_id})
        WHERE w.completed_at >= datetime() - duration('P7D')
        RETURN
            count(w) as total,
            collect({id: w.id, title: w.title})[..5] as recent
        """

        workpacks = await GraphClient.run_query(workpack_query, {"org_id": org_id})
        workpack_count = workpacks[0]["total"] if workpacks else 0
        workpack_recent = workpacks[0]["recent"] if workpacks else []

        digest = {
            "org_id": org_id,
            "week_start": (datetime.utcnow() - timedelta(days=7)).isoformat(),
            "week_end": datetime.utcnow().isoformat(),
            "facts_confirmed": {
                "count": confirmed_count,
                "recent": confirmed_recent
            },
            "decisions_superseded": {
                "count": superseded_count,
                "recent": superseded_recent
            },
            "governance": {
                "blocked": blocked_count,
                "approval_required": approval_count,
                "total_governed": blocked_count + approval_count
            },
            "work_packs_completed": {
                "count": workpack_count,
                "recent": workpack_recent
            }
        }

        print(f"[Writeback] Digest generated: {confirmed_count} confirmed, {blocked_count} blocked")

        return digest

    except Exception as e:
        print(f"[Writeback] Error generating digest: {e}")
        return {"error": str(e)}


def format_digest_for_slack(digest: Dict[str, Any]) -> str:
    """
    Format weekly digest for Slack.

    Args:
        digest: Digest data

    Returns:
        Formatted Slack message (markdown)
    """
    facts = digest["facts_confirmed"]
    decisions = digest["decisions_superseded"]
    governance = digest["governance"]
    workpacks = digest["work_packs_completed"]

    message = f"""📊 *Weekly Brain Digest*

*Facts Confirmed:* {facts['count']}
"""

    if facts['recent']:
        message += "Recent:\n"
        for fact in facts['recent'][:3]:
            message += f"  • [{fact['type']}] {fact['statement'][:60]}...\n"

    message += f"""
*Decisions Superseded:* {decisions['count']}
"""

    if decisions['recent']:
        for dec in decisions['recent'][:2]:
            message += f"  • {dec['old_statement'][:50]}... → {dec['new_statement'][:50]}...\n"

    message += f"""
*Governance:*
  • 🚫 Blocked: {governance['blocked']} violations prevented
  • ⏸️  Approvals: {governance['approval_required']} requests
  • Total: {governance['total_governed']} actions governed

*Work Packs Completed:* {workpacks['count']}
"""

    if workpacks['recent']:
        for wp in workpacks['recent'][:3]:
            message += f"  • {wp['id']}: {wp['title']}\n"

    message += f"""
_View the brain: http://localhost:3000/entities_
"""

    return message


async def post_digest_to_slack(org_id: str, channel_id: str):
    """
    Generate and post weekly digest to Slack.

    Args:
        org_id: Organization ID
        channel_id: Slack channel ID
    """
    import os
    import httpx

    slack_token = os.getenv("SLACK_BOT_TOKEN")
    if not slack_token:
        print("[Writeback] SLACK_BOT_TOKEN not set, skipping digest")
        return

    # Generate digest
    digest = await generate_weekly_digest(org_id)

    if "error" in digest:
        print(f"[Writeback] Failed to generate digest: {digest['error']}")
        return

    # Format for Slack
    message = format_digest_for_slack(digest)

    # Post to Slack
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {slack_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "channel": channel_id,
                    "text": message,
                    "mrkdwn": True
                }
            )

            result = response.json()
            if result.get("ok"):
                print(f"[Writeback] Posted weekly digest to Slack channel {channel_id}")
            else:
                print(f"[Writeback] Failed to post to Slack: {result.get('error')}")

    except Exception as e:
        print(f"[Writeback] Error posting to Slack: {e}")


if __name__ == "__main__":
    import asyncio

    async def test_digest():
        GraphClient.initialize()

        digest = await generate_weekly_digest("test-org")
        print("\nWeekly Digest:")
        print("=" * 60)
        print(format_digest_for_slack(digest))

        await GraphClient.close()

    asyncio.run(test_digest())
