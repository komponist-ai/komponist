"""
Evaluation fixtures for extraction pipeline.

15-20 real-world examples with expected outputs.
"""

from datetime import datetime
from core.models import SourceItem, SourceType


# Fixture 1: Clear architectural decision
FIXTURE_ADR_NEO4J = SourceItem(
    org_id="eval-org",
    source=SourceType.GITHUB,
    kind="adr_file",
    title="ADR-001-use-neo4j.md",
    body="""# ADR 001: Use Neo4j as the Company Brain

## Status
Accepted

## Context
We need a database for the Komponist company brain that can handle:
- Graph queries (relationships between goals, decisions, constraints)
- Vector similarity search for semantic retrieval
- High write throughput from multiple integrations

## Decision
We will use Neo4j 5.x with native vector indexes as the sole brain storage.

## Consequences
- No separate vector database needed (Pinecone/Weaviate eliminated)
- Embedding dimension is fixed at initialization (1024 for the active model)
- Graph traversal queries are native and fast
- Operational complexity reduced to one database
""",
    author="sovin",
    url="https://github.com/aistos/aistos/blob/main/docs/adr/001-neo4j.md",
    reference="ADR-001",
    source_date=datetime(2026, 7, 1, 12, 0, 0)
)

EXPECTED_ADR_NEO4J = [
    {
        "type": "Decision",
        "statement": "Use Neo4j 5.x with native vector indexes as the sole company brain storage",
        "confidence": "high",
        "excerpt": "We will use Neo4j 5.x with native vector indexes as the sole brain storage."
    }
]


# Fixture 2: Superseded decision (PR discussion)
FIXTURE_PR_AUTH = SourceItem(
    org_id="eval-org",
    source=SourceType.GITHUB,
    kind="pr_merged",
    title="Switch auth to WorkOS",
    body="""## Summary
Replaces internal auth service with WorkOS for enterprise identity.

## Why
- Legal flagged our session token storage for compliance
- Building SAML/OIDC from scratch is 3+ months
- WorkOS handles directory sync + audit logs out of the box

## Supersedes
This replaces the decision to build an internal auth service (discussed in issue #42).

cc @alice @bob
""",
    author="charlie",
    url="https://github.com/aistos/aistos/pull/142",
    reference="PR#142",
    source_date=datetime(2026, 7, 5, 14, 30, 0)
)

EXPECTED_PR_AUTH = [
    {
        "type": "Decision",
        "statement": "Use WorkOS for enterprise identity management",
        "confidence": "high",
        "relations_hint": [{"relation": "SUPERSEDES", "target_hint": "internal auth service"}]
    }
]


# Fixture 3: Customer request (Linear issue)
FIXTURE_ISSUE_BULK_IMPORT = SourceItem(
    org_id="eval-org",
    source=SourceType.LINEAR,
    kind="issue",
    title="[Acme Corp] Need bulk import for existing decisions",
    body="""Customer: Acme Corp (design partner)

They have 200+ ADRs in a Notion database and want to seed the brain without reviewing one-by-one.

Request:
- CSV/JSON import for bulk decision upload
- Auto-classify confidence based on ADR status
- Batch to max 50/minute to avoid overwhelming review queue

Priority: High (blocking their onboarding)
""",
    author="product",
    url="https://linear.app/komponist/issue/ENG-88",
    reference="ENG-88",
    source_date=datetime(2026, 7, 8, 9, 15, 0)
)

EXPECTED_ISSUE_BULK_IMPORT = [
    {
        "type": "CustomerRequest",
        "statement": "Acme Corp requests bulk import for 200+ existing ADRs from Notion",
        "confidence": "high",
        "excerpt": "They have 200+ ADRs in a Notion database and want to seed the brain without reviewing one-by-one."
    }
]


# Fixture 4: Constraint (compliance requirement)
FIXTURE_SLACK_COMPLIANCE = SourceItem(
    org_id="eval-org",
    source=SourceType.SLACK,
    kind="thread",
    title="Decision: no auto-confirm extractions",
    body="""alice: Should we auto-confirm facts from ADR files? They're already vetted.

bob: Hard no. Legal was clear: every fact in the brain needs human review for liability reasons.

alice: Even for re-ingesting existing ADRs after a schema change?

bob: Even then. The review queue is fast enough. Make it a constraint.

charlie: +1, this is core to the trust model anyway
""",
    author="alice",
    url="https://slack.com/archives/C123/p1720512345",
    reference="slack:C123/1720512345",
    source_date=datetime(2026, 7, 9, 16, 45, 0)
)

EXPECTED_SLACK_COMPLIANCE = [
    {
        "type": "Constraint",
        "statement": "Never auto-confirm extracted entities without human review",
        "confidence": "high",
        "excerpt": "Legal was clear: every fact in the brain needs human review for liability reasons."
    }
]


