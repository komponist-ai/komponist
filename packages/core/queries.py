"""
Core Graph Queries

The 5 fundamental queries that power Komponist:
1. Hybrid search (vector + fulltext)
2. Active decisions (supersedes-aware)
3. Context expansion (1-2 hop neighborhood)
4. Supersedes chain (decision history)
5. Applicable constraints (global + project-scoped)
"""

from typing import List, Dict, Any, Optional
from core.graph import GraphClient


class BrainQueries:
    """Core queries for the Komponist brain."""

    @staticmethod
    async def hybrid_search(
        org_id: str,
        query_text: Optional[str] = None,
        query_embedding: Optional[List[float]] = None,
        entity_types: Optional[List[str]] = None,
        k: int = 8,
        status: str = "confirmed"
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: vector + fulltext, fused with reciprocal rank fusion.

        Args:
            org_id: Organization ID
            query_text: Text query for fulltext search
            query_embedding: Embedding vector for similarity search (1536 dims)
            entity_types: Filter by entity types (e.g., ["Decision", "Goal"])
            k: Number of results per search method
            status: Entity status filter (default "confirmed")

        Returns:
            List of entities with scores, sorted by score descending
        """
        entities: Dict[str, Dict[str, Any]] = {}
        rank_scores: Dict[str, float] = {}

        def add_ranked(items: List[Dict[str, Any]]) -> None:
            # Raw vector and Lucene scores are not comparable. Reciprocal rank
            # fusion combines their ordering without pretending the scales match.
            for rank, item in enumerate(items, 1):
                entity_id = item["id"]
                entities.setdefault(entity_id, item)
                rank_scores[entity_id] = (
                    rank_scores.get(entity_id, 0.0) + 1.0 / (60 + rank)
                )

        # Vector search (if embedding provided)
        if query_embedding:
            vector_query = """
            CALL db.index.vector.queryNodes('entity_embedding', $k, $query_embedding)
            YIELD node, score
            WHERE node.org_id = $org_id
              AND node.status = $status
              AND (size($entity_types) = 0 OR node.entity_type IN $entity_types)
            RETURN
                node.id as id,
                node.entity_type as entity_type,
                node.statement as statement,
                node.detail as detail,
                node.status as status,
                node.confidence as confidence,
                node.created_at as created_at,
                node.confirmed_at as confirmed_at,
                score
            ORDER BY score DESC
            LIMIT $k
            """

            vector_results = await GraphClient.run_query(
                vector_query,
                {
                    "org_id": org_id,
                    "status": status,
                    "k": k,
                    "query_embedding": query_embedding,
                    "entity_types": entity_types or [],
                }
            )
            add_ranked(vector_results)

        # Fulltext search (if text provided)
        if query_text:
            fulltext_query = """
            CALL db.index.fulltext.queryNodes('entity_text', $query_text)
            YIELD node, score
            WHERE node.org_id = $org_id
              AND node.status = $status
              AND (size($entity_types) = 0 OR node.entity_type IN $entity_types)
            RETURN
                node.id as id,
                node.entity_type as entity_type,
                node.statement as statement,
                node.detail as detail,
                node.status as status,
                node.confidence as confidence,
                node.created_at as created_at,
                node.confirmed_at as confirmed_at,
                score
            ORDER BY score DESC
            LIMIT $k
            """

            fulltext_results = await GraphClient.run_query(
                fulltext_query,
                {
                    "org_id": org_id,
                    "status": status,
                    "query_text": query_text,
                    "k": k,
                    "entity_types": entity_types or [],
                }
            )
            add_ranked(fulltext_results)

        # Dedupe and sort by fused rank score.
        dedupe_results = [
            {**entity, "score": rank_scores[entity_id]}
            for entity_id, entity in entities.items()
        ]
        dedupe_results.sort(key=lambda x: x["score"], reverse=True)

        return dedupe_results

    @staticmethod
    async def active_decisions(
        org_id: str,
        topic_embedding: Optional[List[float]] = None,
        k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get active (non-superseded) decisions.

        Supersedes-aware: a decision is active if no confirmed decision supersedes it.

        Args:
            org_id: Organization ID
            topic_embedding: Optional filter by similarity to topic
            k: Limit results

        Returns:
            List of active decisions with evidence
        """
        if topic_embedding:
            # Filter by topic similarity
            query = """
            CALL db.index.vector.queryNodes('entity_embedding', $k * 2, $topic_embedding)
            YIELD node as d, score
            WHERE d.org_id = $org_id
              AND d.entity_type = 'Decision'
              AND d.status = 'confirmed'
              AND NOT EXISTS {
                  MATCH (newer:Decision {status: 'confirmed'})-[:SUPERSEDES]->(d)
              }
            WITH d, score
            ORDER BY score DESC
            LIMIT $k
            OPTIONAL MATCH (d)-[:CITED_BY]->(e:Evidence)
            RETURN
                d.id as id,
                d.statement as statement,
                d.detail as detail,
                d.confidence as confidence,
                d.confirmed_at as confirmed_at,
                collect(e{.id, .source, .reference, .url, .excerpt}) as evidence,
                score
            ORDER BY score DESC
            """
            params = {"org_id": org_id, "k": k, "topic_embedding": topic_embedding}
        else:
            # All active decisions
            query = """
            MATCH (d:Decision {org_id: $org_id, entity_type: 'Decision', status: 'confirmed'})
            WHERE NOT EXISTS {
                MATCH (newer:Decision {status: 'confirmed'})-[:SUPERSEDES]->(d)
            }
            OPTIONAL MATCH (d)-[:CITED_BY]->(e:Evidence)
            RETURN
                d.id as id,
                d.statement as statement,
                d.detail as detail,
                d.confidence as confidence,
                d.confirmed_at as confirmed_at,
                collect(e{.id, .source, .reference, .url, .excerpt}) as evidence
            ORDER BY d.confirmed_at DESC
            LIMIT $k
            """
            params = {"org_id": org_id, "k": k}

        results = await GraphClient.run_query(query, params)
        return results

    @staticmethod
    async def context_expansion(
        org_id: str,
        seed_ids: List[str],
        max_hops: int = 2
    ) -> Dict[str, Any]:
        """
        Expand context from seed entities.

        Given seed entity IDs, pull the 1-N hop neighborhood with evidence.

        Args:
            org_id: Organization ID
            seed_ids: Starting entity IDs
            max_hops: Maximum relationship hops (1 or 2)

        Returns:
            Dict with seeds, neighbors, and evidence
        """
        query = f"""
        MATCH (e:Entity)
        WHERE e.id IN $seed_ids AND e.org_id = $org_id
        WITH e
        OPTIONAL MATCH path = (e)-[r:SUPERSEDES|AFFECTS|SUPPORTS|ADVANCES|CONSTRAINS|RELATES_TO*1..{max_hops}]-(n:Entity)
        WHERE n.status = 'confirmed'
        WITH e, collect(DISTINCT n) as neighbors, collect(DISTINCT path) as paths
        OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
        WITH e, neighbors, paths, collect(DISTINCT ev) as evidence
        UNWIND neighbors as neighbor
        OPTIONAL MATCH (neighbor)-[:CITED_BY]->(nev:Evidence)
        RETURN
            e{{.id, .entity_type, .statement, .detail, .status, .confidence}} as seed,
            evidence{{.id, .source, .reference, .url, .excerpt}} as seed_evidence,
            collect(DISTINCT neighbor{{.id, .entity_type, .statement, .detail, .status}}) as neighbors,
            collect(DISTINCT nev{{.id, .source, .reference, .url, .excerpt}}) as neighbor_evidence
        """

        results = await GraphClient.run_query(
            query,
            {"org_id": org_id, "seed_ids": seed_ids}
        )

        if not results:
            return {"seeds": [], "neighbors": [], "evidence": []}

        # Aggregate results
        seeds = []
        all_neighbors = []
        all_evidence = []

        for r in results:
            seeds.append(r["seed"])
            all_evidence.extend(r.get("seed_evidence", []))
            all_neighbors.extend(r.get("neighbors", []))
            all_evidence.extend(r.get("neighbor_evidence", []))

        # Dedupe
        unique_neighbors = {n["id"]: n for n in all_neighbors if n}
        unique_evidence = {e["id"]: e for e in all_evidence if e}

        return {
            "seeds": seeds,
            "neighbors": list(unique_neighbors.values()),
            "evidence": list(unique_evidence.values())
        }

    @staticmethod
    async def supersedes_chain(
        decision_id: str,
        org_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get the supersedes chain for a decision (history view).

        Returns the path from the given decision to the latest decision that supersedes it.

        Args:
            decision_id: Starting decision ID
            org_id: Organization ID

        Returns:
            List of decisions in chain, oldest to newest
        """
        query = """
        MATCH path = (d:Decision {id: $decision_id, org_id: $org_id})<-[:SUPERSEDES*0..]-(latest:Decision)
        WHERE NOT EXISTS {
            MATCH (newer:Decision)-[:SUPERSEDES]->(latest)
        }
        WITH nodes(path) as chain
        UNWIND chain as decision
        OPTIONAL MATCH (decision)-[:CITED_BY]->(e:Evidence)
        RETURN
            decision.id as id,
            decision.statement as statement,
            decision.detail as detail,
            decision.status as status,
            decision.confidence as confidence,
            decision.created_at as created_at,
            decision.confirmed_at as confirmed_at,
            collect(e{.id, .source, .reference, .url, .excerpt}) as evidence
        ORDER BY decision.created_at ASC
        """

        results = await GraphClient.run_query(
            query,
            {"decision_id": decision_id, "org_id": org_id}
        )

        return results

    @staticmethod
    async def applicable_constraints(
        org_id: str,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get applicable constraints: global + project-scoped.

        Args:
            org_id: Organization ID
            project_id: Optional project ID for scoped constraints

        Returns:
            List of applicable constraints with evidence
        """
        if project_id:
            query = """
            MATCH (c:Constraint {org_id: $org_id, entity_type: 'Constraint', status: 'confirmed'})
            WHERE NOT EXISTS {
                MATCH (c)-[:CONSTRAINS]->(:Project)
            } OR EXISTS {
                MATCH (c)-[:CONSTRAINS]->(:Project {id: $project_id})
            }
            OPTIONAL MATCH (c)-[:CITED_BY]->(e:Evidence)
            RETURN
                c.id as id,
                c.statement as statement,
                c.detail as detail,
                c.enforcement as enforcement,
                c.confidence as confidence,
                c.confirmed_at as confirmed_at,
                collect(e{.id, .source, .reference, .url, .excerpt}) as evidence
            ORDER BY c.enforcement DESC, c.confirmed_at DESC
            """
            params = {"org_id": org_id, "project_id": project_id}
        else:
            # Global only
            query = """
            MATCH (c:Constraint {org_id: $org_id, entity_type: 'Constraint', status: 'confirmed'})
            WHERE NOT EXISTS {
                MATCH (c)-[:CONSTRAINS]->(:Project)
            }
            OPTIONAL MATCH (c)-[:CITED_BY]->(e:Evidence)
            RETURN
                c.id as id,
                c.statement as statement,
                c.detail as detail,
                c.enforcement as enforcement,
                c.confidence as confidence,
                c.confirmed_at as confirmed_at,
                collect(e{.id, .source, .reference, .url, .excerpt}) as evidence
            ORDER BY c.enforcement DESC, c.confirmed_at DESC
            """
            params = {"org_id": org_id}

        results = await GraphClient.run_query(query, params)
        return results


# Convenience alias
queries = BrainQueries
