from dataclasses import dataclass, field
from typing import List


@dataclass
class PageList:
    pages: List[str]
    source: str
    # 0-indexed pages whose text came from OCR rather than pypdf's text layer.
    ocr_pages: List[int] = field(default_factory=list)
