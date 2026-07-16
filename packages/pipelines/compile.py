"""
Objective Compiler

LangGraph pipeline: plain-language objective → governed WorkPack with cited context.

Pipeline: interpret → select → draft → validate → persist
"""

import sys
sys.path.append("../../packages")

from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
import yaml

from langgraph.graph import Graph, END
from core.models import WorkPack
from core.llm import call_llm_json, Model
from core.embeddings import embed
from core.graph import GraphClient
from core.queries import BrainQueries


class CompilerState(TypedDict):
    """State for compiler pipeline."""
    org_id: str
    objective: str
    objective_embedding: Optional[List[float]]
    context: Dict[str, Any]  # Retrieved entities
    selected: Dict[str, List[Dict]]  # Selected relevant entities
    work_pack: Optional[Dict[str, Any]]
    work_pack_id: Optional[str]
    error: Optional[str]


async def interpret_node(state: CompilerState) -> CompilerState:
    """
    Node 1: Interpret objective.

    Embed the objective and perform hybrid search across all entity types.
    Expand to 2-hop neighborhood for full context.
    """
    objective = state["objective"]
    org_id = state["org_id"]

    print(f"[Compiler] Interpreting objective: {objective[:60]}...")

    try:
        # Embed objective
        embedding = await embed(objective)
        state["objective_embedding"] = embedding

        # Hybrid search across all types
        results = await BrainQueries.hybrid_search(
            org_id=org_id,
            query_text=objective,
            query_embedding=embedding,
            k=20,
            status="confirmed"
        )

        if not results:
            state["error"] = "No relevant context found in the brain"
            return state

        # Get seed IDs
        seed_ids = [r["id"] for r in results[:10]]  # Top 10

        # Expand to 2-hop neighborhood
        expansion = await BrainQueries.context_expansion(
            org_id=org_id,
            seed_ids=seed_ids,
            max_hops=2
        )

        state["context"] = expansion
        print(f"[Compiler] Retrieved {len(expansion['seeds'])} seeds, {len(expansion['neighbors'])} neighbors")

    except Exception as e:
        state["error"] = f"Interpretation failed: {e}"

    return state


async def select_node(state: CompilerState) -> CompilerState:
    """
    Node 2: Select relevant context.

    LLM picks the subset of entities that are actually relevant to the objective.
    Every selected item must keep its entity ID for citation integrity.
    """
    if state.get("error"):
        return state

    objective = state["objective"]
    context = state["context"]

    all_entities = context.get("seeds", []) + context.get("neighbors", [])

    if not all_entities:
        state["error"] = "No context to select from"
        return state

    print(f"[Compiler] Selecting from {len(all_entities)} entities...")

    # Build entity list for LLM
    entity_list = []
    for i, entity in enumerate(all_entities):
        entity_list.append({
            "index": i,
            "id": entity["id"],
            "type": entity["entity_type"],
            "statement": entity["statement"],
            "detail": entity.get("detail", "")
        })

    system_prompt = """You are selecting relevant context for a software engineering work package.

Given an objective and a list of company facts (goals, decisions, constraints, etc.),
select ONLY the facts that are directly relevant to the objective.

Return JSON:
{
  "parent_goal": {"index": ..., "id": "...", "statement": "..."},
  "decisions": [{"index": ..., "id": "...", "statement": "..."}],
  "constraints": [{"index": ..., "id": "...", "statement": "..."}],
  "customer_requests": [{"index": ..., "id": "...", "statement": "..."}]
}

Rules:
- Every item MUST include "index" (from input list) and "id" (entity ID)
- Only include facts that directly apply to this objective
- Constraints are especially important (governance)
- If no items for a category, return empty array
"""

    prompt = f"""Objective:
{objective}

Available context:
{yaml.dump(entity_list, sort_keys=False)}

Select relevant facts:"""

    try:
        result = await call_llm_json(
            prompt=prompt,
            system=system_prompt,
            model=Model.SONNET,
            max_tokens=2000
        )

        state["selected"] = result
        print(f"[Compiler] Selected: {len(result.get('decisions', []))} decisions, {len(result.get('constraints', []))} constraints")

    except Exception as e:
        state["error"] = f"Selection failed: {e}"

    return state


