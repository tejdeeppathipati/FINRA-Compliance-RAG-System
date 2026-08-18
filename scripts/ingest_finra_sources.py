"""CLI entry point for normalizing, chunking, and indexing rule snapshots."""

from __future__ import annotations

import argparse
import logging
from functools import partial
from pathlib import Path

from app.db.session import SessionLocal
from app.ingestion.chunk import ChunkSettings
from app.ingestion.embed import embed_text, embedding_model_name
from app.ingestion.ingest import ingest_source_snapshot
from app.ingestion.manifest import load_manifest

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize and ingest FINRA rule snapshots.")
    parser.add_argument("--manifest", type=Path, default=Path("data/source_manifest.yaml"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--source-id", action="append", required=True)
    parser.add_argument("--target-tokens", type=int, default=600)
    parser.add_argument("--overlap-tokens", type=int, default=50)
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Generate embeddings using the configured provider and API key.",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    sources = manifest.select(set(args.source_id))
    settings = ChunkSettings(args.target_tokens, args.overlap_tokens)
    embedding_provider = partial(embed_text, purpose="document") if args.embed else None
    embedding_model = embedding_model_name() if args.embed else None
    with SessionLocal.begin() as session:
        for source in sources:
            document, inserted = ingest_source_snapshot(
                session,
                source=source,
                raw_dir=args.raw_dir,
                chunk_settings=settings,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
            LOGGER.info("%s document=%s inserted=%s", source.source_id, document.id, inserted)
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(run(parse_args()))


if __name__ == "__main__":
    main()
