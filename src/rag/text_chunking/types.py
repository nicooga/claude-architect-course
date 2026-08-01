from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    source: str
    location: str
    strategy: str
    chunk_id: str
