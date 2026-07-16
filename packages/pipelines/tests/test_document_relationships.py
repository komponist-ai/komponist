"""Tests for conservative relationships inferred within one document."""

import unittest

from pipelines.extract import infer_intra_document_relationships


def result(entity_id: str, entity_type: str, action: str = "create") -> dict:
    return {
        "action": action,
        "entity_id": entity_id,
        "fact": {"type": entity_type},
    }


class DocumentRelationshipTests(unittest.TestCase):
    def test_single_project_connects_document_facts(self) -> None:
        relationships = infer_intra_document_relationships([
            result("project-1", "Project"),
            result("goal-1", "Goal"),
            result("decision-1", "Decision"),
            result("constraint-1", "Constraint"),
        ])

        self.assertEqual(relationships, [
            {"source_id": "project-1", "target_id": "goal-1", "relation": "ADVANCES"},
            {"source_id": "decision-1", "target_id": "project-1", "relation": "AFFECTS"},
            {"source_id": "constraint-1", "target_id": "project-1", "relation": "CONSTRAINS"},
        ])

    def test_ambiguous_projects_do_not_create_speculative_edges(self) -> None:
        relationships = infer_intra_document_relationships([
            result("project-1", "Project"),
            result("project-2", "Project"),
            result("goal-1", "Goal"),
        ])

        self.assertEqual(relationships, [])

    def test_existing_entities_are_not_used_for_document_inference(self) -> None:
        relationships = infer_intra_document_relationships([
            result("project-1", "Project"),
            result("goal-1", "Goal", action="attach_evidence"),
        ])

        self.assertEqual(relationships, [])


if __name__ == "__main__":
    unittest.main()
