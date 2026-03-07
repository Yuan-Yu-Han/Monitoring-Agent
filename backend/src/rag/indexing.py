from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Chunk type
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    id: str
    text: str
    source: str = ""
    title: str = ""
    section: str = ""
    image_captions: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Document loader
# ---------------------------------------------------------------------------

DOCS_ROOT = Path(__file__).resolve().parents[2] / "rag_data" / "knowledge"
SUPPORTED_EXTS = {".txt", ".md", ".pdf", ".docx"}

_PAGE_NOISE_RE = re.compile(r"^(\s*[\dIVX]+\s*|\s*[.·…]{3,}\s*|\s*[-_]{3,}\s*)$")


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _PAGE_NOISE_RE.match(line):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _read_text_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None


def _read_pdf(path: Path) -> Optional[str]:
    try:
        import fitz  # type: ignore
        with fitz.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception:
        pass
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(path) as doc:
            pages = [page.extract_text() or "" for page in doc.pages]
            return "\n".join(pages)
    except Exception:
        return None


def _read_docx(path: Path) -> Optional[str]:
    try:
        import docx  # type: ignore
        document = docx.Document(path)
        return "\n".join(p.text for p in document.paragraphs)
    except Exception:
        return None


def _load_content(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return _read_text_file(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".docx":
        return _read_docx(path)
    return None


def load_docs() -> List[Dict[str, str]]:
    texts: List[Dict[str, str]] = []
    if not DOCS_ROOT.exists():
        return texts
    for path in DOCS_ROOT.glob("**/*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTS:
            continue
        content = _load_content(path)
        if not content:
            continue
        content = _clean_text(content)
        if not content:
            continue
        texts.append({"source": str(path.relative_to(DOCS_ROOT)), "content": content})
    return texts


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

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
    return [cap.strip() for cap in _IMAGE_RE.findall(text) if cap.strip()]


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
