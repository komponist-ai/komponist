"""Document lineage and semantic claim differencing for Komponist.

The module deliberately keeps the first-pass matcher deterministic. Exact
content identities, normalized titles, shared graph entities, and lexical
claim similarity produce candidates without a model call. The existing
extraction pipeline supplies the ontology-aligned Entity nodes used here.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable


_VERSION_NOISE = {
    "copy", "draft", "final", "latest", "new", "old", "revision", "rev",
    "version", "notion", "google", "drive", "slides", "upload", "uploaded",
}
_GENERIC_FAMILY_KEYS = {
    "board update", "company overview", "notes", "presentation", "roadmap",
    "strategy", "team update", "untitled",
}
_CLAIM_STOP_WORDS = {
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "is",
    "of", "on", "or", "our", "the", "to", "will", "with",
}


def _source_value(source: Any) -> str:
    return source.value if hasattr(source, "value") else str(source)


def content_fingerprint(body: str) -> str:
    """Return a stable identity for the normalized document contents."""
    normalized = "\n".join(line.rstrip() for line in body.strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def document_id_for(source_item: Any) -> str:
    """Return an immutable ID for one source-specific document revision."""
    identity = "\x1f".join((
        source_item.org_id,
        _source_value(source_item.source),
        source_item.reference.strip(),
        content_fingerprint(source_item.body),
    ))
    return f"doc-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def _human_reference_title(reference: str) -> str:
    if reference.startswith("upload:"):
        parts = reference.split(":")
        if len(parts) > 2:
            return ":".join(parts[1:-1])
    if reference.startswith(("local:", "manual:")):
        return reference.split(":", 1)[-1].rsplit("/", 1)[-1]
    return reference


def normalize_document_title(title: str | None, reference: str = "") -> str:
    """Normalize names so platform copies and obvious revision suffixes align."""
    value = (title or _human_reference_title(reference) or "untitled").casefold()
    value = re.sub(r"\.(?:md|markdown|txt|pdf|pptx?|docx?|gslides)$", "", value)
    value = re.sub(r"\b(?:19|20)\d{2}[-_. ](?:0?[1-9]|1[0-2])[-_. ](?:0?[1-9]|[12]\d|3[01])\b", " ", value)
    value = re.sub(r"\b(?:v(?:ersion)?\s*)?\d+(?:\.\d+)*\b", " ", value)
    tokens = re.findall(r"[\w]+", value, flags=re.UNICODE)
    tokens = [token for token in tokens if token not in _VERSION_NOISE]
    return " ".join(tokens).strip() or "untitled"


def document_metadata(source_item: Any) -> dict[str, Any]:
    """Create the graph properties shared by every Evidence from a document."""
    fingerprint = content_fingerprint(source_item.body)
    return {
        "document_id": document_id_for(source_item),
        "content_hash": fingerprint,
        "content_length": len(source_item.body),
        "family_key": normalize_document_title(source_item.title, source_item.reference),
        "source": _source_value(source_item.source),
        "kind": source_item.kind,
        "title": source_item.title,
        "author": source_item.author,
        "reference": source_item.reference,
        "url": source_item.url,
        "department_id": source_item.department_id,
        "source_date": source_item.source_date.isoformat(),
    }


def _tokens(value: str, *, ignore_numbers: bool = False) -> set[str]:
    tokens = set(re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE))
    if ignore_numbers:
        tokens = {token for token in tokens if not any(char.isdigit() for char in token)}
    return {token for token in tokens if token not in _CLAIM_STOP_WORDS}


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set, right_set = set(left), set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _text_similarity(left: str, right: str, *, ignore_numbers: bool = False) -> float:
    left_value = left.casefold()
    right_value = right.casefold()
    if ignore_numbers:
        left_value = re.sub(r"\b\d+(?:[.,]\d+)?\b", "#", left_value)
        right_value = re.sub(r"\b\d+(?:[.,]\d+)?\b", "#", right_value)
    token_score = _jaccard(
        _tokens(left_value, ignore_numbers=ignore_numbers),
        _tokens(right_value, ignore_numbers=ignore_numbers),
    )
    sequence_score = SequenceMatcher(None, left_value, right_value).ratio()
    return round((token_score * 0.65) + (sequence_score * 0.35), 4)


def _claim_ids(document: dict[str, Any]) -> set[str]:
    return {
        str(claim.get("id"))
        for claim in document.get("claims", [])
        if claim.get("id")
    }


def _semantic_claim_overlap(left: dict[str, Any], right: dict[str, Any]) -> float:
    """Align claims by ontology type and meaning, allowing changed values."""
    left_claims = [claim for claim in left.get("claims", []) if claim.get("statement")]
    right_claims = [claim for claim in right.get("claims", []) if claim.get("statement")]
    if not left_claims or not right_claims:
        return 0.0

    candidates = []
    for left_index, left_claim in enumerate(left_claims):
        for right_index, right_claim in enumerate(right_claims):
            if left_claim.get("entity_type") != right_claim.get("entity_type"):
                continue
            score = _text_similarity(
                str(left_claim.get("statement", "")),
                str(right_claim.get("statement", "")),
                ignore_numbers=True,
            )
            if score >= 0.5:
                candidates.append((score, left_index, right_index))

    matched_left: set[int] = set()
    matched_right: set[int] = set()
    matched = 0
    for _, left_index, right_index in sorted(candidates, reverse=True):
        if left_index in matched_left or right_index in matched_right:
            continue
        matched_left.add(left_index)
        matched_right.add(right_index)
        matched += 1
    return matched / max(len(left_claims), len(right_claims))


def family_match_score(left: dict[str, Any], right: dict[str, Any]) -> tuple[float, str]:
    """Score whether two source objects are revisions of the same logical file."""
    if left.get("content_hash") and left.get("content_hash") == right.get("content_hash"):
        return 1.0, "identical content"

    left_key = left.get("family_key") or normalize_document_title(left.get("title"), left.get("reference", ""))
    right_key = right.get("family_key") or normalize_document_title(right.get("title"), right.get("reference", ""))
    title_score = _text_similarity(left_key, right_key)
    shared_claims = max(
        _jaccard(_claim_ids(left), _claim_ids(right)),
        _semantic_claim_overlap(left, right),
    )

    if left_key == right_key and left_key != "untitled":
        if left_key in _GENERIC_FAMILY_KEYS and shared_claims < 0.25:
            return 0.45, "generic title without graph overlap"
        return round(0.9 + (shared_claims * 0.08), 4), "normalized title + graph overlap"

    score = (title_score * 0.72) + (shared_claims * 0.28)
    if shared_claims >= 0.5 and title_score >= 0.2:
        score = max(score, 0.72 + (shared_claims * 0.18))
    return round(score, 4), "title + ontology-aligned claims"


def _parse_date(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.min.replace(tzinfo=timezone.utc)
    else:
        parsed = datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _numbers(value: str) -> list[str]:
    return re.findall(r"\b\d+(?:[.,]\d+)?\b", value)


def _claim_key(claim: dict[str, Any]) -> tuple[str, str]:
    return (
        str(claim.get("entity_type") or "Fact"),
        " ".join(str(claim.get("statement") or "").casefold().split()),
    )


def compare_documents(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Return a structural and semantic diff between two graph-backed revisions."""
    old_claims = [claim for claim in previous.get("claims", []) if claim.get("statement")]
    new_claims = [claim for claim in current.get("claims", []) if claim.get("statement")]
    old_by_key = {_claim_key(claim): claim for claim in old_claims}
    new_by_key = {_claim_key(claim): claim for claim in new_claims}

    shared_keys = set(old_by_key) & set(new_by_key)
    unchanged = [new_by_key[key] for key in sorted(shared_keys)]
    remaining_old = [claim for key, claim in old_by_key.items() if key not in shared_keys]
    remaining_new = [claim for key, claim in new_by_key.items() if key not in shared_keys]

    changed: list[dict[str, Any]] = []
    used_new: set[int] = set()
    used_old: set[int] = set()
    for old_index, old_claim in enumerate(remaining_old):
        candidates = []
        for new_index, new_claim in enumerate(remaining_new):
            if new_index in used_new or old_claim.get("entity_type") != new_claim.get("entity_type"):
                continue
            score = _text_similarity(
                str(old_claim.get("statement", "")),
                str(new_claim.get("statement", "")),
                ignore_numbers=True,
            )
            candidates.append((score, new_index, new_claim))
        if not candidates:
            continue
        score, new_index, new_claim = max(candidates, key=lambda item: item[0])
        if score < 0.38:
            continue
        old_numbers = _numbers(str(old_claim.get("statement", "")))
        new_numbers = _numbers(str(new_claim.get("statement", "")))
        reason = "value changed" if old_numbers != new_numbers and (old_numbers or new_numbers) else "meaning changed"
        changed.append({
            "entity_type": new_claim.get("entity_type") or old_claim.get("entity_type"),
            "before": old_claim.get("statement"),
            "after": new_claim.get("statement"),
            "similarity": score,
            "reason": reason,
            "previous_claim_id": old_claim.get("id"),
            "current_claim_id": new_claim.get("id"),
        })
        used_old.add(old_index)
        used_new.add(new_index)

    removed = [claim for index, claim in enumerate(remaining_old) if index not in used_old]
    added = [claim for index, claim in enumerate(remaining_new) if index not in used_new]
    conflicts = [
        {
            "entity_type": item["entity_type"],
            "previous": item["before"],
            "current": item["after"],
            "reason": item["reason"],
            "status": "unresolved",
        }
        for item in changed
    ]
    return {
        "from_version_id": previous.get("id"),
        "to_version_id": current.get("id"),
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "conflicts": conflicts,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": len(unchanged),
            "conflicts": len(conflicts),
        },
    }


