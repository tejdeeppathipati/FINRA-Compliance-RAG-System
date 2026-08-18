# FINRA Compliance RAG & Evaluation System

A narrow, source-grounded assistant for selected FINRA rules and guidance. The system
is designed to show its retrieved evidence, cite rules at subsection level, preserve
source snapshot metadata, and abstain when its indexed corpus cannot support an answer.

> Informational only. This project does not provide legal, compliance, or investment
> advice. Indexed pages are snapshots, not a guarantee of current FINRA requirements.

## Status

**MVP backend vertical slice.** The repository now has a working, testable foundation
for the FINRA-only assistant. The eight rule snapshots in the local starter data have
been parsed into section-aware normalized JSON with exact substantive-coverage audits.
Raw HTML and normalized snapshots remain local and ignored by Git.

Implemented now:

- manifest-driven FINRA source allow-list for 8 rules and 5 guidance pages;
- polite snapshot fetching with retrieval timestamps, effective-date evidence, and
  SHA-256 provenance hashes;
- rule-body and guidance-page parsing that preserves headings, numbered subsections,
  supplementary material, source locators, and parser/audit metadata;
- section-aware 600-token chunks with 50-token overlap only inside oversized sections;
- PostgreSQL/pgvector models and Alembic migrations for documents, chunks, query logs,
  and evaluation records;
- PostgreSQL full-text keyword retrieval, cosine vector retrieval, and RRF hybrid
  retrieval services;
- deterministic evidence-only answer formatting with rule/subsection citations and
  fail-closed abstention;
- configurable OpenAI or Gemini embeddings, with Gemini set up for this project;
- optional Gemini grounded answer generation with exact evidence/citation validation;
- retrieval evaluation across keyword-only, vector-only, and hybrid modes, including
  Recall@3/5, MRR, rule retrieval, subsection retrieval, and abstention accuracy;
- `/api/health`, `/api/sources`, `/api/sources/{source_id}`, and `/api/query`;
- 41 automated tests plus Ruff linting, and a production-buildable React evidence viewer.

The answer layer is intentionally conservative until a generation model is configured:
it returns retrieved evidence rather than inventing a prose answer. This makes the
retrieval and citation behavior inspectable first.

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

Apply the versioned database schema from the `backend` directory:

```bash
cd backend
alembic upgrade head
alembic current
alembic check
```

Alembic migrations are the schema authority. The application uses `DATABASE_URL` at
runtime and `DATABASE_DIRECT_URL` for migrations. They are identical locally; hosted
deployments should use a pooled runtime URL and a direct migration URL.

Copy `.env.example` to `.env`, then set your provider key locally. For Gemini:

```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY=...; keep EMBEDDING_PROVIDER=gemini
```

Never commit API keys. The application uses Gemini's `gemini-embedding-001` with a
1536-dimensional output, matching the current pgvector schema.

## Source snapshots

The manifest permits only HTTPS pages on the explicitly allow-listed FINRA host. The
fetcher requires a truthful contact address in its user agent, follows and validates
redirects, retries transient failures, fetches sequentially, and writes HTML plus
provenance metadata under ignored `data/raw/` directories.

Install the backend package, set a contact address, and fetch one source first:

```bash
source backend/.venv/bin/activate
pip install -e 'backend[dev]'
export FINRA_FETCH_CONTACT="your-email@example.com"
python scripts/fetch_finra_sources.py --source-id finra-rule-2090
```

Fetch all 13 sources only after the single-source check succeeds:

```bash
python scripts/fetch_finra_sources.py
```

Raw-response SHA-256 hashes establish snapshot provenance. A later normalization stage
will compute a second content hash after removing volatile page markup; raw hashes alone
must not be interpreted as evidence that FINRA's legal content changed.

Normalize a saved rule snapshot into the ignored `data/normalized/` directory:

```bash
python scripts/normalize_finra_sources.py --source-id finra-rule-2090
```

Normalize all eight rule snapshots:

```bash
for id in finra-rule-2090 finra-rule-2111 finra-rule-2210 finra-rule-3110 \
  finra-rule-3310 finra-rule-4370 finra-rule-4511 finra-rule-4512; do
  python scripts/normalize_finra_sources.py --source-id "$id"
done
```

The rule parser selects only FINRA's rule-body block, preserves main versus supplementary
material, records amendment history and explicit effective-date evidence, and computes a
stable normalized-content hash. The guidance parser preserves page headings and list
content while recording the same provenance metadata. Each section records exact
source-element locators and source-text hashes, while an embedded audit reports
substantive coverage and intentional exclusions. Synthetic display labels are explicitly
distinguished from official FINRA headings.

Normalize guidance snapshots with the same manifest-driven command:

```bash
for id in finra-guidance-2111-faq finra-guidance-supervision \
  finra-guidance-books-records finra-guidance-bcp finra-guidance-first-overview; do
  python scripts/normalize_finra_sources.py --source-id "$id"
done
```

After PostgreSQL is running and migrations are applied, ingest normalized rule snapshots
and chunks (without embeddings):

```bash
python scripts/ingest_finra_sources.py --source-id finra-rule-2090
```

Add `--embed` after setting the configured provider key; with Gemini this calls
`gemini-embedding-001` and stores vectors alongside the chunks. It also backfills
embeddings for an already-ingested document whose chunks do not yet have vectors:

```bash
python scripts/ingest_finra_sources.py --source-id finra-rule-2090 --embed
```

The ingestion command supports both `rule` and `guidance` manifest entries. Guidance
chunks are labeled `source_type=guidance` so the answer layer can distinguish
explanatory material from binding rule text.

## API contract

Planned endpoints:

| Method | Path | Baseline status |
|---|---|---|
| `GET` | `/api/health` | implemented |
| `POST` | `/api/query` | keyword/hybrid retrieval, citations, evidence, abstention; vector mode requires embeddings |
| `GET` | `/api/sources` | implemented; manifest plus local snapshot state |
| `GET` | `/api/sources/{source_id}` | implemented |
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

Run the local retrieval evaluation after the corpus is ingested:

```bash
PYTHONPATH=backend python evaluations/run_retrieval_eval.py \
  --modes keyword vector hybrid --top-k 3 5 8
```

Vector and true hybrid modes require the configured embedding provider key. The runner
writes a row-level CSV and a summary JSON under ignored `evaluations/reports/`; it does
not claim a vector result when the key is unavailable.

There are deliberately no final performance percentages in this README yet. They will
be added only from saved, reproducible evaluation reports.

To enable Gemini grounded prose after retrieval quality is measured, set
`GENERATION_PROVIDER=gemini` and `GEMINI_API_KEY` in `.env`. The generator must return
structured JSON, and every citation/excerpt is checked against the retrieved passages;
invalid or unsupported output falls back to the deterministic evidence response.

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

## Remaining work after the MVP

The next implementation increments are deliberately separate from the ingestion core:

1. Run the true vector/hybrid benchmark after configuring the Gemini embedding key and
   commit the resulting report summary.
2. Add protected admin/evaluation endpoints and hosted database/provider-secret setup.
3. Expand answer-level evaluation (citation completeness, groundedness, and unsupported
   claim counts) over the measured retrieval configurations.

These are visible follow-on tasks; none should be represented as completed until their
commands and tests have actually run.

The current local retrieval baseline can be reproduced after database ingestion:

```bash
PYTHONPATH=backend python evaluations/run_retrieval_eval.py
```

This writes an ignored CSV under `evaluations/reports/`. The runner currently compares
keyword retrieval with the keyword-only hybrid fallback; vector rows become meaningful
after `--embed` ingestion and a Gemini key are configured.
