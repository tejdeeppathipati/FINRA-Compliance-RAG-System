# ADR 0002: Evidence-gated answers and fail-closed abstention

- Status: accepted
- Date: 2026-07-30

## Context

Compliance answers can cause harm when they blend general knowledge with retrieved
rules, omit qualifications, or imply legal advice. Retrieval scores alone do not
prove that the available passages support an answer.

## Decision

Generation receives only selected passages and structured metadata. The response
must cite retrieved chunk IDs internally and expose rule/guidance citations to users.
A post-generation validator rejects citations that do not map to retrieved chunks.

The system abstains with the canonical text
`Insufficient evidence in the indexed FINRA sources.` when:

1. no passage passes the calibrated evidence threshold;
2. the requested conclusion is outside the indexed FINRA corpus;
3. citations cannot be validated against retrieved evidence; or
4. the model marks the evidence insufficient.

The UI always displays an informational-only disclaimer and snapshot retrieval dates.

## Consequences

False abstentions are preferable to unsupported compliance claims for this portfolio
scope. Thresholds must be calibrated on the labeled dataset, including adversarial
and out-of-scope cases, and never chosen from the test set alone.

