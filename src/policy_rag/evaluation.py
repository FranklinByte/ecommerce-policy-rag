from __future__ import annotations

import csv
import json
import math
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
import psutil
import yaml

from policy_rag.config import Settings
from policy_rag.corpus import CorpusRepository, file_sha256
from policy_rag.generation import ExtractiveAnswerGenerator, build_generator
from policy_rag.logging import get_logger
from policy_rag.models import CustomerContext, EvalCase, QueryRequest, RetrievalMode
from policy_rag.paths import project_path
from policy_rag.retrieval.embedding import SentenceTransformerEmbedder
from policy_rag.retrieval.reranker import CrossEncoderReranker
from policy_rag.retrieval.service import RetrievalService
from policy_rag.service import PolicyRAGService

logger = get_logger()


def ranking_metrics(retrieved: list[str], grades: dict[str, int]) -> dict[str, float]:
    ranked = list(dict.fromkeys(retrieved))
    relevant = {doc_id for doc_id, grade in grades.items() if grade > 0}
    if not relevant:
        raise ValueError("Retrieval metrics require a nonempty relevance set")
    metrics = {f"recall@{k}": len(set(ranked[:k]) & relevant) / len(relevant) for k in (1, 3, 5)}
    metrics["mrr@5"] = next(
        (1 / rank for rank, doc_id in enumerate(ranked[:5], 1) if doc_id in relevant), 0.0
    )
    dcg = sum(
        (2 ** grades.get(doc_id, 0) - 1) / math.log2(i + 2) for i, doc_id in enumerate(ranked[:5])
    )
    ideal = sum(
        (2**grade - 1) / math.log2(i + 2)
        for i, grade in enumerate(sorted(grades.values(), reverse=True)[:5])
    )
    metrics["ndcg@5"] = dcg / ideal if ideal else 0.0
    return metrics


def citation_metrics(cited: list[str], relevant: list[str]) -> dict[str, float | None]:
    cited_set, gold = set(cited), set(relevant)
    return {
        "citation_precision": len(cited_set & gold) / len(cited_set) if cited_set else None,
        "citation_recall": len(cited_set & gold) / len(gold) if gold else None,
    }


def load_cases(path: Path, valid_docs: set[str] | None = None) -> list[EvalCase]:
    cases = [
        EvalCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate evaluation case IDs")
    for case in cases:
        if case.answerable != bool(case.relevant_doc_ids):
            raise ValueError(f"Inconsistent answerability/qrels: {case.id}")
        if set(case.relevance_grades) != set(case.relevant_doc_ids):
            raise ValueError(f"Inconsistent relevance grades: {case.id}")
        if valid_docs is not None and not set(case.relevant_doc_ids) <= valid_docs:
            raise ValueError(f"Unknown relevance document: {case.id}")
    return cases


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, dict | list)
                    else value
                    for key, value in row.items()
                }
            )


