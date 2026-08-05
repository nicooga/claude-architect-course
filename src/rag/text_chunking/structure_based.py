import re
from dataclasses import dataclass
from typing import List, Optional

from ..ingestion.types import PageList
from .types import Chunk

STRATEGY = "structure"

DEFAULT_MAX_CHUNK_SIZE = 1000

_LINE_HYPHEN_BREAK = re.compile(r"-\n(?=[a-záéíóúñü])")
_BLANK_LINE = re.compile(r"\n\s*\n+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ0-9\"'¿¡])")
_NUMBERED_HEADING = re.compile(
    r"^(cap[ií]tulo|chapter|parte|secci[oó]n|section)\b", re.IGNORECASE
)


@dataclass
class _Unit:
    text: str
    page: int
    is_heading: bool


def _is_heading(line: str) -> bool:
    """A line is treated as a heading if it's short, doesn't end mid-sentence,
    and is either a numbered heading ("Capítulo 3") or fully uppercase.

    Known limitation: a scanned book's running header/footer (title repeated
    on every page) matches the all-caps case just as well as a real heading
    — there's no cross-page repetition check here, so those force a chunk
    break on every page. Acceptable for a from-scratch regex heuristic; see
    the README's "Open defaults" note for Stage 3.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 80 or stripped[-1] in ".,;:":
        return False
    if _NUMBERED_HEADING.match(stripped):
        return True
    letters = [c for c in stripped if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _dehyphenate(text: str) -> str:
    return _LINE_HYPHEN_BREAK.sub("", text)


def _page_units(page_text: str, page_number: int) -> List[_Unit]:
    """Split one page into heading lines and paragraph blocks. A paragraph
    block is blank-line-separated where the source has blank lines; PDF text
    extraction usually doesn't, so a block is then the whole non-heading run
    between headings, left for sentence-level packing to break up."""
    units: List[_Unit] = []
    body_lines: List[str] = []

    def flush_body() -> None:
        if not body_lines:
            return
        block = "\n".join(body_lines)
        body_lines.clear()
        for paragraph in _BLANK_LINE.split(block):
            normalized = " ".join(paragraph.split())
            if normalized:
                units.append(_Unit(normalized, page_number, is_heading=False))

    for line in _dehyphenate(page_text).split("\n"):
        if _is_heading(line):
            flush_body()
            units.append(_Unit(line.strip(), page_number, is_heading=True))
        else:
            body_lines.append(line)
    flush_body()
    return units


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_BOUNDARY.split(text) if s.strip()]


def chunk_structure_based(
    page_list: PageList,
    max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
) -> List[Chunk]:
    """Packs paragraphs/sentences under their heading, up to max_chunk_size,
    cutting only at a sentence boundary (never mid-sentence, unlike
    size-based). A heading always starts a new chunk. Per ADR-004, a
    paragraph/sentence run may bridge a page seam when nothing (heading or
    size budget) forces a break there — `location` then reports a page
    range instead of a single page.

    Not great on runs of consecutive heading-like lines with no body text
    between them (a title page: author, title, subtitle, edition, each on
    its own short all-caps line) — each one flushes and starts the next,
    so they come out as separate near-empty chunks instead of one. That's
    the ceiling of inferring structure from plain text with regexes; a
    format that carries real structure (HTML/XML) wouldn't have this
    problem. Acceptable for this experiment."""
    units: List[_Unit] = []
    for page_number, page_text in enumerate(page_list.pages, start=1):
        units.extend(_page_units(page_text, page_number))

    chunks: List[Chunk] = []
    parts: List[str] = []
    length = 0
    first_page: Optional[int] = None
    last_page: Optional[int] = None

    def flush() -> None:
        nonlocal parts, length, first_page, last_page
        if not parts:
            return
        location = (
            f"page {first_page}"
            if first_page == last_page
            else f"pages {first_page}-{last_page}"
        )
        chunks.append(
            Chunk(
                text=" ".join(parts),
                source=page_list.source,
                location=location,
                strategy=STRATEGY,
                chunk_id=f"{STRATEGY}:{page_list.source}:p{first_page}:{len(chunks)}",
            )
        )
        parts, length, first_page, last_page = [], 0, None, None

    def add(piece: str, page: int) -> None:
        nonlocal length, first_page, last_page
        parts.append(piece)
        length += len(piece) + (1 if len(parts) > 1 else 0)
        first_page = page if first_page is None else first_page
        last_page = page

    for unit in units:
        if unit.is_heading:
            flush()
            add(unit.text, unit.page)
            continue

        for sentence in _split_sentences(unit.text):
            if parts and length + len(sentence) + 1 > max_chunk_size:
                flush()
            add(sentence, unit.page)

    flush()
    return chunks
