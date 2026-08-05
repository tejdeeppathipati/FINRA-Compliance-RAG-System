from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.ingestion.manifest import SourceType, load_manifest
from app.ingestion.normalize import (
    latest_snapshot_paths,
    normalize_rule_snapshot,
    write_normalized_document,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_MANIFEST = Path("data/source_manifest.yaml")
DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_OUTPUT_DIR = Path("data/normalized")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize saved FINRA rule snapshots.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--source-id",
        action="append",
        required=True,
        help="Normalize this rule source ID; repeat for multiple rules.",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    sources = manifest.select(set(args.source_id))
    failures = 0
    for source in sources:
        try:
            if source.source_type is not SourceType.RULE:
                raise ValueError(f"{source.source_id}: guidance parsing is not implemented yet")
            html_path, metadata_path = latest_snapshot_paths(args.raw_dir, source)
            document = normalize_rule_snapshot(
                html_path=html_path,
                metadata_path=metadata_path,
                source=source,
            )
            output_path = write_normalized_document(document, args.output)
            LOGGER.info(
                "%s normalized into %s sections: %s",
                source.source_id,
                len(document.sections),
                output_path,
            )
        except (OSError, ValueError):
            failures += 1
            LOGGER.exception("Failed to normalize %s", source.source_id)
    return 1 if failures else 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(run(parse_args()))


if __name__ == "__main__":
    main()