async def draft_node(state: CompilerState) -> CompilerState:
    """
    Node 3: Draft Work Pack.

    LLM produces the WorkPack YAML with requirements, permissions, verification steps.
    """
    if state.get("error"):
        return state

    objective = state["objective"]
    selected = state["selected"]

    print(f"[Compiler] Drafting Work Pack...")

    system_prompt = """You are drafting a governed software engineering Work Pack.

Given an objective and selected context (decisions, constraints, etc.), produce a detailed work package.

Return JSON matching this schema:
{
  "title": "Short title",
  "objective": {
    "description": "What needs to be built",
    "parent_goal_id": "goal entity ID if applicable"
  },
  "business_context": {
    "reason": "Why this work matters",
    "affected_customers": ["entity IDs of customer requests"]
  },
  "requirements": ["Specific requirement 1", "Specific requirement 2", ...],
  "relevant_decisions": [{"id": "entity-id", "statement": "..."}],
  "constraints": [{"id": "entity-id", "statement": "...", "enforcement": "block|approve"}],
  "permissions": {
    "allowed": ["modify code", "add tests", "create PR"],
    "approval_required": ["derived from constraints with enforcement=approve"]
  },
  "verification": ["tests pass", "docs updated", "constraint XYZ verified", ...]
}

Rules:
- Requirements must be specific and testable
- Permissions.approval_required must match constraints with enforcement='approve'
- Verification steps must include checking constraints
- Every entity reference must include its ID
"""

    # Simplify selected for prompt
    prompt_context = {
        "parent_goal": selected.get("parent_goal"),
        "decisions": selected.get("decisions", []),
        "constraints": selected.get("constraints", []),
        "customer_requests": selected.get("customer_requests", [])
    }

    prompt = f"""Objective:
{objective}

Context:
{yaml.dump(prompt_context, sort_keys=False)}

Draft Work Pack:"""

    try:
        result = await call_llm_json(
            prompt=prompt,
            system=system_prompt,
            model=Model.SONNET,
            max_tokens=3000
        )

        # Generate Work Pack ID
        wp_id = f"WP-{uuid4().hex[:8]}"
        result["id"] = wp_id
        result["status"] = "draft"

        state["work_pack"] = result
        state["work_pack_id"] = wp_id

        print(f"[Compiler] Drafted Work Pack: {wp_id}")

    except Exception as e:
        state["error"] = f"Drafting failed: {e}"

    return state


async def validate_node(state: CompilerState) -> CompilerState:
    """
    Node 4: Validate Work Pack.

    Check that:
    - Every referenced entity ID exists and is confirmed
    - Constraints section is non-empty or explicitly 'none_apply'
    - Required fields are present
    """
    if state.get("error"):
        return state

    work_pack = state["work_pack"]
    org_id = state["org_id"]

    print(f"[Compiler] Validating Work Pack...")

    try:
        # Collect all entity IDs
        entity_ids = set()

        parent_goal_id = work_pack.get("objective", {}).get("parent_goal_id")
        if parent_goal_id:
            entity_ids.add(parent_goal_id)

        for customer_id in work_pack.get("business_context", {}).get("affected_customers", []):
            entity_ids.add(customer_id)

        for decision in work_pack.get("relevant_decisions", []):
            entity_ids.add(decision.get("id"))

        for constraint in work_pack.get("constraints", []):
            entity_ids.add(constraint.get("id"))

        # Verify all IDs exist
        if entity_ids:
            query = """
            MATCH (e:Entity {org_id: $org_id, status: 'confirmed'})
            WHERE e.id IN $entity_ids
            RETURN count(e) as found
            """

            result = await GraphClient.run_query(query, {
                "org_id": org_id,
                "entity_ids": list(entity_ids)
            })

            found = result[0]["found"] if result else 0

            if found < len(entity_ids):
                state["error"] = f"Validation failed: {len(entity_ids) - found} entity IDs not found"
                return state

        # Check constraints section
        constraints = work_pack.get("constraints", [])
        if not constraints:
            state["error"] = "Validation failed: constraints section is empty (must have constraints or explicit 'none_apply')"
            return state

        print(f"[Compiler] Validation passed: {len(entity_ids)} entities verified")

    except Exception as e:
        state["error"] = f"Validation failed: {e}"

    return state


async def persist_node(state: CompilerState) -> CompilerState:
    """
    Node 5: Persist Work Pack to Neo4j.

    Creates WorkPack node with IMPLEMENTS/GOVERNED_BY/INFORMED_BY edges.
    """
    if state.get("error"):
        return state

    work_pack = state["work_pack"]
    org_id = state["org_id"]
    wp_id = state["work_pack_id"]

    print(f"[Compiler] Persisting Work Pack {wp_id}...")

    try:
        # Create WorkPack node
        wp_yaml = yaml.dump(work_pack, sort_keys=False)

        create_query = """
        CREATE (w:WorkPack {
            id: $id,
            org_id: $org_id,
            title: $title,
            yaml_content: $yaml_content,
            status: 'draft',
            created_at: datetime()
        })
        """

        await GraphClient.run_query(create_query, {
            "id": wp_id,
            "org_id": org_id,
            "title": work_pack.get("title", ""),
            "yaml_content": wp_yaml
        })

        # Create IMPLEMENTS edge (parent goal)
        parent_goal_id = work_pack.get("objective", {}).get("parent_goal_id")
        if parent_goal_id:
            implements_query = """
            MATCH (w:WorkPack {id: $wp_id})
            MATCH (g:Goal {id: $goal_id, org_id: $org_id})
            MERGE (w)-[:IMPLEMENTS]->(g)
            """
            await GraphClient.run_query(implements_query, {
                "wp_id": wp_id,
                "goal_id": parent_goal_id,
                "org_id": org_id
            })

        # Create GOVERNED_BY edges (constraints)
        for constraint in work_pack.get("constraints", []):
            constraint_id = constraint.get("id")
            if constraint_id:
                governed_query = """
                MATCH (w:WorkPack {id: $wp_id})
                MATCH (c:Constraint {id: $constraint_id, org_id: $org_id})
                MERGE (w)-[:GOVERNED_BY]->(c)
                """
                await GraphClient.run_query(governed_query, {
                    "wp_id": wp_id,
                    "constraint_id": constraint_id,
                    "org_id": org_id
                })

        # Create INFORMED_BY edges (decisions)
        for decision in work_pack.get("relevant_decisions", []):
            decision_id = decision.get("id")
            if decision_id:
                informed_query = """
                MATCH (w:WorkPack {id: $wp_id})
                MATCH (d:Decision {id: $decision_id, org_id: $org_id})
                MERGE (w)-[:INFORMED_BY]->(d)
                """
                await GraphClient.run_query(informed_query, {
                    "wp_id": wp_id,
                    "decision_id": decision_id,
                    "org_id": org_id
                })

        print(f"[Compiler] Work Pack {wp_id} persisted successfully")

    except Exception as e:
        state["error"] = f"Persist failed: {e}"

    return state


