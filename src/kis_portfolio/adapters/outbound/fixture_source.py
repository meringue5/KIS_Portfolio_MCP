"""Recorded, non-secret source adapter used for contract tests and rehearsals."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from kis_portfolio.ports.source import SourceEnvelope


class FixtureSourceAdapter:
    def __init__(self, path: Path) -> None:
        self.path = path
        document = json.loads(path.read_text(encoding="utf-8"))
        self.source_id = document["source_id"]
        self._records = document["records"]

    def collect(self, request: dict[str, Any]) -> list[SourceEnvelope]:
        record_type = request.get("record_type")
        envelopes: list[SourceEnvelope] = []
        for record in self._records:
            if record_type and record["payload"].get("type") != record_type:
                continue
            canonical = json.dumps(record["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            envelopes.append(SourceEnvelope(
                source_id=self.source_id,
                source_record_id=record["source_record_id"],
                observed_at=datetime.fromisoformat(record["observed_at"]),
                fetched_at=datetime.fromisoformat(record["fetched_at"]),
                payload=record["payload"],
                content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
                quality_status=record.get("quality_status", "pass"),
            ))
        return envelopes
