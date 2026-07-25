"""Offline tests for extraction grounding and long-document handling."""

import unittest

from pipelines.extract import (
    document_chunks,
    preserves_source_modality,
    verbatim_excerpt,
)


class ExtractionGroundingTests(unittest.TestCase):
    def test_verbatim_excerpt_repairs_whitespace_to_source_bytes(self) -> None:
        body = "The board decided:\nUse the university account for payments."
        excerpt = "The board decided: Use the university account for payments."

        self.assertEqual(
            verbatim_excerpt(body, excerpt),
            "The board decided:\nUse the university account for payments.",
        )

    def test_unverifiable_excerpt_is_rejected(self) -> None:
        self.assertIsNone(
            verbatim_excerpt("The event is planned for October.", "The event is done.")
        )

    def test_dependency_cannot_be_rewritten_as_completed_fact(self) -> None:
        excerpt = (
            "The launch depends on the privacy review being completed before "
            "20 August."
        )
        self.assertFalse(
            preserves_source_modality(
                excerpt, "The privacy review is completed before 20 August."
            )
        )
        self.assertTrue(
            preserves_source_modality(
                excerpt, "The launch depends on completing the privacy review."
            )
        )

    def test_long_documents_are_split_without_losing_content(self) -> None:
        paragraphs = [f"Section {index}: " + ("x" * 700) for index in range(12)]
        body = "\n\n".join(paragraphs)
        chunks = document_chunks(body, max_chars=1800)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1800 for chunk in chunks))
        for paragraph in paragraphs:
            self.assertTrue(any(paragraph in chunk for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
