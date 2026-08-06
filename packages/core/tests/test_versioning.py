from core.versioning import (
    build_document_families,
    compare_documents,
    content_fingerprint,
    demo_document_versions,
    normalize_document_title,
)


def test_title_normalization_removes_platform_and_version_noise():
    assert normalize_document_title("Northstar Pilot FINAL v3.pptx") == "northstar pilot"
    assert normalize_document_title(None, "upload:Northstar Pilot copy.md:abc123") == "northstar pilot"


def test_content_identity_is_stable_for_trailing_whitespace():
    assert content_fingerprint("Decision: ship.  \n") == content_fingerprint("Decision: ship.")


def test_identical_content_groups_across_different_titles():
    documents = [
        {
            "id": "a", "title": "Strategy", "reference": "notion:a",
            "source": "notion", "source_date": "2026-01-01T00:00:00Z",
            "content_hash": "same", "claims": [],
        },
        {
            "id": "b", "title": "Board pack", "reference": "gdrive:b",
            "source": "google", "source_date": "2026-01-02T00:00:00Z",
            "content_hash": "same", "claims": [],
        },
    ]
    families = build_document_families(documents)
    assert len(families) == 1
    assert families[0]["version_count"] == 2
    assert families[0]["latest_version_id"] == "b"


def test_unrelated_documents_stay_in_separate_families():
    documents = [
        {
            "id": "a", "title": "Hiring plan", "reference": "notion:a",
            "source": "notion", "source_date": "2026-01-01T00:00:00Z",
            "content_hash": "one", "claims": [{"id": "goal-a", "entity_type": "Goal", "statement": "Hire two engineers."}],
        },
        {
            "id": "b", "title": "Security controls", "reference": "gdrive:b",
            "source": "google", "source_date": "2026-01-02T00:00:00Z",
            "content_hash": "two", "claims": [{"id": "constraint-b", "entity_type": "Constraint", "statement": "Require SSO."}],
        },
    ]
    assert len(build_document_families(documents)) == 2


def test_generic_titles_need_claim_overlap_before_grouping():
    documents = [
        {
            "id": "a", "title": "Company Overview", "reference": "notion:a",
            "source": "notion", "source_date": "2026-01-01T00:00:00Z",
            "content_hash": "one", "claims": [{"id": "goal-a", "entity_type": "Goal", "statement": "Hire two engineers."}],
        },
        {
            "id": "b", "title": "Company Overview FINAL", "reference": "gdrive:b",
            "source": "google", "source_date": "2026-01-02T00:00:00Z",
            "content_hash": "two", "claims": [{"id": "constraint-b", "entity_type": "Constraint", "statement": "Require SSO for administrators."}],
        },
    ]
    assert len(build_document_families(documents)) == 2


def test_changed_claims_help_align_renamed_versions():
    documents = [
        {
            "id": "a", "title": "Northstar Pilot", "reference": "notion:a",
            "source": "notion", "source_date": "2026-01-01T00:00:00Z",
            "content_hash": "one", "claims": [{"id": "goal-a", "entity_type": "Goal", "statement": "The Northstar pilot runs for six weeks."}],
        },
        {
            "id": "b", "title": "Northstar Board Update", "reference": "gdrive:b",
            "source": "google", "source_date": "2026-01-02T00:00:00Z",
            "content_hash": "two", "claims": [{"id": "goal-b", "entity_type": "Goal", "statement": "The Northstar pilot runs for four weeks."}],
        },
    ]
    families = build_document_families(documents)
    assert len(families) == 1
    assert families[0]["diff"]["counts"]["changed"] == 1


def test_semantic_diff_aligns_changed_values_and_preserves_history():
    previous = {
        "id": "old",
        "claims": [{"id": "budget-old", "entity_type": "Constraint", "statement": "The budget is EUR 10,000."}],
    }
    current = {
        "id": "new",
        "claims": [{"id": "budget-new", "entity_type": "Constraint", "statement": "The budget is EUR 8,000."}],
    }
    diff = compare_documents(previous, current)
    assert diff["counts"] == {"added": 0, "removed": 0, "changed": 1, "unchanged": 0, "conflicts": 1}
    assert diff["changed"][0]["reason"] == "value changed"
    assert diff["conflicts"][0]["status"] == "unresolved"


def test_built_in_example_is_a_complete_cross_platform_family():
    family = build_document_families(demo_document_versions())[0]
    assert family["is_demo"] is True
    assert family["version_count"] == 3
    assert family["sources"] == ["google", "notion", "upload"]
    assert family["contributors"] == ["Alex Chen", "Lena Hoffmann", "Priya Raman"]
    assert family["latest_version_id"] == "demo-campus-forum-upload"
    assert family["truth_status"] == "contested"
    assert family["diff"]["counts"] == {
        "added": 2, "removed": 0, "changed": 5, "unchanged": 0, "conflicts": 5,
    }
