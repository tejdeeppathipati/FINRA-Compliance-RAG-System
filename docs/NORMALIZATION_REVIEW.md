# Normalization review

This document records source-to-normalized comparisons for each supported FINRA page
layout. Automated coverage is necessary but does not replace initial human approval.

## Rule 2090 — Know Your Customer

- Source ID: `finra-rule-2090`
- Snapshot retrieval: `2026-08-03T15:00:53.072800+00:00`
- Raw SHA-256: `90b788810ff6b5febfd75f9dbd1afda688284bd45ccc1d6c052fd8ab3609eacc`
- Parser: `finra-rule-parser-v2`
- Normalized SHA-256: `7569270e4ae0dee179ba11d2ad3ddc10292ba595c21f1f242a9df94814fd1cf2`
- Automated review: passed
- Human approval: pending

### Coverage

| Measurement | Result |
|---|---:|
| Substantive source characters | 746 |
| Covered substantive characters | 746 |
| Coverage ratio | 1.0000 |
| Exact normalized comparison | passed |
| Parsed sections | 2 |
| Unaccounted substantive elements | 0 |

The parser intentionally excludes one decorative supplementary-material marker. Its
meaning is retained by the official `.01 Essential Facts` section path and
`supplementary` section type.

### Structural review

| Source content | Normalized representation | Assessment |
|---|---|---|
| Unlabeled operative paragraph | `2090`, synthetic display label `Main rule text` | correct |
| `.01 Essential Facts` | official heading under `Supplementary Material` | correct |
| Amendment/adoption footnote | non-retrieval history metadata | correct |
| `eff. July 9, 2012` | explicit evidence plus `latest_effective_date=2012-07-09` | correct |
| Selected Notices | structured IDs `11-02`, `11-25`, `12-25` | correct |

Navigation, rule traversal links, login content, help contacts, related content, and
the site footer are outside the selected rule-body element and are not normalized.

### Approval checklist

- [x] Automated exact-text comparison
- [x] Source locator and source-text hash validation
- [x] Effective-date evidence validation
- [x] Intentional-exclusion review
- [ ] Human source-versus-JSON approval

Rule 2090 should not be marked corpus-approved until a human checks the saved HTML and
normalized JSON and completes the final checkbox.

