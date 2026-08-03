# Project plan

## Product boundary

The system answers only from the 8 selected FINRA rules and 5 official FINRA guidance
pages in `data/source_manifest.yaml`. It is an evidence-navigation tool, not a legal
opinion engine, investment adviser, whole-rulebook search product, or current-law
guarantee.

## Baseline quality gates

No phase is complete until its automated tests pass and its artifacts are reproducible.

| Gate | Required evidence |
|---|---|
| Source integrity | URL, retrieval timestamp, effective date when present, SHA-256 hash, parser version |
| Structural integrity | Fixture tests preserve rule, subsection, heading, ordered text, supplementary material |
| Chunk integrity | No empty chunks; stable IDs; parent section path retained; token bounds reported |
| Retrieval integrity | Deterministic RRF; no duplicate chunks; configuration captured |
| Citation integrity | Every citation maps to a retrieved chunk and its source metadata |
| Responsible behavior | All unsupported baseline cases abstain; disclaimer and snapshot date shown |
| Evaluation integrity | Raw per-case results stored; aggregate metrics derived; no invented percentages |
| Operational integrity | Health/readiness split, migrations reproducible, secrets excluded from logs |

## Delivery phases

### Phase 0 — Baseline (current)

- Confirm a from-scratch repository and explicit FINRA-only boundary.
- Commit source manifest, corpus policy, schema contract, API contract, prompt v1,
  deterministic RRF, and 40 labeled evaluation cases.
- Establish FastAPI health test, lint/test CI, pgvector development service, and ADRs.

Exit: clean install runs unit tests; dataset distribution and manifest validate.

### Phase 1 — Evidence pipeline

- Fetch politely with timeouts, retries, user agent, conditional requests, and per-source errors.
- Save immutable local HTML snapshots under ignored `data/raw/`.
- Normalize into versioned JSON with ordered section nodes.
- Implement FINRA rule parser plus separate guidance parser.
- Build section-aware splitter with token targets and overlap as configuration.
- Add migrations, idempotent upserts, and embedding batching.

Exit: all 13 sources ingest reproducibly; reruns do not duplicate documents or chunks;
parser fixtures cover every page layout represented in the corpus.

### Phase 2 — Retrieval baseline and experiments

- Implement vector, keyword, and hybrid retrieval behind one interface.
- Add rule-number and quoted-term query handling without bypassing ranking.
- Run the full retrieval grid and write per-run CSV plus machine-readable metadata.
- Report Recall@3, Recall@5, MRR, correct-rule, and correct-subsection rates.

Exit: results are reproducible from a run ID; README names the measured default and
shows tradeoffs, including failures.

### Phase 3 — Grounded generation and responsible behavior

- Add structured OpenAI output, passage identifiers, citation construction, and validator.
- Add evidence sufficiency policy and calibrated abstention.
- Log prompt version, retrieval configuration, chunk IDs, latency, answer, and abstention.
- Add deterministic claim/citation checks and a documented human-review rubric.

Exit: all citations are evidence-backed; the six unsupported baseline cases abstain;
answer evaluation reports groundedness, completeness, correctness, and unsupported claims.

### Phase 4 — Demo and delivery

- Implement the small React query and evaluation pages.
- Show rule/guidance distinction, source links, subsections, excerpts, retrieval dates,
  and retrieval configuration.
- Add Docker images, end-to-end tests, architecture diagram, setup guide, and demo script.

Exit: a new reviewer can run, ingest, query, inspect evidence, and reproduce an
evaluation from documented commands.

## Work packages and recommended order

1. Data contracts and migrations.
2. Fetch snapshots and build representative parser fixtures.
3. Normalize section trees and validate metadata.
4. Chunk and embed idempotently.
5. Implement retrieval modes and evaluation runner.
6. Choose the measured retrieval default.
7. Add generation, citation validation, and abstention.
8. Add query trace logs and API endpoints.
9. Build the two-page frontend.
10. Containerize, document, and record the demo.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| FINRA HTML layout changes | Source-specific selectors, fixture snapshots, loud parser failures |
| Rules become stale | Display retrieval/effective dates; hash snapshots; admin sync; never label snapshot “current” |
| API/scraping terms constrain ingestion | Prefer authorized FINRA API where available; document access path and review terms |
| Exact phrases miss vector search | PostgreSQL FTS plus hybrid fusion |
| Semantic matches look relevant but do not support claims | Evidence threshold, citation validation, abstention |
| Evaluation leakage | Separate development/tuning cases from a later held-out set |
| Model or embedding drift | Pin model IDs in run metadata; do not compare runs without configuration |
| Sensitive query logs | Minimize fields, redact obvious PII, define retention, restrict admin access |

## First implementation sprint

1. Alembic migration and SQLAlchemy models matching `schema.sql`.
2. Manifest loader with schema validation and URL allow-listing to `finra.org`.
3. Fetcher with snapshot metadata and content hashing.
4. Parser fixtures for Rules 2090, 2210, 3110, and one guidance page.
5. Recursive section tree normalizer and tokenizer-backed chunker.
6. Ingestion command with dry-run and idempotency tests.

