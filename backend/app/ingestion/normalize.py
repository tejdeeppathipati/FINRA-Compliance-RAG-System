from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from bs4 import BeautifulSoup, Tag

from app.ingestion.fetch import sha256_bytes
from app.ingestion.manifest import Source, SourceType

PARSER_VERSION = "finra-rule-parser-v2"
NORMALIZED_SCHEMA_VERSION = 2
RULE_BODY_SELECTOR = "#block-body .field--name-body"
SUPPLEMENTARY_PATTERN = re.compile(r"^\.(\d{2})\s+(.+?)\.\s*(.*)$", re.DOTALL)
EFFECTIVE_DATE_PATTERN = re.compile(
    r"\beff\.\s+([A-Z][a-z]{2,8}\.?)\s+(\d{1,2}),\s+(\d{4})",
)


@dataclass(frozen=True, slots=True)
class SourceLocator:
    selector: str
    element_index: int
    source_text_hash: str


@dataclass(frozen=True, slots=True)
class NormalizedSection:
    label: str | None
    heading: str | None
    display_label: str
    heading_source: Literal["official", "synthetic"]
    section_path: str
    section_type: Literal["rule_text", "supplementary"]
    content: str
    source_locators: tuple[SourceLocator, ...]


@dataclass(frozen=True, slots=True)
class EffectiveDateEvidence:
    date: str
    source_text: str
    confidence: Literal["explicit"] = "explicit"


@dataclass(frozen=True, slots=True)
class DocumentHistory:
    source_text: str
    selected_notices: tuple[str, ...]
    source_locator: SourceLocator


@dataclass(frozen=True, slots=True)
class ExcludedElement:
    text: str
    reason: str
    source_locator: SourceLocator


@dataclass(frozen=True, slots=True)
class NormalizationAudit:
    substantive_source_characters: int
    covered_substantive_characters: int
    coverage_ratio: float
    exact_substantive_match: bool
    excluded_elements: tuple[ExcludedElement, ...]


@dataclass(frozen=True, slots=True)
class NormalizedDocument:
    schema_version: int
    parser_version: str
    source_id: str
    rule_number: str
    title: str
    source_type: Literal["rule"]
    source_url: str
    raw_snapshot_file: str
    retrieved_at: str
    latest_effective_date: str | None
    effective_date_evidence: EffectiveDateEvidence | None
    raw_content_hash: str
    normalized_content_hash: str
    sections: tuple[NormalizedSection, ...]
    history: DocumentHistory | None
    audit: NormalizationAudit

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


