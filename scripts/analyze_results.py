"""Derive categorized failure counts without using a model judge."""

from __future__ import annotations

import argparse
import json
from collections import Counter

from policy_rag.paths import project_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory")
    args = parser.parse_args()
    directory = project_path(args.run_directory)
    report = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    lines = [
        "# Categorized Failures and Resources",
        "",
        "AI-assisted fixed labels, not independent human judgement. "
        "An answerable refusal counts as a generation failure; "
        "document recall does not verify the particular cited sentence.",
        "",
    ]
    for name, experiment in report["experiments"].items():
        retrieval = json.loads((directory / name / "retrieval.json").read_text(encoding="utf-8"))
        generation = json.loads((directory / name / "generation.json").read_text(encoding="utf-8"))
        failures = json.loads((directory / name / "failures.json").read_text(encoding="utf-8"))
        query_map = {row["id"]: row["query"] for row in retrieval}
        counts = Counter(row["category"] for row in failures["generation"])
        lines.extend(
            [
                f"## {name}",
                "",
                f"Retrieval R@5 failures: {len(failures['retrieval'])}. "
                f"Generation/citation failures: {len(failures['generation'])}/{len(generation)}.",
                "",
                "| Category | Generation/citation failures |",
                "|---|---:|",
            ]
        )
        lines.extend(f"| {category} | {count} |" for category, count in sorted(counts.items()))
        lines.extend(["", "Representative cases (first five by fixed dataset order):", ""])
        for row in failures["generation"][:5]:
            reason = (
                row["answer"]["refusal_reason"] or "Cited document set does not match all qrels"
            )
            lines.append(
                f"- {row['id']} / {row['category']}: {query_map[row['id']]} "
                f"Refused={row['refused']}; cited={row['cited_docs']}; reason={reason}"
            )
        index = experiment["index"]
        lines.extend(
            [
                "",
                f"Index: {index['chunk_count']} chunks, {index['index_seconds']:.3f} s, "
                f"{index['index_size_bytes']} local bytes; process peak/current RSS at build "
                f"{index['peak_rss_mb']:.1f} MiB; "
                f"RSS after queries {experiment['rss_mb_after']:.1f} MiB.",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation Limits",
            "",
            "Thresholds are uncalibrated engineering defaults. "
            "Model scores and RRF are not probabilities. "
            "Latency is one sequential CPU regression run, not concurrent-load performance. "
            "Index timings include cold model load only on the first build in a process. "
            "Windows peak_wset is a process-lifetime high-water mark, "
            "not memory allocated solely by indexing; on Linux the fallback is current RSS. "
            "Qdrant Server disk use is not included in local directory size.",
            "",
        ]
    )
    (directory / "failure-analysis.md").write_text("\n".join(lines), encoding="utf-8")
    print(directory / "failure-analysis.md")


if __name__ == "__main__":
    main()
