"""Represent and write provenance metadata for downloaded source snapshots."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    source_id: str
    rule_number: str | None
    title: str
    source_type: str
    requested_url: str
    final_url: str
    retrieved_at: str
    http_status: int
    content_type: str
    content_length_bytes: int
    content_sha256: str
    etag: str | None
    last_modified: str | None
    html_file: str
    fetcher_version: str = "finra-fetcher-v1"

    @classmethod
    def create(cls, **values: Any) -> SnapshotMetadata:
        retrieved_at = values.get("retrieved_at")
        if isinstance(retrieved_at, datetime):
            values["retrieved_at"] = retrieved_at.isoformat()
        return cls(**values)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def read_latest_metadata(source_dir: Path) -> dict[str, Any] | None:
    metadata_files = sorted(source_dir.glob("*.metadata.json"), reverse=True)
    if not metadata_files:
        return None
    try:
        value = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        LOGGER.warning("Could not read previous metadata: %s", metadata_files[0])
        return None
    return value if isinstance(value, dict) else None
