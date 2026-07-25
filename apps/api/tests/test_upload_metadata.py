"""Offline contract tests for uploaded document metadata."""

from datetime import datetime
import unittest

from main import MAX_UPLOAD_FILES, _uploaded_document_date


class UploadMetadataTests(unittest.TestCase):
    def test_realistic_demo_pack_fits_in_one_upload(self) -> None:
        self.assertGreaterEqual(MAX_UPLOAD_FILES, 14)

    def test_front_matter_date_drives_version_order(self) -> None:
        content = """---
title: Campus Forum Plan v2
date: 2026-10-10
---
# Approved plan
"""
        self.assertEqual(
            _uploaded_document_date(content),
            datetime(2026, 10, 10),
        )

    def test_document_without_date_uses_current_time(self) -> None:
        before = datetime.utcnow()
        result = _uploaded_document_date("# Notes")
        after = datetime.utcnow()
        self.assertLessEqual(before, result)
        self.assertLessEqual(result, after)


if __name__ == "__main__":
    unittest.main()
