from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.ingestion.manifest import Source, SourceManifest
from app.ingestion.metadata import SnapshotMetadata, read_latest_metadata

LOGGER = logging.getLogger(__name__)
FETCHER_VERSION = "finra-fetcher-v1"
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class FetchSettings:
    attempts: int = 3
    delay_seconds: float = 5.0
    minimum_content_bytes: int = 1_000

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least 1")
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds cannot be negative")
        if self.minimum_content_bytes < 1:
            raise ValueError("minimum_content_bytes must be positive")


def utc_now() -> datetime:
    return datetime.now(UTC)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _retry_delay(attempt: int, *, rate_limited: bool) -> float:
    base = 10 if rate_limited else 5
    return min(base * (2 ** (attempt - 1)), 60) + random.uniform(0, 1)


async def request_with_retry(
    client: httpx.AsyncClient,
    source: Source,
    *,
    attempts: int,
    sleep: Sleep = asyncio.sleep,
) -> httpx.Response:
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(source.url)
            if response.status_code == 429:
                response.raise_for_status() if attempt == attempts else None
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else _retry_delay(attempt, rate_limited=True)
                )
                LOGGER.warning(
                    "%s rate-limited on attempt %s/%s; retrying in %.2fs",
                    source.source_id,
                    attempt,
                    attempts,
                    delay,
                )
                await sleep(delay)
                continue

            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
            last_error = error
            if attempt == attempts:
                break
            delay = _retry_delay(attempt, rate_limited=False)
            LOGGER.warning(
                "%s failed on attempt %s/%s: %s; retrying in %.2fs",
                source.source_id,
                attempt,
                attempts,
                error,
                delay,
            )
            await sleep(delay)

    if last_error is None:
        raise RuntimeError(f"{source.source_id}: request failed without an error")
    raise last_error


def _atomic_write(path: Path, content: bytes) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_bytes(content)
    temporary_path.replace(path)


async def fetch_source(
    client: httpx.AsyncClient,
    source: Source,
    *,
    allowed_hosts: frozenset[str],
    output_dir: Path,
    settings: FetchSettings,
    now: Callable[[], datetime] = utc_now,
    sleep: Sleep = asyncio.sleep,
) -> dict[str, Any]:
    source_dir = output_dir / source.source_id
    source_dir.mkdir(parents=True, exist_ok=True)

    response = await request_with_retry(
        client,
        source,
        attempts=settings.attempts,
        sleep=sleep,
    )
    retrieved_at = now()
    final_url = str(response.url)
    final_host = urlparse(final_url).hostname
    if final_host not in allowed_hosts:
        raise ValueError(
            f"{source.source_id}: redirect ended on non-approved host {final_host!r}"
        )

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type.lower():
        raise ValueError(f"{source.source_id}: expected HTML but received {content_type!r}")

    content = response.content
    if len(content) < settings.minimum_content_bytes:
        raise ValueError(
            f"{source.source_id}: response is unexpectedly small ({len(content)} bytes)"
        )

    digest = sha256_bytes(content)
    previous = read_latest_metadata(source_dir)
    if previous and previous.get("content_sha256") == digest:
        LOGGER.info("%s unchanged; no duplicate snapshot written", source.source_id)
        return {
            "source_id": source.source_id,
            "status": "unchanged",
            "content_sha256": digest,
            "bytes": len(content),
        }

    timestamp = retrieved_at.strftime("%Y%m%dT%H%M%SZ")
    stem = f"{timestamp}-{digest[:12]}"
    html_path = source_dir / f"{stem}.html"
    metadata_path = source_dir / f"{stem}.metadata.json"
    metadata = SnapshotMetadata.create(
        source_id=source.source_id,
        rule_number=source.rule_number,
        title=source.title,
        source_type=source.source_type.value,
        requested_url=source.url,
        final_url=final_url,
        retrieved_at=retrieved_at,
        http_status=response.status_code,
        content_type=content_type,
        content_length_bytes=len(content),
        content_sha256=digest,
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
        html_file=html_path.name,
        fetcher_version=FETCHER_VERSION,
    )

    _atomic_write(html_path, content)
    _atomic_write(metadata_path, metadata.to_json().encode())
    LOGGER.info("%s saved: %s bytes, sha256=%s", source.source_id, len(content), digest)
    if settings.delay_seconds:
        await sleep(settings.delay_seconds)

    return {
        "source_id": source.source_id,
        "status": "saved",
        "content_sha256": digest,
        "bytes": len(content),
        "html_path": str(html_path),
        "metadata_path": str(metadata_path),
    }


def build_http_client(*, contact: str) -> httpx.AsyncClient:
    if not contact.strip():
        raise ValueError("A truthful contact address is required for the fetch user agent")
    return httpx.AsyncClient(
        headers={
            "User-Agent": (
                "FINRAComplianceRAG/0.1 "
                f"(educational compliance research project; contact: {contact.strip()})"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.8",
        },
        follow_redirects=True,
        timeout=httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=15.0),
        limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
    )


async def fetch_manifest(
    manifest: SourceManifest,
    *,
    output_dir: Path,
    contact: str,
    source_ids: set[str] | None = None,
    settings: FetchSettings | None = None,
) -> tuple[list[dict[str, Any]], Path]:
    active_settings = settings or FetchSettings()
    selected_sources = manifest.select(source_ids)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    async with build_http_client(contact=contact) as client:
        for source in selected_sources:
            try:
                result = await fetch_source(
                    client,
                    source,
                    allowed_hosts=manifest.allowed_hosts,
                    output_dir=output_dir,
                    settings=active_settings,
                )
            except Exception as error:  # Continue to produce a complete corpus report.
                LOGGER.exception("Failed to fetch %s", source.source_id)
                result = {
                    "source_id": source.source_id,
                    "status": "failed",
                    "error": str(error),
                }
            results.append(result)

    summary_path = output_dir / "fetch_summary.json"
    summary = {
        "run_at": utc_now().isoformat(),
        "manifest_version": manifest.version,
        "corpus_name": manifest.corpus_name,
        "results": results,
    }
    _atomic_write(summary_path, (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode())
    return results, summary_path
