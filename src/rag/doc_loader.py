from __future__ import annotations

from pathlib import Path
from typing import Dict, List

DOCS_ROOT = Path(__file__).resolve().parents[2] / "data" / "knowledge"


def load_docs() -> List[Dict[str, str]]:
    texts: List[Dict[str, str]] = []
    if not DOCS_ROOT.exists():
        return texts

    for path in DOCS_ROOT.glob("**/*.md"):
        try:
            texts.append(
                {
                    "source": str(path.relative_to(DOCS_ROOT)),
                    "content": path.read_text(encoding="utf-8"),
                }
            )
        except Exception:
            continue
    return texts