def _average(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return mean(values) if values else None


def summarize(retrieval: list[dict[str, Any]], generation: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [row for row in retrieval if not row["degraded"]]
    answerable = [row for row in complete if row["answerable"]]
    generated = [row for row in generation if not row["degraded"]]
    negative = [row for row in generated if not row["answerable"]]
    positive = [row for row in generated if row["answerable"]]
    latencies = [row["latency_ms"] for row in complete]
    return {
        "status": "completed" if len(complete) == len(retrieval) else "incomplete_degraded",
        "queries": len(retrieval),
        "degraded_queries": len(retrieval) - len(complete),
        "retrieval": {
            key: _average(answerable, key)
            for key in ["recall@1", "recall@3", "recall@5", "mrr@5", "ndcg@5"]
        },
        "retrieval_p50_ms": float(np.percentile(latencies, 50)) if latencies else None,
        "retrieval_p95_ms": float(np.percentile(latencies, 95)) if latencies else None,
        "generation": {
            "citation_precision_when_cited": _average(positive, "citation_precision"),
            "citation_recall_all_answerable": _average(positive, "citation_recall"),
            "citation_coverage_answerable": mean(bool(row["cited_docs"]) for row in positive)
            if positive
            else None,
            "no_answer_refusal_accuracy": _average(negative, "correct_refusal"),
            "answerable_acceptance_rate": mean(not row["refused"] for row in positive)
            if positive
            else None,
            "answerability_accuracy": _average(generated, "correct_refusal"),
            "generation_p50_ms": float(np.percentile([row["latency_ms"] for row in generated], 50))
            if generated
            else None,
            "generation_p95_ms": float(np.percentile([row["latency_ms"] for row in generated], 95))
            if generated
            else None,
        },
        "by_category": {
            category: {
                "queries": len([row for row in complete if row["category"] == category]),
                "recall@5": _average(
                    [row for row in answerable if row["category"] == category], "recall@5"
                ),
                "mrr@5": _average(
                    [row for row in answerable if row["category"] == category], "mrr@5"
                ),
            }
            for category in sorted({row["category"] for row in retrieval})
        },
    }


def run_evaluation(
    settings: Settings, config_path: Path, output: Path, *, provider: bool = False
) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            "Output directory is not empty; use a new run directory to preserve raw results"
        )
    output.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config["repetitions"] != 1:
        raise ValueError("This fixed-regression protocol requires repetitions=1; use separate runs")
    updates = {key: config[key] for key in ("candidate_k", "chunk_size", "chunk_overlap", "rrf_k")}
    updates.update(
        {
            "sparse_threshold": config["thresholds"]["sparse"],
            "dense_threshold": config["thresholds"]["dense"],
            "evidence_threshold": config["thresholds"]["cross_encoder"],
        }
    )
    settings = Settings.model_validate(settings.model_dump() | updates)
    docs = {
        entry.metadata.doc_id
        for entry in CorpusRepository(settings.source_manifest).read_manifest().sources
    }
    cases_path = project_path(config["dataset"])
    cases = load_cases(cases_path, docs)
    embedder = SentenceTransformerEmbedder(
        settings.embedding_model,
        settings.embedding_device,
        settings.embedding_batch_size,
        settings.model_cache_dir,
        settings.embedding_revision,
        settings.torch_threads,
    )
    reranker = CrossEncoderReranker(
        settings.reranker_model,
        settings.reranker_device,
        settings.reranker_batch_size,
        settings.model_cache_dir,
        settings.reranker_revision,
        settings.torch_threads,
    )
    generator = build_generator(settings) if provider else ExtractiveAnswerGenerator()
    manifest: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": file_sha256(cases_path),
        "config_sha256": file_sha256(config_path),
        "config": config,
        "source_hashes": {
            str(path.relative_to(project_path("."))).replace("\\", "/"): file_sha256(path)
            for path in sorted(project_path("src/policy_rag").rglob("*.py"))
        },
        "dependency_lock_sha256": file_sha256(project_path("uv.lock")),
        "embedding_revision": settings.embedding_revision,
        "reranker_revision": settings.reranker_revision,
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu_count": psutil.cpu_count(),
        "torch_threads": settings.torch_threads,
        "annotation": (
            "AI-assisted fixed regression; NOT independently human-reviewed; "
            "NOT model generalization evidence"
        ),
        "generation_backend": generator.name,
        "llm_generation_evaluation": "requested"
        if provider
        else "not_executed_no_provider_requested",
        "llm_factual_correctness": "not_evaluated; citation relevance is not semantic entailment",
        "experiments": {},
    }
    for strategy in config["strategies"]:
        retrieval_service = RetrievalService(
            settings,
            embedder=embedder,
            reranker=reranker,
            index_dir=settings.strategy_index_dir(strategy),
        )
        service = PolicyRAGService(settings, retrieval_service, generator)
        try:
            for mode_value in config["modes"]:
                mode = RetrievalMode(mode_value)
                name = f"{strategy}-{mode.value}"
                rows: list[dict[str, Any]] = []
                gen_rows: list[dict[str, Any]] = []
                started = time.perf_counter()
                service.query(
                    QueryRequest(question=config["warmup_query"], mode=mode, generate=False)
                )
                warmup_ms = (time.perf_counter() - started) * 1000
                for case in cases:
                    context = CustomerContext(
                        platform=case.filters.platform,
                        product_category=case.filters.product_category,
                        as_of_date=case.filters.as_of_date,
                    )
                    response = service.query(
                        QueryRequest(
                            question=case.query,
                            filters=case.filters,
                            context=context,
                            mode=mode,
                            top_k=config["top_k"],
                        )
                    )
                    retrieved = [item.doc_id for item in response.candidates]
                    row: dict[str, Any] = {
                        "id": case.id,
                        "category": case.category,
                        "answerable": case.answerable,
                        "query": case.query,
                        "filters": case.filters.model_dump(mode="json"),
                        "relevant_docs": case.relevant_doc_ids,
                        "retrieved_docs": retrieved,
                        "degraded": response.degraded,
                        "effective_mode": response.effective_mode.value,
                        "degradation_reasons": response.degradation_reasons,
                        "latency_ms": response.retrieval_ms,
                        "chunks": [item.model_dump(mode="json") for item in response.candidates],
                    }
                    if case.answerable:
                        row.update(ranking_metrics(retrieved, case.relevance_grades))
                    rows.append(row)
                    answer = response.answer
                    assert answer is not None
                    cited = [citation.doc_id for citation in answer.citations]
                    gen_rows.append(
                        {
                            "id": case.id,
                            "category": case.category,
                            "answerable": case.answerable,
                            "degraded": response.degraded,
                            "generator": answer.generator,
                            "refused": answer.refused,
                            "correct_refusal": float(answer.refused != case.answerable),
                            "cited_docs": cited,
                            "latency_ms": response.generation_ms,
                            **citation_metrics(cited, case.relevant_doc_ids),
                            "answer": answer.model_dump(mode="json"),
                        }
                    )
                    if len(rows) % 12 == 0:
                        logger.info(
                            "evaluation_progress",
                            experiment=name,
                            completed=len(rows),
                            total=len(cases),
                        )
                summary = summarize(rows, gen_rows)
                summary["warmup_ms"] = warmup_ms
                summary["index"] = retrieval_service.manifest.model_dump(mode="json")
                summary["rss_mb_after"] = psutil.Process().memory_info().rss / 1024**2
                manifest["experiments"][name] = summary
                run_dir = output / name
                run_dir.mkdir()
                write_json(run_dir / "retrieval.json", rows)
                write_json(run_dir / "generation.json", gen_rows)
                write_csv(
                    run_dir / "retrieval.csv",
                    [{key: value for key, value in row.items() if key != "chunks"} for row in rows],
                )
                write_csv(run_dir / "generation.csv", gen_rows)
                failures = [row for row in rows if row.get("recall@5", 1) < 1 or row["degraded"]]
                failed_generation = [
                    row
                    for row in gen_rows
                    if not row["correct_refusal"]
                    or (row["answerable"] and row["citation_recall"] < 1)
                ]
                write_json(
                    run_dir / "failures.json",
                    {"retrieval": failures, "generation": failed_generation},
                )
                write_json(output / "summary.json", manifest)
        finally:
            service.close()
    _write_report(output, manifest)
    return manifest


