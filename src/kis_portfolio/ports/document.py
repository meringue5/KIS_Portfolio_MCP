"""Restricted document extraction port."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ExtractionUnit:
    locator: str
    text: str | None = None
    structured: dict[str, Any] | None = None
    quality_status: str = "pass"


class DocumentExtractorPort(Protocol):
    extractor_id: str
    extractor_version: str

    def extract(self, path: Path) -> tuple[ExtractionUnit, ...]: ...
