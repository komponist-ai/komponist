"""
Local documents connector.

Watch a local directory for markdown, text, and YAML files.
No OAuth required - just a path configuration.
"""

import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, List, AsyncIterator
import asyncio

import sys
sys.path.append("../../../packages")

from core.models import SourceItem, SourceType


# Configuration
LOCAL_DOCS_PATH = os.getenv("KOMPONIST_LOCAL_DOCS_PATH", "./docs")
LOCAL_DOCS_EXTENSIONS = os.getenv(
    "KOMPONIST_LOCAL_DOCS_EXTENSIONS",
    ".md,.txt,.yaml,.yml"
).split(",")


def get_file_id(file_path: Path) -> str:
    """
    Generate a stable ID for a file based on its path.

    Args:
        file_path: Path to the file

    Returns:
        Hash-based ID
    """
    return hashlib.md5(str(file_path).encode()).hexdigest()[:12]


def parse_markdown_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter from markdown content.

    Args:
        content: Raw file content

    Returns:
        Tuple of (frontmatter dict, body content)
    """
    if not content.startswith("---"):
        return {}, content

    try:
        # Find the closing ---
        end_idx = content.find("---", 3)
        if end_idx == -1:
            return {}, content

        import yaml
        frontmatter_str = content[3:end_idx].strip()
        frontmatter = yaml.safe_load(frontmatter_str) or {}
        body = content[end_idx + 3:].strip()

        return frontmatter, body
    except Exception:
        return {}, content


def extract_title_from_markdown(content: str, filename: str) -> str:
    """
    Extract title from markdown content.

    Priority:
    1. Frontmatter 'title' field
    2. First H1 heading
    3. Filename without extension

    Args:
        content: Markdown content
        filename: File name for fallback

    Returns:
        Extracted title
    """
    frontmatter, body = parse_markdown_frontmatter(content)

    # Check frontmatter
    if "title" in frontmatter:
        return str(frontmatter["title"])

    # Look for first H1
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("##"):
            return line[2:].strip()

    # Fallback to filename
    return Path(filename).stem.replace("-", " ").replace("_", " ").title()


def normalize_local_doc(
    file_path: Path,
    content: str,
    org_id: str,
    department_id: Optional[str] = None,
) -> SourceItem:
    """
    Normalize a local document to SourceItem.

    Args:
        file_path: Path to the file
        content: File content
        org_id: Organization ID

    Returns:
        SourceItem for extraction
    """
    filename = file_path.name
    title = extract_title_from_markdown(content, filename)

    # Get modification time
    try:
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
    except Exception:
        mtime = datetime.utcnow()

    # Determine kind based on extension
    suffix = file_path.suffix.lower()
    if suffix in [".md", ".markdown"]:
        kind = "markdown"
    elif suffix in [".yaml", ".yml"]:
        kind = "yaml"
    elif suffix == ".txt":
        kind = "text"
    else:
        kind = "document"

    # Create reference with file path relative to docs root
    docs_root = Path(LOCAL_DOCS_PATH)
    try:
        relative_path = file_path.relative_to(docs_root)
    except ValueError:
        relative_path = file_path.name

    return SourceItem(
        org_id=org_id,
        department_id=department_id,
        source=SourceType.MANUAL,  # Using MANUAL for local docs
        kind=kind,
        title=title,
        body=content,
        author=None,  # Local docs don't have author
        url=f"file://{file_path.absolute()}",
        reference=f"local:{relative_path}",
        source_date=mtime
    )


def scan_directory(
    directory: Path,
    extensions: List[str]
) -> List[Path]:
    """
    Recursively scan directory for matching files.

    Args:
        directory: Root directory to scan
        extensions: List of file extensions to include

    Returns:
        List of matching file paths
    """
    files = []

    if not directory.exists():
        return files

    for ext in extensions:
        ext = ext.strip()
        if not ext.startswith("."):
            ext = f".{ext}"
        files.extend(directory.rglob(f"*{ext}"))

    return sorted(files)


async def read_file_async(file_path: Path) -> Optional[str]:
    """
    Read file content asynchronously.

    Args:
        file_path: Path to file

    Returns:
        File content or None on error
    """
    try:
        # Run in thread pool to not block
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(
            None,
            lambda: file_path.read_text(encoding="utf-8")
        )
        return content
    except Exception as e:
        print(f"[LocalDocs] Error reading {file_path}: {e}")
        return None


async def scan_local_docs(
    org_id: str,
    docs_path: Optional[str] = None,
    department_id: Optional[str] = None,
) -> AsyncIterator[SourceItem]:
    """
    Scan local documents directory and yield SourceItems.

    Args:
        org_id: Organization ID
        docs_path: Override path (uses env var if not provided)

    Yields:
        SourceItem for each document
    """
    path = Path(docs_path or LOCAL_DOCS_PATH)

    if not path.exists():
        print(f"[LocalDocs] Directory not found: {path}")
        return

    print(f"[LocalDocs] Scanning {path}...")

    files = scan_directory(path, LOCAL_DOCS_EXTENSIONS)
    print(f"[LocalDocs] Found {len(files)} files")

    for file_path in files:
        content = await read_file_async(file_path)

        if content is None:
            continue

        # Skip empty files
        if not content.strip():
            continue

        # Skip very small files (likely not useful)
        if len(content) < 50:
            continue

        source_item = normalize_local_doc(
            file_path, content, org_id, department_id=department_id
        )
        print(f"  Document: {source_item.title[:60]}")

        yield source_item


async def backfill_local_docs(
    org_id: str,
    docs_path: Optional[str] = None,
    department_id: Optional[str] = None,
    processor: Optional[Callable[[SourceItem], Awaitable[dict[str, Any]]]] = None,
) -> dict:
    """
    Backfill local documents into the extraction pipeline.

    Args:
        org_id: Organization ID
        docs_path: Override path

    Returns:
        Summary of backfill results
    """
    path = Path(docs_path or LOCAL_DOCS_PATH)
    if not path.exists():
        return {
            "status": "error",
            "error": f"Local documents directory not found: {path}",
            "documents_scanned": 0,
            "documents_processed": 0,
            "items_processed": 0,
            "facts_extracted": 0,
            "entities_created": 0,
            "errors": 1,
        }

    if processor is None:
        from pipelines.extract import extract_from_source

        processor = extract_from_source

    scanned = 0
    processed = 0
    facts_extracted = 0
    entities_created = 0
    entity_ids: list[str] = []
    errors = 0

    async for source_item in scan_local_docs(
        org_id, docs_path, department_id=department_id
    ):
        scanned += 1
        try:
            result = await processor(source_item)
            if not result.get("success", True):
                raise RuntimeError(result.get("error") or "Extraction failed")

            processed += 1
            facts_extracted += result.get("facts_extracted", 0)
            entities_created += result.get("entities_created", 0)
            entity_ids.extend(result.get("entity_ids", []))
        except Exception as e:
            print(f"[LocalDocs] Error processing {source_item.reference}: {e}")
            errors += 1

    print(
        "[LocalDocs] Backfill complete: "
        f"{processed}/{scanned} documents, {entities_created} entities, {errors} errors"
    )

    return {
        "status": "complete" if errors == 0 else "partial",
        "documents_scanned": scanned,
        "documents_processed": processed,
        "items_processed": processed,
        "facts_extracted": facts_extracted,
        "entities_created": entities_created,
        "entity_ids": entity_ids,
        "errors": errors
    }


def get_local_docs_status(docs_path: Optional[str] = None) -> dict:
    """
    Get status of local docs connector.

    Args:
        docs_path: Override path

    Returns:
        Status dict with file counts
    """
    path = Path(docs_path or LOCAL_DOCS_PATH)

    if not path.exists():
        return {
            "configured": bool(docs_path or LOCAL_DOCS_PATH),
            "path": str(path),
            "exists": False,
            "file_count": 0,
            "extensions": LOCAL_DOCS_EXTENSIONS
        }

    files = scan_directory(path, LOCAL_DOCS_EXTENSIONS)

    return {
        "configured": True,
        "path": str(path),
        "exists": True,
        "file_count": len(files),
        "extensions": LOCAL_DOCS_EXTENSIONS
    }


if __name__ == "__main__":
    import asyncio

    async def main():
        # Test scan
        status = get_local_docs_status()
        print(f"Status: {status}")

        if status["exists"]:
            result = await backfill_local_docs(org_id="test-org")
            print(f"Result: {result}")

    asyncio.run(main())
