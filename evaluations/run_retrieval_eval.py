"""Run the reproducible local retrieval baseline and write CSV results."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from uuid import uuid4

from app.db.session import SessionLocal
from app.generation.abstention import should_abstain_for_scope
from app.retrieval.search import hybrid_search, keyword_search


def _reciprocal_rank(retrieved: list[str], expected: list[str]) -> float:
    expected_set = set(expected)
    for index, rule_number in enumerate(retrieved, start=1):
        if rule_number in expected_set:
            return 1.0 / index
    return 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic FINRA retrieval evaluation.")
    parser.add_argument("--dataset", type=Path, default=Path("evaluations/dataset.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("evaluations/reports/retrieval_results.csv"))
    parser.add_argument("--top-k", type=int, nargs="+", default=[3, 5, 8])
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    cases = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    with SessionLocal() as session:
        for mode in ("keyword", "hybrid"):
            for top_k in args.top_k:
                for case in cases:
                    if should_abstain_for_scope(case["question"]):
                        passages = []
                    elif mode == "keyword":
                        passages = keyword_search(session, case["question"], limit=top_k)
                    else:
                        passages = hybrid_search(session, case["question"], limit=top_k)
                    retrieved = [passage.rule_number for passage in passages if passage.rule_number]
                    expected = case["expected_rule_numbers"]
                    rows.append(
                        {
                            "run_id": str(uuid4()),
                            "case_id": case["id"],
                            "mode": mode,
                            "top_k": top_k,
                            "retrieved_rule_numbers": ";".join(retrieved),
                            "expected_rule_numbers": ";".join(expected),
                            "rule_recall": bool(set(expected) & set(retrieved)) if expected else not retrieved,
                            "reciprocal_rank": _reciprocal_rank(retrieved, expected),
                            "passed_abstention": (not passages) is (not case["expected_answerable"]),
                        }
                    )
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
