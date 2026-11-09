"""Runbooks are Markdown files with YAML front matter; chunks are split by `##` heading."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..models import Chunk, Runbook

_FRONT = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def parse_runbook(text: str) -> Runbook:
    match = _FRONT.match(text)
    if not match:
        raise ValueError("runbook is missing YAML front matter")
    meta = yaml.safe_load(match.group(1)) or {}
    return Runbook(**meta, body=match.group(2).strip())


def load_runbooks(folder: str | Path) -> dict[str, Runbook]:
    books: dict[str, Runbook] = {}
    for path in sorted(Path(folder).glob("*.md")):
        book = parse_runbook(path.read_text(encoding="utf-8"))
        if book.id in books:
            raise ValueError(f"duplicate runbook id: {book.id}")
        books[book.id] = book
    return books


def chunk_runbook(book: Runbook) -> list[Chunk]:
    """One chunk for the header (title + keywords) and one per `##` section.

    The header chunk carries the keywords so that short alert titles still match.
    """
    chunks = [
        Chunk(
            id=f"{book.id}#overview",
            runbook_id=book.id,
            heading="Overview",
            text=f"{book.title}. Keywords: {', '.join(book.keywords)}. Sources: {', '.join(book.sources)}.",
        )
    ]
    sections = re.split(r"^## +", book.body, flags=re.M)
    for section in sections[1:]:
        heading, _, content = section.partition("\n")
        slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
        chunks.append(
            Chunk(
                id=f"{book.id}#{slug}",
                runbook_id=book.id,
                heading=heading.strip(),
                text=f"{book.title} - {heading.strip()}\n{content.strip()}",
            )
        )
    return chunks
