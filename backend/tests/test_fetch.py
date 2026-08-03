import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.ingestion.fetch import FetchSettings, fetch_source, request_with_retry
from app.ingestion.manifest import Source, SourceType

SOURCE = Source(
    source_id="finra-rule-2090",
    rule_number="2090",
    title="Know Your Customer",
    source_type=SourceType.RULE,
    url="https://www.finra.org/rules/2090",
)
FIXED_TIME = datetime(2026, 8, 3, 15, 0, tzinfo=UTC)


async def no_sleep(_: float) -> None:
    return None


def make_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, follow_redirects=True)


def test_fetch_source_writes_snapshot_and_metadata(tmp_path: Path) -> None:
    content = b"<html><main>FINRA Rule 2090</main></html>" + (b" " * 1_000)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=content,
            headers={"content-type": "text/html; charset=UTF-8", "etag": '"test"'},
        )

    async def execute() -> dict[str, object]:
        async with make_client(httpx.MockTransport(handler)) as client:
            return await fetch_source(
                client,
                SOURCE,
                allowed_hosts=frozenset({"www.finra.org"}),
                output_dir=tmp_path,
                settings=FetchSettings(attempts=1, delay_seconds=0),
                now=lambda: FIXED_TIME,
                sleep=no_sleep,
            )

    result = asyncio.run(execute())
    html_path = Path(str(result["html_path"]))
    metadata_path = Path(str(result["metadata_path"]))
    metadata = json.loads(metadata_path.read_text())

    assert result["status"] == "saved"
    assert html_path.read_bytes() == content
    assert metadata["source_id"] == SOURCE.source_id
    assert metadata["retrieved_at"] == "2026-08-03T15:00:00+00:00"
    assert metadata["content_length_bytes"] == len(content)
    assert metadata["html_file"] == html_path.name


def test_fetch_source_does_not_duplicate_identical_raw_content(tmp_path: Path) -> None:
    content = b"<html><main>FINRA Rule 2090</main></html>" + (b" " * 1_000)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=content,
            headers={"content-type": "text/html"},
        )

    async def execute() -> tuple[dict[str, object], dict[str, object]]:
        async with make_client(httpx.MockTransport(handler)) as client:
            arguments = {
                "allowed_hosts": frozenset({"www.finra.org"}),
                "output_dir": tmp_path,
                "settings": FetchSettings(attempts=1, delay_seconds=0),
                "now": lambda: FIXED_TIME,
                "sleep": no_sleep,
            }
            first = await fetch_source(client, SOURCE, **arguments)
            second = await fetch_source(client, SOURCE, **arguments)
            return first, second

    first, second = asyncio.run(execute())

    assert first["status"] == "saved"
    assert second["status"] == "unchanged"
    assert len(list((tmp_path / SOURCE.source_id).glob("*.html"))) == 1
    assert len(list((tmp_path / SOURCE.source_id).glob("*.metadata.json"))) == 1


def test_fetch_source_rejects_redirect_outside_allowlist(tmp_path: Path) -> None:
    content = b"<html><main>unexpected host</main></html>" + (b" " * 1_000)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.finra.org":
            return httpx.Response(
                302,
                request=request,
                headers={"location": "https://example.com/rules/2090"},
            )
        return httpx.Response(
            200,
            request=request,
            content=content,
            headers={"content-type": "text/html"},
        )

    async def execute() -> None:
        async with make_client(httpx.MockTransport(handler)) as client:
            await fetch_source(
                client,
                SOURCE,
                allowed_hosts=frozenset({"www.finra.org"}),
                output_dir=tmp_path,
                settings=FetchSettings(attempts=1, delay_seconds=0),
                sleep=no_sleep,
            )

    with pytest.raises(ValueError, match="redirect ended on non-approved host"):
        asyncio.run(execute())


def test_request_retries_server_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        status = 503 if calls == 1 else 200
        return httpx.Response(status, request=request, content=b"ok")

    async def execute() -> httpx.Response:
        async with make_client(httpx.MockTransport(handler)) as client:
            return await request_with_retry(client, SOURCE, attempts=2, sleep=no_sleep)

    response = asyncio.run(execute())

    assert response.status_code == 200
    assert calls == 2
