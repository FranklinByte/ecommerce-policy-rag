"""Record local quality checks without claiming remote CI execution."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from policy_rag.evaluation import write_json

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    checks = [
        ["ruff", "format", "--check", "src", "tests", "scripts"],
        ["ruff", "check", "src", "tests", "scripts"],
        ["mypy", "src/policy_rag"],
        [
            "pytest",
            "--cov-report=json:eval-results/coverage.json",
            "--junitxml=eval-results/pytest.xml",
            "-o",
            "faulthandler_timeout=60",
        ],
        ["policy_rag.cli", "verify-corpus"],
    ]
    output = ROOT / "eval-results" / "validation"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for number, args in enumerate(checks, 1):
        command = [sys.executable, "-m", *args]
        started = datetime.now(UTC)
        run = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=600)
        log = run.stdout.decode("utf-8", errors="replace") + run.stderr.decode(
            "utf-8", errors="replace"
        )
        (output / f"{number}-{args[0]}.txt").write_text(log, encoding="utf-8")
        results.append(
            {
                "command": command,
                "exit_code": run.returncode,
                "started_at": started.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
            }
        )
        print(f"{args[0]}: exit={run.returncode}", flush=True)
        if run.returncode:
            print(log, flush=True)
    write_json(output / "checks.json", {"checks": results, "cloud_ci": "not_executed"})
    raise SystemExit(int(any(item["exit_code"] for item in results)))


if __name__ == "__main__":
    main()
