"""Build and health-check this project's Compose stack, including a reversible outage."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime

import httpx

from policy_rag.evaluation import write_json
from policy_rag.paths import PROJECT_ROOT, project_path


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=True,
    )


def main() -> None:
    output = project_path("eval-results/docker-validation")
    output.mkdir(parents=True, exist_ok=True)
    built = docker("compose", "build")
    (output / "build.txt").write_text(built.stdout + built.stderr, encoding="utf-8")
    docker("compose", "up", "-d")
    with httpx.Client(base_url="http://127.0.0.1:8011", timeout=120) as client:
        for _attempt in range(120):
            try:
                if client.get("/ready", timeout=3).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("Compose app did not become ready in 240 seconds")
        query = {
            "question": "AM115 有线耳机保修期限是多久？",
            "mode": "hybrid_rerank",
            "filters": {"platform": "huawei_cn", "product_category": "accessory"},
        }
        response = client.post("/api/v1/query", json=query)
        response.raise_for_status()
        warm = response.json()
        assert not warm["degraded"]
        try:
            docker("compose", "stop", "qdrant")
            assert client.get("/ready").status_code == 503
            degraded = client.post("/api/v1/query", json=query)
            degraded.raise_for_status()
            fallback = degraded.json()
            assert fallback["degraded"] and fallback["effective_mode"] == "bm25"
        finally:
            docker("compose", "start", "qdrant")
        for _attempt in range(30):
            if client.get("/ready").status_code == 200:
                break
            time.sleep(1)
        assert client.get("/ready").status_code == 200
        recovered = client.post("/api/v1/query", json=query)
        recovered.raise_for_status()
        assert not recovered.json()["degraded"]
        app_id = docker("compose", "ps", "-q", "app").stdout.strip()
        inspection = json.loads(docker("inspect", app_id).stdout)[0]
        image = json.loads(docker("image", "inspect", "ecommerce-policy-rag:0.1.0").stdout)[0]
        evidence = {
            "time": datetime.now(UTC).isoformat(),
            "build_exit_code": built.returncode,
            "image_id": image["Id"],
            "image_size_bytes": image["Size"],
            "container_state": inspection["State"],
            "container_user": inspection["Config"]["User"],
            "ready": client.get("/ready").json(),
            "normal": warm,
            "qdrant_outage": fallback,
            "recovered": recovered.json(),
            "cloud_ci": "not_executed",
        }
        write_json(output / "results.json", evidence)
        print("Docker build, readiness, real reranker, BM25 fallback and recovery passed")


if __name__ == "__main__":
    main()