def _family_payload(documents: list[dict[str, Any]], match_scores: list[float]) -> dict[str, Any]:
    versions = sorted(documents, key=lambda item: (_parse_date(item.get("source_date")), item.get("id", "")))
    latest = versions[-1]
    comparisons = []
    for index, version in enumerate(versions):
        version["sequence"] = index + 1
        version["is_latest"] = version is latest
        version["parent_id"] = versions[index - 1].get("id") if index else None
        if index:
            comparison = compare_documents(versions[index - 1], version)
            comparisons.append(comparison)
            version["changes_from_previous"] = comparison["counts"]
        else:
            version["changes_from_previous"] = {
                "added": len(version.get("claims", [])), "removed": 0,
                "changed": 0, "unchanged": 0, "conflicts": 0,
            }

    baseline_diff = compare_documents(versions[0], latest) if len(versions) > 1 else {
        "from_version_id": latest.get("id"), "to_version_id": latest.get("id"),
        "added": [], "removed": [], "changed": [],
        "unchanged": latest.get("claims", []), "conflicts": [],
        "counts": {"added": 0, "removed": 0, "changed": 0, "unchanged": len(latest.get("claims", [])), "conflicts": 0},
    }
    dates = sorted({_parse_date(version.get("source_date")) for version in versions}, reverse=True)
    latest_confidence = 0.92 if len(dates) == len(versions) and (len(dates) == 1 or dates[0] > dates[1]) else 0.68
    title = latest.get("title") or versions[0].get("title") or "Untitled document"
    family_seed = "\x1f".join(sorted(str(version.get("id")) for version in versions))
    contributors = sorted({str(version.get("author")) for version in versions if version.get("author")})
    sources = sorted({str(version.get("source")) for version in versions if version.get("source")})
    statuses = {claim.get("status") for claim in latest.get("claims", []) if claim.get("status")}

    return {
        "id": f"family-{hashlib.sha256(family_seed.encode('utf-8')).hexdigest()[:16]}",
        "title": title,
        "family_key": normalize_document_title(title, latest.get("reference", "")),
        "is_demo": bool(latest.get("is_demo")),
        "version_count": len(versions),
        "contributors": contributors,
        "sources": sources,
        "latest_version_id": latest.get("id"),
        "latest_confidence": latest_confidence,
        "match_confidence": round(min(match_scores) if match_scores else 1.0, 2),
        "truth_status": "contested" if baseline_diff["conflicts"] else ("reviewed" if statuses == {"confirmed"} else "needs review"),
        "versions": versions,
        "comparisons": comparisons,
        "diff": baseline_diff,
        "canonical_claims": latest.get("claims", []),
    }


