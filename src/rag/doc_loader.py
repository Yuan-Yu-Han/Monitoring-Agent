from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
import re

DOCS_ROOT = Path(__file__).resolve().parents[2] / "rag_data" / "knowledge"
SUPPORTED_EXTS = {".txt", ".md", ".pdf", ".docx"}


_PAGE_NOISE_RE = re.compile(r"^(\s*[\dIVX]+\s*|\s*[.·…]{3,}\s*|\s*[-_]{3,}\s*)$")


def _clean_text(text: str) -> str:
    # 过滤常见页码/分隔线噪声，并压缩空白
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
    # 优先使用 PyMuPDF，其次尝试 pdfplumber
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

        texts.append(
            {
                "source": str(path.relative_to(DOCS_ROOT)),
                "content": content,
            }
        )
    return texts
