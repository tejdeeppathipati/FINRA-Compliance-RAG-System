"""Verify rule parsing, provenance, hashes, and substantive coverage audits."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.ingestion.fetch import sha256_bytes
from app.ingestion.manifest import Source, SourceType
from app.ingestion.normalize import (
    compute_normalized_content_hash,
    normalize_rule_snapshot,
    parse_finra_guidance_html,
    parse_finra_rule_html,
    write_normalized_document,
)

SOURCE = Source(
    source_id="finra-rule-2090",
    rule_number="2090",
    title="Know Your Customer",
    source_type=SourceType.RULE,
    url="https://www.finra.org/rules-guidance/rulebooks/finra-rules/2090",
)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "finra_rule_2090.html"
RETRIEVED_AT = "2026-08-03T15:00:53+00:00"


def metadata_for(html: bytes, *, html_file: str = "snapshot.html") -> dict[str, object]:
    return {
        "source_id": SOURCE.source_id,
        "retrieved_at": RETRIEVED_AT,
        "content_sha256": sha256_bytes(html),
        "html_file": html_file,
    }


def test_rule_parser_extracts_only_authoritative_body() -> None:
    html = FIXTURE_PATH.read_bytes()
    document = parse_finra_rule_html(html, source=SOURCE, metadata=metadata_for(html))

    assert document.latest_effective_date == "2012-07-09"
    assert document.effective_date_evidence is not None
    assert document.effective_date_evidence.source_text.startswith("Adopted")
    assert document.effective_date_evidence.source_text.endswith("July 9, 2012.")
    assert document.raw_content_hash == sha256_bytes(html)
    assert len(document.normalized_content_hash) == 64
    assert [section.section_type for section in document.sections] == [
        "rule_text",
        "supplementary",
    ]
    assert document.sections[0].section_path == "2090"
    assert document.sections[0].heading is None
    assert document.sections[0].display_label == "Main rule text"
    assert document.sections[0].heading_source == "synthetic"
    assert document.sections[1].label == ".01"
    assert document.sections[1].heading == "Essential Facts"
    assert document.sections[1].heading_source == "official"
    assert document.sections[1].source_locators[0].selector.endswith(":nth-child(4)")
    assert len(document.sections[1].source_locators[0].source_text_hash) == 64
    assert document.history is not None
    assert document.history.selected_notices == ("11-02",)
    assert document.audit.coverage_ratio == 1.0
    assert document.audit.exact_substantive_match is True
    assert document.audit.excluded_elements[0].reason == (
        "decorative supplementary-material marker"
    )
    assert "navigation" not in document.to_json()
    assert "footer" not in document.to_json()


def test_normalized_hash_ignores_volatile_markup_and_retrieval_time() -> None:
    html = FIXTURE_PATH.read_bytes()
    changed_html = html.replace(b"request-token-one", b"request-token-two")
    original = parse_finra_rule_html(html, source=SOURCE, metadata=metadata_for(html))
    changed = parse_finra_rule_html(
        changed_html,
        source=SOURCE,
        metadata={**metadata_for(changed_html), "retrieved_at": "2026-08-04T10:00:00+00:00"},
    )

    assert original.raw_content_hash != changed.raw_content_hash
    assert original.normalized_content_hash == changed.normalized_content_hash


def test_content_change_changes_normalized_hash() -> None:
    html = FIXTURE_PATH.read_bytes()
    document = parse_finra_rule_html(html, source=SOURCE, metadata=metadata_for(html))
    first_section = replace(document.sections[0], content="Materially changed rule content")
    changed = replace(document, sections=(first_section, *document.sections[1:]))

    assert compute_normalized_content_hash(changed) != document.normalized_content_hash


def test_normalized_hash_ignores_parser_and_synthetic_display_changes() -> None:
    html = FIXTURE_PATH.read_bytes()
    document = parse_finra_rule_html(html, source=SOURCE, metadata=metadata_for(html))
    first_section = replace(document.sections[0], display_label="Different UI label")
    changed = replace(
        document,
        parser_version="future-parser-version",
        sections=(first_section, *document.sections[1:]),
    )

    assert compute_normalized_content_hash(changed) == document.normalized_content_hash


def test_snapshot_normalization_validates_raw_hash_and_writes_json(tmp_path: Path) -> None:
    html = FIXTURE_PATH.read_bytes()
    html_path = tmp_path / "snapshot.html"
    metadata_path = tmp_path / "snapshot.metadata.json"
    html_path.write_bytes(html)
    metadata_path.write_text(
        json.dumps(metadata_for(html, html_file=html_path.name)),
        encoding="utf-8",
    )

    document = normalize_rule_snapshot(
        html_path=html_path,
        metadata_path=metadata_path,
        source=SOURCE,
    )
    output_path = write_normalized_document(document, tmp_path / "normalized")
    output = json.loads(output_path.read_text())

    assert output["source_id"] == SOURCE.source_id
    assert output["normalized_content_hash"] == document.normalized_content_hash
    assert output_path.parent.name == SOURCE.source_id


def test_snapshot_normalization_rejects_hash_mismatch(tmp_path: Path) -> None:
    html = FIXTURE_PATH.read_bytes()
    html_path = tmp_path / "snapshot.html"
    metadata_path = tmp_path / "snapshot.metadata.json"
    html_path.write_bytes(html)
    metadata = metadata_for(html, html_file=html_path.name)
    metadata["content_sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="raw snapshot hash does not match metadata"):
        normalize_rule_snapshot(
            html_path=html_path,
            metadata_path=metadata_path,
            source=SOURCE,
        )


def test_supplementary_marker_is_not_triggered_by_rule_body_reference() -> None:
    source = replace(SOURCE, source_id="finra-rule-4512", rule_number="4512")
    html = b"""
    <html><body><div id="block-body"><div class="field--name-body">
      <div>(a) Each member shall maintain information subject to Supplementary Material .06.</div>
      <div>(1) The member shall record the account information.</div>
      <hr />
      <p><strong>Supplementary Material: --------------</strong></p>
      <p><strong>.01 Trusted Contact Person.</strong> The member may contact the
      trusted contact.</p>
      <table class="table footnote"><tr><td>Adopted by SR-FINRA-2010-052 eff.
      Dec. 5, 2011.</td></tr></table>
    </div></div></body></html>
    """
    document = parse_finra_rule_html(html, source=source, metadata=metadata_for(html))

    assert document.sections[0].section_path == "4512 > (a)"
    assert "Supplementary Material .06" in document.sections[0].content
    assert document.sections[-1].label == ".01"
    assert document.audit.exact_substantive_match is True


def test_guidance_parser_preserves_heading_paths_and_lists() -> None:
    source = Source(
        source_id="finra-guidance-bcp",
        rule_number=None,
        title="Business Continuity Planning Guidance",
        source_type=SourceType.GUIDANCE,
        url="https://www.finra.org/rules-guidance/key-topics/business-continuity-planning",
    )
    html = b"""
    <html><body><main>
      <h1>Business Continuity Planning</h1>
      <p>Firms must maintain written continuity plans.</p>
      <h2>What to Include</h2>
      <p>The plan should address critical operations.</p>
      <ul><li>Data backup and recovery.</li><li>Alternate communications.</li></ul>
    </main></body></html>
    """
    document = parse_finra_guidance_html(
        html,
        source=source,
        metadata={
            "source_id": source.source_id,
            "retrieved_at": RETRIEVED_AT,
            "html_file": "guidance.html",
        },
    )

    assert document.source_type == "guidance"
    assert document.rule_number is None
    assert len(document.sections) == 2
    assert document.sections[1].section_path.endswith(" > What to Include")
    assert "Data backup" in document.sections[1].content
    assert document.audit.exact_substantive_match is True