def _write_report(output: Path, report: dict[str, Any]) -> None:
    rows = []
    lines = [
        "# Fixed Regression Experiment",
        "",
        report["annotation"],
        "",
        "Retrieval is document-level: deduplicate document IDs from top-5 returned chunks. "
        "MRR is truncated at 5. No-answer cases are excluded from retrieval denominators.",
        "",
        "| Experiment | R@1 | R@3 | R@5 | MRR@5 | nDCG@5 | p50 ms | p95 ms | Refusal accuracy |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, summary in report["experiments"].items():
        metric = summary["retrieval"]
        generation = summary["generation"]
        row = {
            "experiment": name,
            "status": summary["status"],
            **metric,
            **generation,
            "p50_ms": summary["retrieval_p50_ms"],
            "p95_ms": summary["retrieval_p95_ms"],
        }
        rows.append(row)
        values = [metric[key] for key in ("recall@1", "recall@3", "recall@5", "mrr@5", "ndcg@5")]
        values += [
            summary["retrieval_p50_ms"],
            summary["retrieval_p95_ms"],
            generation["no_answer_refusal_accuracy"],
        ]
        lines.append(
            f"| {name} | "
            + " | ".join("N/A" if item is None else f"{item:.4f}" for item in values)
            + " |"
        )
    lines += [
        "",
        "## Generation and Failure Analysis",
        "",
        "Citation precision is relevance of cited document IDs, "
        "not entailment or legal correctness. "
        "Empty citations have undefined precision; recall is zero for answerable refusals. "
        "See summary.json for coverage and acceptance rate, "
        "and each experiment's failures.json for categorized cases.",
        "",
        "Paid LLM generation and independent human correctness review are not implied by "
        "extractive-v1 results. Warmup time is recorded separately; per-query latency includes "
        "computation, not model download. Single sequential run, not a load benchmark.",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_csv(output / "summary.csv", rows)
