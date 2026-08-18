"""Run the reproducible local retrieval baseline and write CSV results."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from uuid import uuid4

from app.db.session import SessionLocal
from app.generation.abstention import should_abstain_for_scope
from app.ingestion.embed import embed_text, has_embedding_credentials
from app.retrieval.search import hybrid_search, keyword_search, vector_search


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
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=["keyword", "vector", "hybrid"],
        default=["keyword", "vector", "hybrid"],
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    cases = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    run_id = str(uuid4())
    with SessionLocal() as session:
        for mode in args.modes:
            for top_k in args.top_k:
                for case in cases:
                    if should_abstain_for_scope(case["question"]):
                        passages = []
                    elif mode == "keyword":
                        passages = keyword_search(session, case["question"], limit=top_k)
                    else:
                        if not has_embedding_credentials():
                            if mode == "vector":
                                raise RuntimeError(
                                    "Vector evaluation requires the configured embedding provider key"
                                )
                            query_embedding = None
                        else:
                            query_embedding = embed_text(case["question"], purpose="query")
                        if mode == "vector":
                            passages = vector_search(session, query_embedding, limit=top_k)
                        else:
                            passages = hybrid_search(
                                session,
                                case["question"],
                                limit=top_k,
                                vector_embedding=query_embedding,
                            )
                    retrieved = [passage.rule_number for passage in passages if passage.rule_number]
                    retrieved_subsections = [
                        passage.subsection for passage in passages if passage.subsection
                    ]
                    expected = case["expected_rule_numbers"]
                    expected_subsections = case.get("expected_subsections", [])
                    expected_answerable = bool(case["expected_answerable"])
                    rule_overlap = set(expected) & set(retrieved)
                    subsection_overlap = set(expected_subsections) & set(retrieved_subsections)
                    rows.append(
                        {
                            "run_id": run_id,
                            "case_id": case["id"],
                            "mode": mode,
                            "top_k": top_k,
                            "retrieved_rule_numbers": ";".join(retrieved),
                            "retrieved_subsections": ";".join(retrieved_subsections),
                            "expected_rule_numbers": ";".join(expected),
                            "expected_subsections": ";".join(expected_subsections),
                            "rule_recall": (
                                len(rule_overlap) / len(expected) if expected_answerable and expected else None
                            ),
                            "subsection_recall": (
                                len(subsection_overlap) / len(expected_subsections)
                                if expected_answerable and expected_subsections
                                else None
                            ),
                            "reciprocal_rank": (
                                _reciprocal_rank(retrieved, expected) if expected_answerable else None
                            ),
                            "passed_abstention": (not passages) is (not expected_answerable),
                        }
                    )
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} results to {args.output}")
    summary = _summarize(rows)
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote summary to {summary_path}")
    return 0


def _summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    summary: dict[str, object] = {}
    groups = sorted({(str(row["mode"]), int(row["top_k"])) for row in rows})
    for mode, top_k in groups:
        group = [row for row in rows if row["mode"] == mode and row["top_k"] == top_k]
        answerable = [row for row in group if row["rule_recall"] is not None]
        subsection_cases = [row for row in group if row["subsection_recall"] is not None]
        key = f"{mode}-top-{top_k}"
        summary[key] = {
            "answerable_cases": len(answerable),
            "recall_at_k": sum(float(row["rule_recall"]) for row in answerable) / len(answerable)
            if answerable
            else 0.0,
            "subsection_recall": (
                sum(float(row["subsection_recall"]) for row in subsection_cases)
                / len(subsection_cases)
                if subsection_cases
                else None
            ),
            "mrr": sum(float(row["reciprocal_rank"]) for row in answerable) / len(answerable)
            if answerable
            else 0.0,
            "abstention_accuracy": sum(
                bool(row["passed_abstention"]) for row in group
            )
            / len(group),
        }
    return summary


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
