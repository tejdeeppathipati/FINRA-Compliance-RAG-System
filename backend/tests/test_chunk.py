"""Verify legal sections remain intact and oversized sections overlap safely."""

from dataclasses import replace
from pathlib import Path

import pytest

from app.ingestion.chunk import ChunkSettings, chunk_document
from app.ingestion.fetch import sha256_bytes
from app.ingestion.manifest import Source, SourceType
from app.ingestion.normalize import parse_finra_rule_html

SOURCE = Source(
    source_id="finra-rule-2090",
    rule_number="2090",
    title="Know Your Customer",
    source_type=SourceType.RULE,
    url="https://www.finra.org/rules-guidance/rulebooks/finra-rules/2090",
)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "finra_rule_2090.html"


def metadata_for(html: bytes) -> dict[str, object]:
    return {
        "source_id": SOURCE.source_id,
        "retrieved_at": "2026-08-03T15:00:53+00:00",
        "content_sha256": sha256_bytes(html),
        "html_file": "snapshot.html",
    }


def _document():
    html = FIXTURE_PATH.read_bytes()
    return parse_finra_rule_html(html, source=SOURCE, metadata=metadata_for(html))


def test_short_sections_remain_intact() -> None:
    chunks = chunk_document(_document(), ChunkSettings(target_tokens=100, overlap_tokens=10))

    assert len(chunks) == 2
    assert [chunk.section_path for chunk in chunks] == [
        "2090",
        "2090 > Supplementary Material > .01 Essential Facts",
    ]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]


def test_long_sections_split_with_overlap() -> None:
    document = _document()
    long_section = replace(
        document.sections[0],
        content=" ".join(f"word{i}" for i in range(25)),
    )
    document = replace(document, sections=(long_section, document.sections[1]))
    chunks = chunk_document(document, ChunkSettings(target_tokens=10, overlap_tokens=2))

    assert chunks[0].content.split()[-2:] == chunks[1].content.split()[:2]
    assert all(chunk.token_count <= 10 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunk_settings_reject_invalid_overlap() -> None:
    with pytest.raises(ValueError, match="smaller than"):
        ChunkSettings(target_tokens=10, overlap_tokens=10)
