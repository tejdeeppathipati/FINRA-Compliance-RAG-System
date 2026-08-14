"""Expose the manifest and local snapshot provenance through read-only endpoints."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.ingestion.manifest import Source, load_manifest

router = APIRouter(tags=["sources"])


class SourceSummary(BaseModel):
    source_id: str
    rule_number: str | None
    title: str
    source_type: str
    source_url: str
    latest_retrieved_at: datetime | None = None
    latest_effective_date: date | None = None
    normalized_content_hash: str | None = None
    normalized: bool = False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _manifest() -> tuple[Path, Any]:
    path = _repo_root() / "data" / "source_manifest.yaml"
    return path, load_manifest(path)


def _latest_metadata(source: Source) -> dict[str, Any]:
    source_dir = _repo_root() / "data" / "raw" / source.source_id
    paths = sorted(source_dir.glob("*.metadata.json"), reverse=True)
    if not paths:
        return {}
    try:
        value = json.loads(paths[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _latest_normalized(source: Source) -> dict[str, Any]:
    source_dir = _repo_root() / "data" / "normalized" / source.source_id
    paths = sorted(source_dir.glob("*.json"), reverse=True)
    if not paths:
        return {}
    try:
        value = json.loads(paths[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _summary(source: Source) -> SourceSummary:
    metadata = _latest_metadata(source)
    normalized = _latest_normalized(source)
    retrieved_at = metadata.get("retrieved_at")
    latest_effective_date = normalized.get("latest_effective_date")
    return SourceSummary(
        source_id=source.source_id,
        rule_number=source.rule_number,
        title=source.title,
        source_type=source.source_type.value,
        source_url=source.url,
        latest_retrieved_at=(
            datetime.fromisoformat(retrieved_at) if isinstance(retrieved_at, str) else None
        ),
        latest_effective_date=(
            date.fromisoformat(latest_effective_date)
            if isinstance(latest_effective_date, str)
            else None
        ),
        normalized_content_hash=(
            normalized.get("normalized_content_hash")
            if isinstance(normalized.get("normalized_content_hash"), str)
            else None
        ),
        normalized=bool(normalized),
    )


@router.get("/sources", response_model=list[SourceSummary])
def list_sources() -> list[SourceSummary]:
    _, manifest = _manifest()
    return [_summary(source) for source in manifest.sources]


@router.get("/sources/{source_id}", response_model=SourceSummary)
def get_source(source_id: str) -> SourceSummary:
    _, manifest = _manifest()
    matches = [source for source in manifest.sources if source.source_id == source_id]
    if not matches:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source_id}")
    return _summary(matches[0])