def normalize_whitespace(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _element_text(element: Tag) -> str:
    return normalize_whitespace(element.get_text(" ", strip=True))


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _source_locator(*, element_index: int, text: str) -> SourceLocator:
    return SourceLocator(
        selector=f"{RULE_BODY_SELECTOR} > :nth-child({element_index + 1})",
        element_index=element_index,
        source_text_hash=_text_hash(text),
    )


def _extract_effective_date(history: str | None) -> EffectiveDateEvidence | None:
    if not history:
        return None
    match = EFFECTIVE_DATE_PATTERN.search(history)
    if not match:
        return None
    month, day, year = match.groups()
    cleaned_month = month.rstrip(".")
    try:
        value = datetime.strptime(f"{cleaned_month} {day} {year}", "%b %d %Y")
    except ValueError:
        value = datetime.strptime(f"{cleaned_month} {day} {year}", "%B %d %Y")
    previous_sentence_end = history.rfind(". ", 0, match.start())
    sentence_start = 0 if previous_sentence_end == -1 else previous_sentence_end + 2
    sentence_end = history.find(". ", match.end())
    if sentence_end == -1:
        sentence_end = len(history)
    else:
        sentence_end += 1
    return EffectiveDateEvidence(
        date=value.date().isoformat(),
        source_text=history[sentence_start:sentence_end],
    )


def _normalized_hash_payload(document: NormalizedDocument) -> dict[str, Any]:
    return {
        "rule_number": document.rule_number,
        "title": document.title,
        "source_type": document.source_type,
        "source_url": document.source_url,
        "latest_effective_date": document.latest_effective_date,
        "sections": [
            {
                "label": section.label,
                "heading": section.heading,
                "section_type": section.section_type,
                "content": section.content,
            }
            for section in document.sections
        ],
        "history": document.history.source_text if document.history else None,
    }


def compute_normalized_content_hash(document: NormalizedDocument) -> str:
    canonical = json.dumps(
        _normalized_hash_payload(document),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def parse_finra_rule_html(
    html: bytes,
    *,
    source: Source,
    metadata: dict[str, Any],
) -> NormalizedDocument:
    if source.source_type is not SourceType.RULE or source.rule_number is None:
        raise ValueError(f"{source.source_id}: rule parser requires a rule source")

    soup = BeautifulSoup(html, "html.parser")
    bodies = soup.select(RULE_BODY_SELECTOR)
    if len(bodies) != 1:
        raise ValueError(
            f"{source.source_id}: expected exactly one FINRA rule body, found {len(bodies)}"
        )
    body = bodies[0]

    main_paragraphs: list[str] = []
    main_locators: list[SourceLocator] = []
    supplementary_sections: list[NormalizedSection] = []
    excluded_elements: list[ExcludedElement] = []
    history: DocumentHistory | None = None
    substantive_source_parts: list[str] = []
    covered_substantive_parts: list[str] = []
    in_supplementary_material = False

    elements = [child for child in body.children if isinstance(child, Tag)]
    for element_index, child in enumerate(elements):
        text = _element_text(child)
        if not text:
            continue
        locator = _source_locator(element_index=element_index, text=text)
        if child.name == "table" and "footnote" in child.get("class", []):
            notices = tuple(_element_text(ref) for ref in child.find_all("ref"))
            history = DocumentHistory(
                source_text=text,
                selected_notices=notices,
                source_locator=locator,
            )
            substantive_source_parts.append(text)
            covered_substantive_parts.append(text)
            continue
        if "Supplementary Material" in text:
            in_supplementary_material = True
            excluded_elements.append(
                ExcludedElement(
                    text=text,
                    reason="decorative supplementary-material marker",
                    source_locator=locator,
                )
            )
            continue
        if in_supplementary_material:
            match = SUPPLEMENTARY_PATTERN.match(text)
            if not match:
                raise ValueError(
                    f"{source.source_id}: unrecognized supplementary section: {text[:80]!r}"
                )
            number, heading, content = match.groups()
            label = f".{number}"
            normalized_content = normalize_whitespace(content)
            supplementary_sections.append(
                NormalizedSection(
                    label=label,
                    heading=heading,
                    display_label=f"{label} {heading}",
                    heading_source="official",
                    section_path=(
                        f"{source.rule_number} > Supplementary Material > {label} {heading}"
                    ),
                    section_type="supplementary",
                    content=normalized_content,
                    source_locators=(locator,),
                )
            )
            substantive_source_parts.extend((heading, normalized_content))
            covered_substantive_parts.extend((heading, normalized_content))
        else:
            main_paragraphs.append(text)
            main_locators.append(locator)
            substantive_source_parts.append(text)
            covered_substantive_parts.append(text)

    main_content = "\n\n".join(main_paragraphs)
    if not main_content:
        raise ValueError(f"{source.source_id}: extracted rule text is empty")

    sections = (
        NormalizedSection(
            label=None,
            heading=None,
            display_label="Main rule text",
            heading_source="synthetic",
            section_path=source.rule_number,
            section_type="rule_text",
            content=main_content,
            source_locators=tuple(main_locators),
        ),
        *supplementary_sections,
    )
    source_substantive = "\n".join(substantive_source_parts)
    covered_substantive = "\n".join(covered_substantive_parts)
    source_characters = len(source_substantive)
    covered_characters = len(covered_substantive)
    audit = NormalizationAudit(
        substantive_source_characters=source_characters,
        covered_substantive_characters=covered_characters,
        coverage_ratio=covered_characters / source_characters if source_characters else 0.0,
        exact_substantive_match=source_substantive == covered_substantive,
        excluded_elements=tuple(excluded_elements),
    )
    if not audit.exact_substantive_match or audit.coverage_ratio != 1.0:
        raise ValueError(f"{source.source_id}: normalized content failed coverage validation")

    history_text = history.source_text if history else None
    effective_date_evidence = _extract_effective_date(history_text)
    document = NormalizedDocument(
        schema_version=NORMALIZED_SCHEMA_VERSION,
        parser_version=PARSER_VERSION,
        source_id=source.source_id,
        rule_number=source.rule_number,
        title=source.title,
        source_type="rule",
        source_url=source.url,
        raw_snapshot_file=str(metadata["html_file"]),
        retrieved_at=str(metadata["retrieved_at"]),
        latest_effective_date=(effective_date_evidence.date if effective_date_evidence else None),
        effective_date_evidence=effective_date_evidence,
        raw_content_hash=sha256_bytes(html),
        normalized_content_hash="",
        sections=sections,
        history=history,
        audit=audit,
    )
    return replace(
        document,
        normalized_content_hash=compute_normalized_content_hash(document),
    )


def normalize_rule_snapshot(
    *,
    html_path: Path,
    metadata_path: Path,
    source: Source,
) -> NormalizedDocument:
    html = html_path.read_bytes()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError(f"{metadata_path}: metadata root must be an object")
    if metadata.get("source_id") != source.source_id:
        raise ValueError(f"{source.source_id}: snapshot metadata source_id does not match manifest")
    if metadata.get("html_file") != html_path.name:
        raise ValueError(f"{source.source_id}: metadata html_file does not match snapshot filename")
    raw_hash = sha256_bytes(html)
    if metadata.get("content_sha256") != raw_hash:
        raise ValueError(f"{source.source_id}: raw snapshot hash does not match metadata")
    return parse_finra_rule_html(html, source=source, metadata=metadata)


def latest_snapshot_paths(raw_dir: Path, source: Source) -> tuple[Path, Path]:
    source_dir = raw_dir / source.source_id
    metadata_paths = sorted(source_dir.glob("*.metadata.json"), reverse=True)
    if not metadata_paths:
        raise ValueError(f"{source.source_id}: no raw snapshot metadata found")
    metadata_path = metadata_paths[0]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    html_name = metadata.get("html_file") if isinstance(metadata, dict) else None
    if not isinstance(html_name, str) or not html_name:
        raise ValueError(f"{metadata_path}: missing html_file")
    return source_dir / html_name, metadata_path


def write_normalized_document(document: NormalizedDocument, output_dir: Path) -> Path:
    source_dir = output_dir / document.source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.fromisoformat(document.retrieved_at)
    timestamp = retrieved_at.strftime("%Y%m%dT%H%M%SZ")
    output_path = source_dir / f"{timestamp}-{document.normalized_content_hash[:12]}.json"
    temporary_path = output_path.with_suffix(".json.tmp")
    temporary_path.write_text(document.to_json(), encoding="utf-8")
    temporary_path.replace(output_path)
    return output_path
