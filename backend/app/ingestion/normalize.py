"""Parse FINRA rule HTML into traceable, section-aware normalized documents."""

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

PARSER_VERSION = "finra-rule-parser-v3"
NORMALIZED_SCHEMA_VERSION = 2
RULE_BODY_SELECTOR = "#block-body .field--name-body"
GUIDANCE_BODY_SELECTOR = "#block-body, main"
SUPPLEMENTARY_PATTERN = re.compile(r"^\.(\d{2})\s+(.+)$", re.DOTALL)
TOP_LEVEL_PATTERN = re.compile(r"^\(([a-z])\)\s+(.+)$", re.DOTALL)
NUMBERED_PATTERN = re.compile(r"^\((\d+)\)\s+(.+)$", re.DOTALL)
EFFECTIVE_DATE_PATTERN = re.compile(
    r"\beff\.\s+([A-Z][a-z]{2,8}\.?)\s+(\d{1,2}),\s+(\d{4})",
)
SUPPLEMENTARY_MARKER_PATTERN = re.compile(
    r"\bSupplementary Material\s*:\s*-+",
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
    section_type: Literal["rule_text", "supplementary", "guidance"]
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
    rule_number: str | None
    title: str
    source_type: Literal["rule", "guidance"]
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


def _looks_like_inline_content(value: str) -> bool:
    return len(value) > 80 or any(mark in value for mark in (".", ";", ":", "?", "!"))


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _source_locator(
    *,
    element_index: int,
    text: str,
    selector: str = RULE_BODY_SELECTOR,
) -> SourceLocator:
    return SourceLocator(
        selector=f"{selector} > :nth-child({element_index + 1})",
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
    rule_sections: list[dict[str, Any]] = []
    supplementary_sections: list[NormalizedSection] = []
    excluded_elements: list[ExcludedElement] = []
    history: DocumentHistory | None = None
    substantive_source_parts: list[str] = []
    substantive_source_locators: list[SourceLocator] = []
    in_supplementary_material = False

    def record_substantive(text: str, locator: SourceLocator) -> None:
        substantive_source_parts.append(text)
        substantive_source_locators.append(locator)

    elements = [child for child in body.children if isinstance(child, Tag)]
    for element_index, child in enumerate(elements):
        text = _element_text(child)
        if not text:
            continue
        locator = _source_locator(element_index=element_index, text=text)
        # The footnote table is provenance, while the supplementary-material marker
        # is layout chrome; both are handled separately from rule text.
        if child.name == "table" and "footnote" in child.get("class", []):
            notices = tuple(_element_text(ref) for ref in child.find_all("ref"))
            history = DocumentHistory(
                source_text=text,
                selected_notices=notices,
                source_locator=locator,
            )
            record_substantive(text, locator)
            continue
        if SUPPLEMENTARY_MARKER_PATTERN.search(text):
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
            # FINRA sometimes puts continuation paragraphs below a .NN heading,
            # so unlabelled elements are appended to the preceding subsection.
            match = SUPPLEMENTARY_PATTERN.match(text)
            if not match:
                if not supplementary_sections:
                    raise ValueError(
                        f"{source.source_id}: supplementary content appeared before a "
                        f"section: {text[:80]!r}"
                    )
                previous = supplementary_sections[-1]
                supplementary_sections[-1] = replace(
                    previous,
                    content=(f"{previous.content}\n\n{text}").strip(),
                    source_locators=(*previous.source_locators, locator),
                )
                record_substantive(text, locator)
                continue
            number, remainder = match.groups()
            label = f".{number}"
            heading, separator, content = remainder.partition(". ")
            normalized_content = normalize_whitespace(content if separator else "")
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
            record_substantive(text, locator)
        else:
            top_match = TOP_LEVEL_PATTERN.fullmatch(text)
            numbered_match = NUMBERED_PATTERN.fullmatch(text)
            if top_match:
                label, heading = top_match.groups()
                content = [heading] if _looks_like_inline_content(heading) else []
                official_heading = None if content else heading
                rule_sections.append(
                    {
                        "label": f"({label})",
                        "heading": official_heading,
                        "content": content,
                        "locators": [locator],
                        "children": [],
                    }
                )
                record_substantive(text, locator)
                continue
            if numbered_match and rule_sections:
                label, heading = numbered_match.groups()
                content = [heading] if _looks_like_inline_content(heading) else []
                official_heading = None if content else heading
                rule_sections[-1]["children"].append(
                    {
                        "label": f"({label})",
                        "heading": official_heading,
                        "content": content,
                        "locators": [locator],
                    }
                )
                record_substantive(text, locator)
                continue
            if rule_sections:
                active = rule_sections[-1]
                target = active["children"][-1] if active["children"] else active
                target["content"].append(text)
                target["locators"].append(locator)
            else:
                main_paragraphs.append(text)
                main_locators.append(locator)
            record_substantive(text, locator)

    main_content = "\n\n".join(main_paragraphs)
    if not main_content and not rule_sections:
        raise ValueError(f"{source.source_id}: extracted rule text is empty")

    sections: list[NormalizedSection] = []
    if main_content:
        sections.append(
            NormalizedSection(
                label=None,
                heading=None,
                display_label="Main rule text",
                heading_source="synthetic",
                section_path=source.rule_number,
                section_type="rule_text",
                content=main_content,
                source_locators=tuple(main_locators),
            )
        )
    for section in rule_sections:
        section_title = section["heading"]
        section_path = (
            f"{source.rule_number} > {section['label']} {section_title}"
            if section_title
            else f"{source.rule_number} > {section['label']}"
        )
        if section["content"] or section["heading"]:
            sections.append(
                NormalizedSection(
                    label=section["label"],
                    heading=section_title,
                    display_label=(
                        f"{section['label']} {section_title}"
                        if section_title
                        else section["label"]
                    ),
                    heading_source="official",
                    section_path=section_path,
                    section_type="rule_text",
                    content="\n\n".join(section["content"]),
                    source_locators=tuple(section["locators"]),
                )
            )
        for child in section["children"]:
            child_title = child["heading"]
            child_content = list(child["content"])
            parent_context = "\n\n".join(section["content"])
            if not section["heading"] and parent_context and len(parent_context) <= 200:
                child_content.insert(0, parent_context)
            child_path = (
                f"{section_path} > {child['label']} {child_title}"
                if child_title
                else f"{section_path} > {child['label']}"
            )
            sections.append(
                NormalizedSection(
                    label=f"{section['label']}{child['label']}",
                    heading=child_title,
                    display_label=(
                        f"{child['label']} {child_title}"
                        if child_title
                        else child["label"]
                    ),
                    heading_source="official",
                    section_path=child_path,
                    section_type="rule_text",
                    content="\n\n".join(child_content),
                    source_locators=tuple(child["locators"]),
                )
            )
    sections.extend(supplementary_sections)
    source_text_by_index = {
        locator.element_index: text
        for locator, text in zip(
            substantive_source_locators,
            substantive_source_parts,
            strict=True,
        )
    }
    covered_locators = [
        locator
        for section in sections
        for locator in section.source_locators
    ]
    if history is not None:
        covered_locators.append(history.source_locator)
    source_indices = sorted(locator.element_index for locator in substantive_source_locators)
    covered_indices = sorted(locator.element_index for locator in covered_locators)
    source_characters = sum(len(source_text_by_index[index]) for index in source_indices)
    covered_characters = sum(
        len(source_text_by_index[index])
        for index in covered_indices
        if index in source_text_by_index
    )
    audit = NormalizationAudit(
        substantive_source_characters=source_characters,
        covered_substantive_characters=covered_characters,
        coverage_ratio=covered_characters / source_characters if source_characters else 0.0,
        exact_substantive_match=(
            source_indices == covered_indices and source_characters == covered_characters
        ),
        excluded_elements=tuple(excluded_elements),
    )
    if not audit.exact_substantive_match or audit.coverage_ratio != 1.0:
        missing = sorted(set(source_indices) - set(covered_indices))
        extra = sorted(set(covered_indices) - set(source_indices))
        raise ValueError(
            f"{source.source_id}: normalized content failed coverage validation "
            f"(missing={missing}, extra={extra})"
        )

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
        sections=tuple(sections),
        history=history,
        audit=audit,
    )
    return replace(
        document,
        normalized_content_hash=compute_normalized_content_hash(document),
    )


def parse_finra_guidance_html(
    html: bytes,
    *,
    source: Source,
    metadata: dict[str, Any],
) -> NormalizedDocument:
    """Normalize guidance headings, paragraphs, and lists into searchable sections."""
    if source.source_type is not SourceType.GUIDANCE:
        raise ValueError(f"{source.source_id}: guidance parser requires a guidance source")

    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("#block-body") or soup.select_one("main")
    if body is None:
        raise ValueError(f"{source.source_id}: guidance body was not found")

    sections: list[NormalizedSection] = []
    source_locators: list[SourceLocator] = []
    source_text_by_index: dict[int, str] = {}
    active: dict[str, Any] | None = None
    heading_stack: list[str] = []
    selector = "#block-body" if body.get("id") == "block-body" else "main"

    def flush() -> None:
        if active is None:
            return
        if not active["content"] and active["heading"]:
            # Keep standalone headings traceable even when the page places no
            # paragraph directly beneath them.
            active["content"].append(active["heading"])
        sections.append(
            NormalizedSection(
                label=None,
                heading=active["heading"],
                display_label=active["heading"] or "Guidance introduction",
                heading_source="official" if active["heading"] else "synthetic",
                section_path=" > ".join([source.title, *active["path"]]),
                section_type="guidance",
                content="\n\n".join(active["content"]),
                source_locators=tuple(active["locators"]),
            )
        )

    elements = body.find_all(["h1", "h2", "h3", "h4", "p", "li"])
    for element_index, element in enumerate(elements):
        text = _element_text(element)
        if not text:
            continue
        locator = _source_locator(
            element_index=element_index,
            text=text,
            selector=selector,
        )
        source_text_by_index[element_index] = text
        source_locators.append(locator)
        if element.name.startswith("h"):
            flush()
            level = int(element.name[1]) - 1
            heading_stack = heading_stack[:level]
            heading_stack.append(text)
            active = {
                "heading": text,
                "path": list(heading_stack),
                "content": [],
                "locators": [locator],
            }
            continue
        if active is None:
            active = {"heading": None, "path": [], "content": [], "locators": []}
        active["content"].append(text)
        active["locators"].append(locator)
    flush()

    if not sections:
        raise ValueError(f"{source.source_id}: extracted guidance content is empty")
    source_indices = sorted(locator.element_index for locator in source_locators)
    covered_indices = sorted(
        locator.element_index
        for section in sections
        for locator in section.source_locators
    )
    source_characters = sum(len(text) for text in source_text_by_index.values())
    covered_characters = sum(
        len(source_text_by_index[index])
        for index in covered_indices
        if index in source_text_by_index
    )
    audit = NormalizationAudit(
        substantive_source_characters=source_characters,
        covered_substantive_characters=covered_characters,
        coverage_ratio=covered_characters / source_characters if source_characters else 0.0,
        exact_substantive_match=source_indices == covered_indices,
        excluded_elements=(),
    )
    if not audit.exact_substantive_match or audit.coverage_ratio != 1.0:
        missing = sorted(set(source_indices) - set(covered_indices))
        extra = sorted(set(covered_indices) - set(source_indices))
        raise ValueError(
            f"{source.source_id}: guidance content failed coverage validation "
            f"(missing={missing}, extra={extra}, source_chars={source_characters}, "
            f"covered_chars={covered_characters})"
        )

    document = NormalizedDocument(
        schema_version=NORMALIZED_SCHEMA_VERSION,
        parser_version="finra-guidance-parser-v1",
        source_id=source.source_id,
        rule_number=source.rule_number,
        title=source.title,
        source_type="guidance",
        source_url=source.url,
        raw_snapshot_file=str(metadata["html_file"]),
        retrieved_at=str(metadata["retrieved_at"]),
        latest_effective_date=None,
        effective_date_evidence=None,
        raw_content_hash=sha256_bytes(html),
        normalized_content_hash="",
        sections=tuple(sections),
        history=None,
        audit=audit,
    )
    return replace(document, normalized_content_hash=compute_normalized_content_hash(document))


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


def normalize_guidance_snapshot(
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
    if metadata.get("content_sha256") != sha256_bytes(html):
        raise ValueError(f"{source.source_id}: raw snapshot hash does not match metadata")
    return parse_finra_guidance_html(html, source=source, metadata=metadata)


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
