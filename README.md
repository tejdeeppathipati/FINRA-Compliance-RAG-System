# FINRA Compliance RAG

FINRA Compliance RAG is a source-grounded question-answering service for a deliberately
small corpus of FINRA rules and official guidance. It retrieves the relevant rule
sections, shows the evidence used, cites the source and subsection, and refuses to make
claims when the indexed corpus does not support an answer.

This is an engineering and evaluation project—not legal, compliance, or investment
advice. The application is informational and only covers the sources listed in
[`data/source_manifest.yaml`](data/source_manifest.yaml).

## What it does

- Ingests official FINRA HTML pages through a manifest-controlled allow-list.
- Preserves headings, subsection labels, source URLs, retrieval dates, effective-date
  evidence, and content hashes.
- Chunks documents by legal sections instead of blindly splitting every page at a
  fixed character count.
- Supports PostgreSQL full-text search, vector search with pgvector, and hybrid search
  using reciprocal-rank fusion.
- Returns rule- and subsection-level citations with expandable retrieved evidence.
- Abstains on unsupported or out-of-scope questions.
- Logs the question, answer, retrieval configuration, prompt version, and evidence IDs.
- Provides a small FastAPI backend and React interface suitable for a local demo.
- Evaluates retrieval quality with a labeled 40-question dataset.

## Corpus

The initial corpus contains eight rules:

| Rule | Topic |
| --- | --- |
| 2090 | Know Your Customer |
| 2111 | Suitability |
| 2210 | Communications with the Public |
| 3110 | Supervision |
| 3310 | Anti-Money Laundering |
| 4370 | Business Continuity |
| 4511 | Books and Records |
| 4512 | Customer Account Information |

It also includes official guidance for suitability, supervision, books and records,
business continuity, and FINRA's FIRST rulebook search tool. The manifest is the source
of truth; raw HTML snapshots and normalized files are intentionally ignored by Git.

## Architecture

```text
FINRA pages
   -> manifest-controlled fetcher
   -> rule/guidance parser
   -> section-aware chunks + provenance metadata
   -> PostgreSQL + pgvector + full-text search
   -> keyword/vector/hybrid retrieval
   -> evidence validation
   -> deterministic response or optional Gemini grounded answer
   -> citations, evidence, and trace log
```

## Technology

- Backend: Python, FastAPI, SQLAlchemy, Alembic, pytest, Ruff
- Database: PostgreSQL 16 with the pgvector extension
- Embeddings and optional generation: Gemini or OpenAI adapters
- Parsing: BeautifulSoup
- Frontend: React, TypeScript, Vite
- Local infrastructure: Docker Compose

## Run locally

Requirements: Python 3.12+, Docker Desktop, and Node.js 18+.

1. Install dependencies and configure local environment variables:

   ```bash
   cp .env.example .env
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -e '.[dev]'
   cd ..
   ```

   Set `GEMINI_API_KEY` in `.env` if you want Gemini embeddings or generation. The
   default configuration is safe without a generation key: it returns retrieved
   evidence rather than generating unsupported prose.

2. Start PostgreSQL and apply the schema:

   ```bash
   docker compose up -d postgres
   cd backend
   .venv/bin/alembic upgrade head
   cd ..
   ```

3. Fetch, normalize, and ingest sources. Set a real contact address before fetching:

   ```bash
   export FINRA_FETCH_CONTACT="you@example.com"
   backend/.venv/bin/python scripts/fetch_finra_sources.py
   backend/.venv/bin/python scripts/normalize_finra_sources.py
   backend/.venv/bin/python scripts/ingest_finra_sources.py
   ```

   Add `--embed` to the ingestion command after configuring an embedding provider key:

   ```bash
   backend/.venv/bin/python scripts/ingest_finra_sources.py --embed
   ```

4. Start the API:

   ```bash
   backend/.venv/bin/uvicorn app.main:app --app-dir backend --reload
   ```

   Interactive API documentation is available at <http://localhost:8000/docs>.

5. Start the frontend in a second terminal:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Query API

`POST /api/query` accepts a question and retrieval configuration:

```bash
curl -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What information must a member maintain about a customer account?", "retrieval_mode":"hybrid", "top_k":5}'
```

The response includes:

- a grounded answer or the exact insufficient-evidence response;
- citations with rule number, subsection, source URL, and supporting excerpt;
- the retrieved chunks and scores;
- the retrieval configuration and prompt version;
- an informational-use disclaimer.

Other available endpoints are `GET /api/health`, `GET /api/sources`, and
`GET /api/sources/{source_id}`. Administrative sync and evaluation endpoints are not
exposed yet.

## Gemini configuration

Gemini can be used for both retrieval embeddings and optional answer generation:

```env
GEMINI_API_KEY=your-key
EMBEDDING_PROVIDER=gemini
GENERATION_PROVIDER=gemini
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GENERATION_MODEL=gemini-2.5-flash
```

The answer generator receives only retrieved passages. Its citations must match a
retrieved rule/subsection/source URL, and each supporting excerpt must be present in the
retrieved text. Invalid or unsupported model output falls back to the deterministic
evidence response.

## Evaluation

The labeled dataset contains 20 direct questions, 8 multi-rule or multi-section
questions, 6 paraphrases, and 6 questions that should abstain.

Run the retrieval benchmark after embedding the corpus:

```bash
PYTHONPATH=backend backend/.venv/bin/python evaluations/run_retrieval_eval.py \
  --modes keyword vector hybrid --top-k 3 5 8
```

The runner writes row-level results and aggregate summaries to the ignored
`evaluations/reports/` directory. It measures Recall@k, subsection recall, mean
reciprocal rank, and abstention accuracy. Vector and true hybrid modes require a
configured embedding key; the keyword-only baseline can run without one.

## Responsible behavior

- The corpus scope is explicit and FINRA-only.
- Source snapshots retain retrieval dates and hashes so stale content is visible.
- Rule text and explanatory guidance remain distinguishable in metadata.
- Unsupported, out-of-scope, and personalized-advice questions are not answered.
- User-visible citations are validated against retrieved evidence.
- API keys, raw snapshots, normalized snapshots, and evaluation reports are excluded
  from version control.

## Repository layout

```text
backend/       FastAPI app, ingestion, retrieval, generation, database, tests
frontend/      React/TypeScript evidence viewer
data/          Source manifest; fetched data stays local and ignored
evaluations/   Labeled questions and retrieval evaluation runner
scripts/       Fetch, normalize, and ingest commands
```

## Development checks

```bash
backend/.venv/bin/ruff check backend/app backend/tests scripts evaluations
PYTHONPATH=backend backend/.venv/bin/pytest -q
cd frontend && npm run build
```