def build_compiler_graph() -> Graph:
    """Build the compiler pipeline graph."""
    workflow = Graph()

    workflow.add_node("interpret", interpret_node)
    workflow.add_node("select", select_node)
    workflow.add_node("draft", draft_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("persist", persist_node)

    workflow.set_entry_point("interpret")
    workflow.add_edge("interpret", "select")
    workflow.add_edge("select", "draft")
    workflow.add_edge("draft", "validate")
    workflow.add_edge("validate", "persist")
    workflow.add_edge("persist", END)

    return workflow.compile()


async def compile_objective(objective: str, org_id: str = "default-org") -> Dict[str, Any]:
    """
    Compile a plain-language objective into a governed Work Pack.

    Args:
        objective: Plain-language engineering objective
        org_id: Organization ID

    Returns:
        Dict with work_pack (YAML dict), work_pack_id, and markdown
    """
    graph = build_compiler_graph()

    initial_state: CompilerState = {
        "org_id": org_id,
        "objective": objective,
        "objective_embedding": None,
        "context": {},
        "selected": {},
        "work_pack": None,
        "work_pack_id": None,
        "error": None
    }

    try:
        final_state = await graph.ainvoke(initial_state)

        if final_state.get("error"):
            return {
                "success": False,
                "error": final_state["error"]
            }

        work_pack = final_state["work_pack"]
        wp_id = final_state["work_pack_id"]

        # Render as Markdown
        markdown = render_work_pack_markdown(work_pack)

        return {
            "success": True,
            "work_pack_id": wp_id,
            "work_pack": work_pack,
            "markdown": markdown
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def render_work_pack_markdown(work_pack: Dict[str, Any]) -> str:
    """Render Work Pack as Markdown."""
    md = f"""# Work Pack: {work_pack.get('title', 'Untitled')}

**ID:** `{work_pack.get('id', 'N/A')}`
**Status:** {work_pack.get('status', 'draft')}

## Objective

{work_pack.get('objective', {}).get('description', '')}

"""

    # Business context
    context = work_pack.get('business_context', {})
    if context:
        md += f"""## Business Context

**Why:** {context.get('reason', '')}

"""

    # Requirements
    requirements = work_pack.get('requirements', [])
    if requirements:
        md += "## Requirements\n\n"
        for req in requirements:
            md += f"- {req}\n"
        md += "\n"

    # Decisions
    decisions = work_pack.get('relevant_decisions', [])
    if decisions:
        md += "## Relevant Decisions\n\n"
        for dec in decisions:
            md += f"- **{dec.get('statement', '')}**\n"
            md += f"  _Entity ID: `{dec.get('id', '')}`_\n\n"

    # Constraints
    constraints = work_pack.get('constraints', [])
    if constraints:
        md += "## Constraints\n\n"
        for con in constraints:
            enforcement = con.get('enforcement', 'approve')
            emoji = "🚫" if enforcement == "block" else "⏸️ "
            md += f"{emoji} **{con.get('statement', '')}**\n"
            md += f"  _Entity ID: `{con.get('id', '')}` • Enforcement: {enforcement}_\n\n"

    # Permissions
    permissions = work_pack.get('permissions', {})
    if permissions:
        md += "## Permissions\n\n"
        md += "**Allowed:**\n"
        for action in permissions.get('allowed', []):
            md += f"- ✅ {action}\n"
        md += "\n**Requires Approval:**\n"
        for action in permissions.get('approval_required', []):
            md += f"- ⏸️  {action}\n"
        md += "\n"

    # Verification
    verification = work_pack.get('verification', [])
    if verification:
        md += "## Verification\n\n"
        for step in verification:
            md += f"- [ ] {step}\n"
        md += "\n"

    return md


if __name__ == "__main__":
    import asyncio

    async def test():
        GraphClient.initialize()

        objective = "Add API key authentication for org-level access"

        result = await compile_objective(objective, org_id="test-org")

        if result["success"]:
            print("\n" + "="*60)
            print("WORK PACK COMPILED")
            print("="*60)
            print(result["markdown"])
        else:
            print(f"Error: {result['error']}")

        await GraphClient.close()

    asyncio.run(test())
