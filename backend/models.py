from dataclasses import dataclass, field
from typing import Any

@dataclass
class Artifact:
    id: str
    filename: str
    path: str
    artifact_type: str
    version: int
    parent_id: str | None = None
    style_profile: dict[str, Any] = field(default_factory=dict)
    structure: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
