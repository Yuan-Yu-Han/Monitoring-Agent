from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

from src.rag.types import Chunk

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^\)]+\)")


def extract_title(text: str) -> str:
    for line in text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            return match.group(2).strip()
    for line in text.splitlines():
        clean = line.strip()
        if clean:
            return clean[:120]
    return ""


def extract_image_captions(text: str) -> List[str]:
    captions = [cap.strip() for cap in _IMAGE_RE.findall(text) if cap.strip()]
    return captions


def _split_sections(text: str) -> List[Tuple[str, str]]:
    sections: List[Tuple[str, List[str]]] = []
    current_title = "General"
    current_lines: List[str] = []

    for line in text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = match.group(2).strip() or "General"
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))

    return [(title, "\n".join(lines).strip()) for title, lines in sections]


def _split_text(text: str, max_chars: int, overlap: int) -> List[str]:
    chunks: List[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == length:
            break
        start = max(0, end - overlap)
    return chunks


def _augment_chunk(text: str, title: str, section: str, image_captions: List[str]) -> str:
    meta: List[str] = []
    if title:
        meta.append(f"Title: {title}")
    if section:
        meta.append(f"Section: {section}")
    if image_captions:
        meta.append("Images: " + ", ".join(image_captions))
    if meta:
        return "\n".join(meta) + "\n\n" + text.strip()
    return text.strip()


def build_chunks(
    docs: Iterable[Dict[str, str]],
    max_chars: int = 800,
    overlap: int = 120,
) -> List[Chunk]:
    chunks: List[Chunk] = []
    for doc in docs:
        source = doc.get("source", "")
        content = doc.get("content", "")
        title = extract_title(content)
        image_captions = extract_image_captions(content)
        sections = _split_sections(content)

        for section_idx, (section_title, section_text) in enumerate(sections):
            if not section_text:
                continue
            for chunk_idx, chunk_text in enumerate(
                _split_text(section_text, max_chars=max_chars, overlap=overlap)
            ):
                augmented = _augment_chunk(chunk_text, title, section_title, image_captions)
                chunks.append(
                    Chunk(
                        id=f"{source}::s{section_idx}::c{chunk_idx}",
                        text=augmented,
                        source=source,
                        title=title,
                        section=section_title,
                        image_captions=image_captions,
                    )
                )
    return chunks
