from dataclasses import dataclass
from typing import List


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    title: str
    section: str
    image_captions: List[str]
