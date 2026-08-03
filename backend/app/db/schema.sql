CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE source_type AS ENUM ('rule', 'guidance');

CREATE TABLE documents (
    id uuid PRIMARY KEY,
    source_id text NOT NULL UNIQUE,
    rule_number text,
    title text NOT NULL,
    source_type source_type NOT NULL,
    source_url text NOT NULL,
    effective_date date,
    retrieved_at timestamptz NOT NULL,
    content_hash text NOT NULL,
    normalized_content jsonb NOT NULL,
    CONSTRAINT documents_content_hash_sha256 CHECK (content_hash ~ '^[a-f0-9]{64}$')
);

CREATE TABLE chunks (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section_path text NOT NULL,
    subsection text,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    content text NOT NULL,
    content_hash text NOT NULL,
    token_count integer NOT NULL CHECK (token_count > 0),
    embedding vector(1536),
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(section_path, '') || ' ' || content)
    ) STORED,
    UNIQUE (document_id, section_path, chunk_index),
    CONSTRAINT chunks_content_hash_sha256 CHECK (content_hash ~ '^[a-f0-9]{64}$')
);

CREATE INDEX chunks_search_vector_idx ON chunks USING gin (search_vector);
CREATE INDEX chunks_embedding_hnsw_idx ON chunks
USING hnsw (embedding vector_cosine_ops)
WHERE embedding IS NOT NULL;

CREATE TABLE query_logs (
    id uuid PRIMARY KEY,
    question text NOT NULL,
    answer text NOT NULL,
    abstained boolean NOT NULL,
    retrieved_chunk_ids uuid[] NOT NULL,
    retrieval_configuration jsonb NOT NULL,
    prompt_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    latency_ms integer NOT NULL CHECK (latency_ms >= 0)
);

CREATE TABLE evaluation_cases (
    id text PRIMARY KEY,
    question text NOT NULL,
    expected_rule_numbers text[] NOT NULL,
    expected_subsections text[] NOT NULL,
    expected_answerable boolean NOT NULL,
    reference_notes text NOT NULL,
    category text NOT NULL
);

CREATE TABLE evaluation_results (
    id uuid PRIMARY KEY,
    evaluation_case_id text NOT NULL REFERENCES evaluation_cases(id),
    run_id uuid NOT NULL,
    configuration jsonb NOT NULL,
    retrieved_rule_numbers text[] NOT NULL,
    retrieved_subsections text[] NOT NULL,
    reciprocal_rank double precision NOT NULL CHECK (
        reciprocal_rank >= 0 AND reciprocal_rank <= 1
    ),
    answer text,
    citations jsonb NOT NULL DEFAULT '[]'::jsonb,
    passed_grounding boolean,
    passed_abstention boolean,
    unsupported_claim_count integer CHECK (unsupported_claim_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX evaluation_results_run_id_idx ON evaluation_results(run_id);

