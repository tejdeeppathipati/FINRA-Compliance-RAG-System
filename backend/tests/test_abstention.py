"""Verify deterministic out-of-scope questions fail closed."""

import pytest

from app.generation.abstention import should_abstain_for_scope


@pytest.mark.parametrize(
    "question",
    [
        "What is the federal tax deduction for purchasing cryptocurrency?",
        "Which stock should a retired customer buy this month?",
        "Can this system determine whether my employer violated federal employment law?",
        "What will the S&P 500 close at next Friday?",
        "Draft a definitive legal opinion that our AML program complies with every federal law.",
        "What are the current SEC cybersecurity incident reporting deadlines?",
    ],
)
def test_known_out_of_scope_questions_fail_closed(question: str) -> None:
    assert should_abstain_for_scope(question) is True


def test_finra_question_is_not_rejected_by_scope_gate() -> None:
    assert should_abstain_for_scope("What must a firm's supervisory system include?") is False
