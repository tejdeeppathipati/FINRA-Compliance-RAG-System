from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from app.ingestion.fetch import FetchSettings, fetch_manifest
from app.ingestion.manifest import load_manifest

DEFAULT_MANIFEST = Path("data/source_manifest.yaml")
DEFAULT_OUTPUT = Path("data/raw")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch versioned HTML snapshots from the approved FINRA manifest."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--source-id",
        action="append",
        help="Fetch only this source ID; repeat for multiple sources.",
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--delay", type=float, default=5.0)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    contact = os.getenv("FINRA_FETCH_CONTACT", "").strip()
    if not contact:
        raise RuntimeError(
            "Set FINRA_FETCH_CONTACT to a real contact email before fetching. "
            "Example: export FINRA_FETCH_CONTACT='you@example.com'"
        )

    manifest = load_manifest(args.manifest)
    results, summary_path = await fetch_manifest(
        manifest,
        output_dir=args.output,
        contact=contact,
        source_ids=set(args.source_id) if args.source_id else None,
        settings=FetchSettings(attempts=args.attempts, delay_seconds=args.delay),
    )
    failures = [result for result in results if result["status"] == "failed"]
    logging.getLogger(__name__).info(
        "Fetch complete: %s succeeded/unchanged, %s failed; summary: %s",
        len(results) - len(failures),
        len(failures),
        summary_path,
    )
    return 1 if failures else 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args()
    try:
        exit_code = asyncio.run(run(args))
    except (ValueError, RuntimeError, OSError) as error:
        logging.getLogger(__name__).error("%s", error)
        exit_code = 2
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

