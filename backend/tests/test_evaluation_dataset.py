"""Verify the labeled evaluation set has the intended shape and categories."""

import json
from collections import Counter
from pathlib import Path


def test_evaluation_dataset_shape() -> None:
    dataset_path = Path(__file__).parents[2] / "evaluations" / "dataset.jsonl"
    cases = [json.loads(line) for line in dataset_path.read_text().splitlines() if line.strip()]

    assert len(cases) == 40
    assert len({case["id"] for case in cases}) == 40
    assert Counter(case["category"] for case in cases) == {
        "direct_single_rule": 20,
        "multi_rule_or_section": 8,
        "paraphrased": 6,
        "unsupported": 6,
    }
    assert all(case["expected_rule_numbers"] for case in cases if case["expected_answerable"])
    assert all(
        not case["expected_rule_numbers"] for case in cases if not case["expected_answerable"]
    )