def build_document_families(documents: list[dict[str, Any]], threshold: float = 0.62) -> list[dict[str, Any]]:
    """Cluster revisions and enrich every family with lineage and semantic diffs."""
    if not documents:
        return []
    prepared = []
    for document in documents:
        item = dict(document)
        item["family_key"] = item.get("family_key") or normalize_document_title(item.get("title"), item.get("reference", ""))
        prepared.append(item)

    parents = list(range(len(prepared)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    pair_scores: dict[tuple[int, int], float] = {}
    for left in range(len(prepared)):
        for right in range(left + 1, len(prepared)):
            score, _ = family_match_score(prepared[left], prepared[right])
            pair_scores[(left, right)] = score
            if score >= threshold:
                union(left, right)

    groups: dict[int, list[int]] = {}
    for index in range(len(prepared)):
        groups.setdefault(find(index), []).append(index)

    families = []
    for indices in groups.values():
        scores = [
            pair_scores[(min(left, right), max(left, right))]
            for position, left in enumerate(indices)
            for right in indices[position + 1:]
        ]
        families.append(_family_payload([prepared[index] for index in indices], scores))
    return sorted(
        families,
        key=lambda family: (
            family["is_demo"],
            _parse_date(next(version["source_date"] for version in family["versions"] if version["is_latest"])),
        ),
        reverse=True,
    )


def demo_document_versions() -> list[dict[str, Any]]:
    """A built-in, model-free cross-platform example for the Versions UI."""
    facts = [
        (
            "demo-northstar-notion", "Northstar Pilot — Draft v1", "notion", "notion:northstar-v1",
            "Lena Hoffmann", "2026-07-02T09:30:00+00:00", "demo-hash-notion",
            [
                ("project", "Project", "The Northstar design-partner pilot is planned for Q3."),
                ("duration-v1", "Goal", "The Northstar pilot will run for six weeks."),
                ("team-v1", "Decision", "The pilot starts with Marketing and Sales."),
                ("budget-v1", "Constraint", "The pilot budget is capped at EUR 10,000."),
            ],
        ),
        (
            "demo-northstar-slides", "Northstar Pilot FINAL v2", "google", "gdrive:northstar-slides",
            "Alex Chen", "2026-07-09T14:15:00+00:00", "demo-hash-google",
            [
                ("project", "Project", "The Northstar design-partner pilot is planned for Q3."),
                ("duration-v2", "Goal", "The Northstar pilot will run for four weeks."),
                ("team-v2", "Decision", "The pilot starts with Platform Engineering."),
                ("budget-v1", "Constraint", "The pilot budget is capped at EUR 10,000."),
            ],
        ),
        (
            "demo-northstar-upload", "Northstar Pilot — Board update", "upload", "upload:northstar-board.md:demo",
            "Priya Raman", "2026-07-14T08:45:00+00:00", "demo-hash-upload",
            [
                ("project", "Project", "The Northstar design-partner pilot is planned for Q3."),
                ("duration-v2", "Goal", "The Northstar pilot will run for four weeks."),
                ("team-v2", "Decision", "The pilot starts with Platform Engineering."),
                ("budget-v3", "Constraint", "The pilot budget is capped at EUR 8,000."),
                ("success-v3", "Goal", "Success means at least 80% weekly active usage by the pilot team."),
            ],
        ),
    ]
    documents = []
    for doc_id, title, source, reference, author, source_date, content_hash, claims in facts:
        documents.append({
            "id": doc_id,
            "title": title,
            "source": source,
            "reference": reference,
            "url": None,
            "author": author,
            "source_date": source_date,
            "content_hash": content_hash,
            "family_key": "northstar pilot",
            "department_id": None,
            "is_demo": True,
            "claims": [
                {
                    "id": claim_id,
                    "entity_type": entity_type,
                    "statement": statement,
                    "status": "confirmed",
                    "confidence": "high",
                }
                for claim_id, entity_type, statement in claims
            ],
        })
    return documents
