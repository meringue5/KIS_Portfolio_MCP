"""Source collection port used by managed pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SourceEnvelope:
    source_id: str
    source_record_id: str
    observed_at: datetime
    fetched_at: datetime
    payload: dict[str, Any]
    content_hash: str
    quality_status: str = "pass"


class SourcePort(Protocol):
    source_id: str

    def collect(self, request: dict[str, Any]) -> list[SourceEnvelope]: ...
