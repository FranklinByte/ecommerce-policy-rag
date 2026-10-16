"""Freeze or verify Git-visible project bytes, excluding secrets and runtime caches."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from policy_rag.corpus import file_sha256
from policy_rag.evaluation import write_json
from policy_rag.paths import PROJECT_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--manifest", type=Path, default=Path("freeze.json"))
    parser.add_argument("--maintenance-of", type=Path)
    args = parser.parse_args()
    manifest_path = PROJECT_ROOT / args.manifest
    if args.verify:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        failures = [
            name
            for name, digest in manifest["files"].items()
            if not (PROJECT_ROOT / name).is_file() or file_sha256(PROJECT_ROOT / name) != digest
        ]
        if failures:
            raise RuntimeError(f"Frozen files changed or missing: {failures}")
        print(f"Verified {len(manifest['files'])} frozen files")
        return
    if manifest_path.exists():
        raise ValueError("Manifest exists; preserve it and choose a new --manifest path")
    metadata = {}
    if args.maintenance_of:
        baseline_path = PROJECT_ROOT / args.maintenance_of
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        metadata = {
            "baseline_manifest": args.maintenance_of.as_posix(),
            "baseline_sha256": file_sha256(baseline_path),
            "evaluation_applies_to": "historical_baseline_only",
            "changed_since_baseline": [
                name
                for name, digest in baseline["files"].items()
                if not (PROJECT_ROOT / name).is_file() or file_sha256(PROJECT_ROOT / name) != digest
            ],
        }
    else:
        report = json.loads(
            (PROJECT_ROOT / "eval-results/frozen-2026-09-06/summary.json").read_text(
                encoding="utf-8"
            )
        )
        assert len(report["experiments"]) == 8
        assert all(item["status"] == "completed" for item in report["experiments"].values())
        for name, digest in report["source_hashes"].items():
            assert file_sha256(PROJECT_ROOT / name) == digest, (
                f"Source changed after evaluation: {name}"
            )
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=PROJECT_ROOT,
        )
        .decode("utf-8")
        .split("\0")
    )
    files = {
        name: file_sha256(PROJECT_ROOT / name)
        for name in sorted(set(names))
        if name and (PROJECT_ROOT / name) != manifest_path and (PROJECT_ROOT / name).is_file()
    }
    write_json(
        manifest_path,
        {
            "release": "0.1.0+maintenance" if args.maintenance_of else "0.1.0",
            "created_at": datetime.now(UTC).isoformat(),
            "evaluation": "eval-results/frozen-2026-09-06",
            "files": files,
            "cloud_ci": "not_executed",
            "paid_llm_generation": "not_executed",
            "human_review": "not_executed",
            **metadata,
        },
    )
    print(f"Frozen {len(files)} files; no Git commit created")


if __name__ == "__main__":
    main()
