from __future__ import annotations

import re

OUT_OF_SCOPE_PATTERNS = (
    r"\b(?:tax deduction|cryptocurrency|crypto)\b",
    r"\bwhich stock\b|\bwhat stock\b|\bshould .*\b(?:buy|sell)\b",
    r"\b(?:employer|employment) law\b|\bviolated federal employment\b",
    r"\b(?:s&p|sp500|market)\b.*\b(?:close|price|next|predict)\b",
    r"\b(?:legal opinion|legal advice|complies with every)\b",
    r"\b(?:current|latest)\b.*\b(?:sec|cybersecurity|deadline)\b",
)


def should_abstain_for_scope(question: str) -> bool:
    return any(
        re.search(pattern, question, flags=re.IGNORECASE)
        for pattern in OUT_OF_SCOPE_PATTERNS
    )
