"""Ingestion pipeline for the shared knowledge store.

Indexes local docs/ and trusted online sources into the SqliteStore.
Run via: bash run.sh ingest-knowledge
"""

from __future__ import annotations

import hashlib
import logging
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .knowledge_store import get_knowledge_store

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[2]
_TRUSTED_SOURCES_FILE = _PROJECT_ROOT / "docs" / "trusted-sources.md"
_LOCAL_DOCS_DIR = _PROJECT_ROOT / "docs"

_URL_RE = re.compile(r"- URL:\s*(https?://\S+)")


def _content_key(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _chunk_markdown(text: str, source: str, max_chars: int = 1500) -> list[dict]:
    sections = re.split(r"\n#{1,3} ", text)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        lines = section.splitlines()
        title = lines[0].lstrip("#").strip() if lines else "untitled"
        for i in range(0, len(section), max_chars):
            chunk = section[i:i + max_chars]
            chunks.append({
                "title": title,
                "source": source,
                "content": chunk,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            })
    return chunks


def ingest_local_docs(force: bool = False) -> int:
    store = get_knowledge_store()
    count = 0
    for md_file in sorted(_LOCAL_DOCS_DIR.glob("**/*.md")):
        if md_file.name.startswith("_"):
            continue
        text = md_file.read_text(encoding="utf-8")
        source = str(md_file.relative_to(_PROJECT_ROOT))
        chunks = _chunk_markdown(text, source)
        for chunk in chunks:
            key = _content_key(chunk["content"])
            store.put(("shared", "docs"), key, chunk)
            count += 1
    logger.info("Ingested %d chunks from local docs", count)
    return count


def _parse_trusted_urls() -> list[str]:
    if not _TRUSTED_SOURCES_FILE.exists():
        return []
    text = _TRUSTED_SOURCES_FILE.read_text(encoding="utf-8")
    return _URL_RE.findall(text)


def _fetch_url(url: str, timeout: int = 10) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agent-factory-knowledge-bot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return raw.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return None


def ingest_trusted_sources() -> int:
    store = get_knowledge_store()
    urls = _parse_trusted_urls()
    count = 0
    for url in urls:
        logger.info("Fetching trusted source: %s", url)
        content = _fetch_url(url)
        if not content:
            continue
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()
        chunks = _chunk_markdown(text, url)
        for chunk in chunks:
            key = _content_key(chunk["content"])
            store.put(("shared", "trusted"), key, chunk)
            count += 1
        logger.info("Ingested %d chunks from %s", len(chunks), url)
    return count


def run_ingestion() -> None:
    local = ingest_local_docs()
    online = ingest_trusted_sources()
    print(f"Ingestion complete: {local} local chunks, {online} online chunks")
