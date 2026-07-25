"""Contract checks for the realistic CampusKollektiv upload fixture."""

import hashlib
from pathlib import Path
import re
import unittest


PACK = Path(__file__).parents[3] / "test-data" / "upload" / "campuskollektiv"
MARKER = re.compile(r"(?m)^(Decision|Goal|Constraint|Project):\s+(.+)$")


class CampusKollektivPackTests(unittest.TestCase):
    def test_pack_has_broad_realistic_coverage(self) -> None:
        documents = sorted([
            *PACK.glob("*.md"),
            *PACK.glob("*.txt"),
        ])
        documents = [path for path in documents if path.name != "README.md"]
        self.assertGreaterEqual(len(documents), 14)

        markers = []
        combined = ""
        for document in documents:
            content = document.read_text(encoding="utf-8")
            combined += "\n" + content
            markers.extend(MARKER.findall(content))

        self.assertGreaterEqual(len(markers), 35)
        self.assertEqual(
            {entity_type for entity_type, _ in markers},
            {"Decision", "Goal", "Constraint", "Project"},
        )
        for term in (
            "board",
            "Events department",
            "Partnerships department",
            "highly confidential",
            "€4,800",
            "depends on",
        ):
            self.assertIn(term, combined)

    def test_approved_copy_is_byte_identical(self) -> None:
        original = (PACK / "08-campus-forum-plan-v2.md").read_bytes()
        copied = (PACK / "09-campus-forum-plan-approved-copy.md").read_bytes()
        self.assertEqual(
            hashlib.sha256(original).hexdigest(),
            hashlib.sha256(copied).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
