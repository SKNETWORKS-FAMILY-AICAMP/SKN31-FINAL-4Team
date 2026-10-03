from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class CollectionResult:
    source_code: str
    entity_type: str
    source_entity_id: str
    collected_at: datetime
    payload: dict[str, Any]

    source_url: str | None = None
    http_status: int | None = None

    discovered_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self):
        self.source_code = self.source_code.upper().strip()
        self.entity_type = self.entity_type.upper().strip()
        self.source_entity_id = str(self.source_entity_id)

        if not isinstance(self.payload, dict):
            raise TypeError(
                "CollectionResult.payload must be dict"
            )

        if self.discovered_count < 0:
            raise ValueError(
                "discovered_count cannot be negative"
            )

        if self.success_count < 0:
            raise ValueError(
                "success_count cannot be negative"
            )

        if self.failure_count < 0:
            raise ValueError(
                "failure_count cannot be negative"
            )