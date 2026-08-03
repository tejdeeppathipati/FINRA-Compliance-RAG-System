# ADR 0001: Section-aware chunks with hybrid retrieval

- Status: accepted
- Date: 2026-07-30

## Context

FINRA rules contain nested legal sections, exact regulatory phrases, and supplementary
material. Fixed-size chunks can detach a requirement from its subsection, while
vector-only retrieval can miss exact terms and rule numbers.

## Decision

Preserve rule and guidance headings as structural boundaries. Split only sections
larger than the active token target, retaining the full section path on every child
chunk. The initial production candidate is 600 tokens with 50-token overlap.

Retrieve the top 15 vector and top 15 PostgreSQL full-text matches, deduplicate by
chunk ID, fuse with Reciprocal Rank Fusion using `k=60`, and return the top 5 passages.

This is a hypothesis, not a claimed optimum. Evaluation must compare:

- token targets: 350, 600, 900;
- overlap: 0, 50;
- retrieval modes: vector, keyword, hybrid;
- final `top_k`: 3, 5, 8.

## Consequences

Every chunk needs a stable section path, subsection, source URL, retrieval timestamp,
and content hash. Configuration must be stored with every evaluation result and query
log. A winner is selected from measured retrieval and answer behavior, not intuition.

