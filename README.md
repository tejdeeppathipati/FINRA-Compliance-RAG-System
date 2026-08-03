# FINRA Compliance RAG & Evaluation System

A narrow, source-grounded assistant for selected FINRA rules and guidance. The system
is designed to show its retrieved evidence, cite rules at subsection level, preserve
source snapshot metadata, and abstain when its indexed corpus cannot support an answer.

> Informational only. This project does not provide legal, compliance, or investment
> advice. Indexed pages are snapshots, not a guarantee of current FINRA requirements.

## Status

**Phase 0 baseline.** The repository currently provides the project contracts and a
small runnable FastAPI shell; ingestion, database queries, generation, and the React
interface are intentionally not represented as complete.

Implemented now:

- canonical manifest for 8 FINRA rules and 5 FINRA guidance pages;
- ignored local raw and normalized data directories;
- 40 labeled evaluation cases with the required category distribution;
- PostgreSQL/pgvector schema contract and local Docker service;
- typed query response contract, prompt v1, and deterministic RRF;
- health endpoint, explicit `501` query placeholder, unit tests, and CI;
- delivery plan, quality gates, risks, and architecture decisions.

## Scope

| Rule | Area |
|---|---|
| 2090 | Know Your Customer |
| 2111 | Suitability |
| 2210 | Communications with the Public |
| 3110 | Supervision |
| 3310 | Anti-Money Laundering |
| 4370 | Business Continuity |
| 4511 | Books and Records |
| 4512 | Customer Account Information |

The guidance corpus covers suitability, supervision, books and records, business
continuity, and the FIRST overview. The [source manifest](data/source_manifest.yaml)
is the corpus authority.

## Target architecture

```text
Official FINRA HTML / authorized API
              |
       snapshot + hash
              |
    rule/guidance parsers
              |
 normalized section tree
              |
 section-aware chunks (metadata retained)
              |
 embeddings + PostgreSQL FTS in pgvector
              |
 vector top-15 + keyword top-15
              |
 reciprocal rank fusion
              |
 evidence gate + top passages
              |
 structured grounded generation
              |
 citation validation or abstention
              |
 FastAPI response + React evidence view
```

## Local baseline

Requirements: Python 3.12+. PostgreSQL is not required for the current unit tests.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check app tests
uvicorn app.main:app --reload
```

Then open `http://localhost:8000/docs` or request:

```bash
curl http://localhost:8000/api/health
```

To start pgvector for upcoming ingestion work:

```bash
docker compose up -d postgres
```

Copy `.env.example` to `.env` only when database or OpenAI-backed work begins. Never
commit API keys.

## API contract

Planned endpoints:

| Method | Path | Baseline status |
|---|---|---|
| `GET` | `/api/health` | implemented |
| `POST` | `/api/query` | typed placeholder; returns `501` |
| `GET` | `/api/sources` | planned |
| `GET` | `/api/sources/{source_id}` | planned |
| `POST` | `/api/admin/sync` | planned; must be protected |
| `POST` | `/api/evaluations/run` | planned; must be protected |
| `GET` | `/api/evaluations/latest` | planned |

The query endpoint will return the answer, validated citations, abstention flag,
retrieved chunks, retrieval configuration, prompt version, and informational disclaimer.

## Evaluation baseline

The committed dataset contains:

| Category | Count |
|---|---:|
| Direct single-rule | 20 |
| Multi-rule or multi-section | 8 |
| Paraphrased | 6 |
| Must abstain | 6 |
| **Total** | **40** |

Retrieval experiments will compare vector, keyword, and hybrid modes across token
targets 350/600/900, overlap 0/50, and final top-k 3/5/8. Metrics are Recall@3,
Recall@5, MRR, correct-rule rate, and correct-subsection rate. Answer metrics are
citation correctness/completeness, groundedness, abstention accuracy, and unsupported
claim count.

There are deliberately no performance percentages in this README yet. They will be
added only from saved, reproducible evaluation reports.

## Key design rules

- Legal section boundaries take priority over fixed token windows.
- Every chunk carries rule/guidance identity, section path, URL, retrieval time, and hash.
- Guidance is visibly distinguished from binding rule text.
- Every user-visible citation must map to a retrieved chunk.
- Unsupported and out-of-scope questions fail closed with the canonical abstention text.
- Query logs capture trace configuration and evidence IDs, with a future PII policy.
- Snapshot age is visible; syncing never silently rewrites historical provenance.

See [the project plan](docs/PROJECT_PLAN.md) and the
[retrieval ADR](docs/adr/0001-section-aware-hybrid-retrieval.md).

## Immediate next milestone

Phase 1 begins with schema migrations, a validated manifest loader, a polite snapshot
fetcher, representative HTML fixtures, and section-tree parsing. Its exit criterion is
reproducible, idempotent ingestion of all 13 sources—not merely successful HTTP downloads.

