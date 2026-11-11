from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class QualityReport:
    input_rows: int = 0
    output_rows: int = 0
    accepted_rows: int = 0
    review_rows: int = 0
    rejected_rows: int = 0
    duplicate_removed_rows: int = 0
    repaired_rows: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_reason(self, reason: str, count: int = 1) -> None:
        self.reasons[reason] = self.reasons.get(reason, 0) + count

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
