from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

SOURCE_ID_PATTERN = re.compile(r"^finra-(?:rule|guidance)-[a-z0-9]+(?:-[a-z0-9]+)*$")
RULE_NUMBER_PATTERN = re.compile(r"^\d{4}$")


class SourceType(StrEnum):
    RULE = "rule"
    GUIDANCE = "guidance"


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    rule_number: str | None
    title: str
    source_type: SourceType
    url: str


@dataclass(frozen=True, slots=True)
class SourceManifest:
    version: int
    corpus_name: str
    scope: str
    allowed_hosts: frozenset[str]
    sources: tuple[Source, ...]

    def select(self, source_ids: set[str] | None = None) -> tuple[Source, ...]:
        if not source_ids:
            return self.sources

        known_ids = {source.source_id for source in self.sources}
        unknown_ids = source_ids - known_ids
        if unknown_ids:
            names = ", ".join(sorted(unknown_ids))
            raise ValueError(f"Unknown source IDs: {names}")
        return tuple(source for source in self.sources if source.source_id in source_ids)


def _required_text(item: dict[str, Any], field: str, *, context: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: {field} must be a non-empty string")
    return value.strip()


def _parse_source(item: Any, *, index: int, allowed_hosts: frozenset[str]) -> Source:
    context = f"Source at index {index}"
    if not isinstance(item, dict):
        raise ValueError(f"{context} must be a mapping")

    source_id = _required_text(item, "source_id", context=context)
    if not SOURCE_ID_PATTERN.fullmatch(source_id):
        raise ValueError(f"{source_id}: invalid source_id format")

    title = _required_text(item, "title", context=source_id)
    raw_source_type = _required_text(item, "source_type", context=source_id)
    try:
        source_type = SourceType(raw_source_type)
    except ValueError as error:
        raise ValueError(f"{source_id}: source_type must be 'rule' or 'guidance'") from error

    url = _required_text(item, "url", context=source_id)
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https":
        raise ValueError(f"{source_id}: only HTTPS URLs are permitted")
    if parsed_url.hostname not in allowed_hosts:
        raise ValueError(f"{source_id}: host {parsed_url.hostname!r} is not allow-listed")
    if parsed_url.username or parsed_url.password:
        raise ValueError(f"{source_id}: URL credentials are not permitted")
    if parsed_url.query or parsed_url.fragment:
        raise ValueError(f"{source_id}: URL query strings and fragments are not permitted")

    raw_rule_number = item.get("rule_number")
    rule_number = str(raw_rule_number).strip() if raw_rule_number is not None else None
    if rule_number and not RULE_NUMBER_PATTERN.fullmatch(rule_number):
        raise ValueError(f"{source_id}: rule_number must contain exactly four digits")
    if source_type is SourceType.RULE and rule_number is None:
        raise ValueError(f"{source_id}: rule sources require a rule_number")

    return Source(
        source_id=source_id,
        rule_number=rule_number,
        title=title,
        source_type=source_type,
        url=url,
    )


def load_manifest(path: Path) -> SourceManifest:
    try:
        raw_manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Could not read manifest {path}: {error}") from error
    except yaml.YAMLError as error:
        raise ValueError(f"Manifest is not valid YAML: {error}") from error

    if not isinstance(raw_manifest, dict):
        raise ValueError("Manifest root must be a mapping")
    if raw_manifest.get("version") != 1:
        raise ValueError("Manifest version must be 1")

    corpus_name = _required_text(raw_manifest, "corpus_name", context="Manifest")
    scope = _required_text(raw_manifest, "scope", context="Manifest")
    if scope != "finra-only":
        raise ValueError("Manifest scope must be 'finra-only'")

    raw_allowed_hosts = raw_manifest.get("allowed_hosts")
    if not isinstance(raw_allowed_hosts, list) or not raw_allowed_hosts:
        raise ValueError("Manifest must declare at least one allowed host")
    if not all(isinstance(host, str) and host.strip() for host in raw_allowed_hosts):
        raise ValueError("Manifest allowed_hosts must contain non-empty strings")
    allowed_hosts = frozenset(host.strip().lower() for host in raw_allowed_hosts)

    raw_sources = raw_manifest.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("Manifest contains no sources")

    sources = tuple(
        _parse_source(item, index=index, allowed_hosts=allowed_hosts)
        for index, item in enumerate(raw_sources)
    )
    source_ids = [source.source_id for source in sources]
    if len(source_ids) != len(set(source_ids)):
        duplicate = next(source_id for source_id in source_ids if source_ids.count(source_id) > 1)
        raise ValueError(f"Duplicate source_id: {duplicate}")

    return SourceManifest(
        version=1,
        corpus_name=corpus_name,
        scope=scope,
        allowed_hosts=allowed_hosts,
        sources=sources,
    )

