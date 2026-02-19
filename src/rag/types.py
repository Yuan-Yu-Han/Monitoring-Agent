from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Chunk:
    id: str
    text: str
    source: str = ""
    title: str = ""
    section: str = ""
    image_captions: List[str] = field(default_factory=list)