# Fixture 5: Company goal (Linear project)
FIXTURE_GOAL_YC = SourceItem(
    org_id="eval-org",
    source=SourceType.LINEAR,
    kind="issue",
    title="Ship MVP and apply to YC",
    body="""Q3 2026 goal: Launch with 10 design partners and apply to Y Combinator.

Milestones:
1. 3 integrations live (GitHub, Slack, Linear)
2. MCP server installed by 10 teams
3. ≥1 constraint violation blocked per team
4. 3-minute demo video showing full loop

Target application deadline: August 15
""",
    author="founder",
    url="https://linear.app/komponist/project/Q3-GOAL",
    reference="Q3-GOAL",
    source_date=datetime(2026, 7, 1, 8, 0, 0)
)

EXPECTED_GOAL_YC = [
    {
        "type": "Goal",
        "statement": "Launch Komponist MVP with 10 design partners and apply to Y Combinator by August 15",
        "confidence": "high"
    }
]


# Fixture 6: Noise (should classify as not relevant)
FIXTURE_NOISE_STANDUP = SourceItem(
    org_id="eval-org",
    source=SourceType.SLACK,
    kind="thread",
    title="Daily standup check-in",
    body="""alice: Working on the MCP server today, should have search_company_context done by EOD

bob: Debugging the Neo4j vector index issue, will pair with charlie this afternoon

charlie: Finishing up the review queue UI, added keyboard shortcuts

alice: Nice! Let me know when you want a demo
""",
    author="alice",
    url="https://slack.com/archives/C456/p1720598400",
    reference="slack:C456/1720598400",
    source_date=datetime(2026, 7, 10, 9, 0, 0)
)

EXPECTED_NOISE_STANDUP = []  # Should classify as not relevant


# Fixture 7: Multiple facts in one source
FIXTURE_PR_REFACTOR = SourceItem(
    org_id="eval-org",
    source=SourceType.GITHUB,
    kind="pr_merged",
    title="Refactor extraction pipeline",
    body="""## Changes
- Split extraction into 6 LangGraph nodes (classify -> extract -> embed -> dedup -> link -> persist)
- Use Haiku for classification (cheap gate)
- Use Sonnet for extraction (quality)

## Decisions
1. Dedup threshold set to 0.92 for exact matches, 0.80 for possible duplicates
2. Bias toward "allowed" in constraint checking to avoid false positives (ADR-010)
3. Store unresolved relation hints as entity properties for reviewer

## Performance
Extraction latency reduced from 8s to 3s avg.
""",
    author="dev",
    url="https://github.com/aistos/aistos/pull/156",
    reference="PR#156",
    source_date=datetime(2026, 7, 10, 11, 30, 0)
)

EXPECTED_PR_REFACTOR = [
    {
        "type": "Decision",
        "statement": "Set entity deduplication threshold to 0.92 for exact matches and 0.80 for possible duplicates",
        "confidence": "high"
    },
    {
        "type": "Decision",
        "statement": "Bias constraint checking toward allowed verdicts to minimize false positives",
        "confidence": "high",
        "relations_hint": [{"relation": "REFERENCES", "target_hint": "ADR-010"}]
    }
]


# All fixtures
FIXTURES = [
    (FIXTURE_ADR_NEO4J, EXPECTED_ADR_NEO4J),
    (FIXTURE_PR_AUTH, EXPECTED_PR_AUTH),
    (FIXTURE_ISSUE_BULK_IMPORT, EXPECTED_ISSUE_BULK_IMPORT),
    (FIXTURE_SLACK_COMPLIANCE, EXPECTED_SLACK_COMPLIANCE),
    (FIXTURE_GOAL_YC, EXPECTED_GOAL_YC),
    (FIXTURE_NOISE_STANDUP, EXPECTED_NOISE_STANDUP),
    (FIXTURE_PR_REFACTOR, EXPECTED_PR_REFACTOR),
]


def run_eval():
    """Run extraction pipeline on all fixtures and score results."""
    import asyncio
    from pipelines.extract import extract_from_source
    from core.graph import GraphClient

    async def evaluate():
        GraphClient.initialize()

        total = len(FIXTURES)
        passed = 0

        for i, (source_item, expected) in enumerate(FIXTURES, 1):
            print(f"\n{'='*60}")
            print(f"Fixture {i}/{total}: {source_item.title}")
            print(f"{'='*60}")

            result = await extract_from_source(source_item)

            if not result["success"]:
                print(f"❌ FAILED: {result['error']}")
                continue

            extracted_count = result["facts_extracted"]
            expected_count = len(expected)

            if extracted_count == expected_count:
                print(f"✅ PASSED: Extracted {extracted_count} facts (expected {expected_count})")
                passed += 1
            else:
                print(f"⚠️  PARTIAL: Extracted {extracted_count} facts (expected {expected_count})")
                passed += 0.5

        await GraphClient.close()

        print(f"\n{'='*60}")
        print(f"SCORE: {passed}/{total} ({passed/total*100:.1f}%)")
        print(f"{'='*60}")

        return passed / total

    score = asyncio.run(evaluate())
    return score


if __name__ == "__main__":
    score = run_eval()
    print(f"\nFinal score: {score*100:.1f}%")
    print("Target: ≥70% for MVP")
