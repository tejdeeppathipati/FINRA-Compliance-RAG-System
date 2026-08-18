"""Verify manifest validation prevents out-of-scope or malformed sources."""

from pathlib import Path

import pytest

from app.ingestion.manifest import SourceType, load_manifest


def write_manifest(tmp_path: Path, sources: str, *, allowed_host: str = "www.finra.org") -> Path:
    path = tmp_path / "manifest.yaml"
    path.write_text(
        f"""version: 1
corpus_name: test-corpus
scope: finra-only
allowed_hosts:
  - {allowed_host}
sources:
{sources}
""",
        encoding="utf-8",
    )
    return path


def test_project_manifest_has_expected_corpus() -> None:
    manifest_path = Path(__file__).parents[2] / "data" / "source_manifest.yaml"
    manifest = load_manifest(manifest_path)

    assert manifest.scope == "finra-only"
    assert manifest.allowed_hosts == frozenset({"www.finra.org"})
    assert len(manifest.sources) == 13
    assert len({source.source_id for source in manifest.sources}) == 13
    assert sum(source.source_type is SourceType.RULE for source in manifest.sources) == 8
    assert sum(source.source_type is SourceType.GUIDANCE for source in manifest.sources) == 5


def test_manifest_rejects_non_allowlisted_host(tmp_path: Path) -> None:
    path = write_manifest(
        tmp_path,
        """  - source_id: finra-rule-2090
    rule_number: "2090"
    title: Know Your Customer
    source_type: rule
    url: https://example.com/rule/2090
""",
    )

    with pytest.raises(ValueError, match="not allow-listed"):
        load_manifest(path)


def test_manifest_rejects_rule_without_number(tmp_path: Path) -> None:
    path = write_manifest(
        tmp_path,
        """  - source_id: finra-rule-2090
    title: Know Your Customer
    source_type: rule
    url: https://www.finra.org/rule/2090
""",
    )

    with pytest.raises(ValueError, match="require a rule_number"):
        load_manifest(path)


def test_manifest_selection_preserves_manifest_order(tmp_path: Path) -> None:
    path = write_manifest(
        tmp_path,
        """  - source_id: finra-rule-2090
    rule_number: "2090"
    title: Know Your Customer
    source_type: rule
    url: https://www.finra.org/rule/2090
  - source_id: finra-guidance-supervision
    rule_number: "3110"
    title: Supervision Guidance
    source_type: guidance
    url: https://www.finra.org/guidance/supervision
""",
    )
    manifest = load_manifest(path)

    selected = manifest.select({"finra-guidance-supervision", "finra-rule-2090"})

    assert [source.source_id for source in selected] == [
        "finra-rule-2090",
        "finra-guidance-supervision",
    ]
    with pytest.raises(ValueError, match="Unknown source IDs: missing"):
        manifest.select({"missing"})
