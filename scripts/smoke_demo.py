"""Exercise real HTTP/UI behavior; requires the dev extra and installed Chromium."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

import httpx
from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright

from policy_rag.evaluation import write_json
from policy_rag.paths import project_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8010")
    parser.add_argument("--name", default="local")
    args = parser.parse_args()
    output = project_path(f"eval-results/{args.name}-smoke")
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "question": "AM115 有线耳机保修期限是多久？",
        "filters": {"platform": "huawei_cn", "product_category": "accessory"},
        "generate": True,
    }
    evidence = {"url": args.url, "time": datetime.now(UTC).isoformat(), "api": [], "viewports": []}
    with httpx.Client(base_url=args.url, timeout=180) as client:
        assert client.get("/ready").status_code == 200
        evidence["health"] = client.get("/health").json()
        for mode in ("bm25", "dense", "hybrid", "hybrid_rerank"):
            response = client.post("/api/v1/query", json={**payload, "mode": mode})
            response.raise_for_status()
            result = response.json()
            assert not result["degraded"] and result["effective_mode"] == mode
            assert (
                not result["answer"]["refused"] and "90" in result["answer"]["policy_explanation"]
            )
            assert result["answer"]["citations"]
            evidence["api"].append(result)
        response = client.post(
            "/api/v1/query",
            json={
                "question": "NEBULA-P2 激活手机退货",
                "mode": "hybrid_rerank",
                "filters": {
                    "platform": "starmall",
                    "product_category": "phone",
                    "as_of_date": "2025-06-01",
                },
            },
        )
        response.raise_for_status()
        dated = response.json()
        assert dated["candidates"] and all(
            c["version"] == "v2" and c["synthetic"] for c in dated["candidates"]
        )
        evidence["date_filter"] = dated
        response = client.post(
            "/api/v1/query",
            json={"question": "有没有可用政策", "filters": {"platform": "missing-platform"}},
        )
        response.raise_for_status()
        assert response.json()["answer"]["refused"] and not response.json()["answer"]["citations"]
        evidence["no_evidence"] = response.json()
        assert client.post("/api/v1/query", json={"question": " "}).status_code == 422

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in ((1440, 1000), (390, 844), (360, 800)):
            page = browser.new_page(
                viewport={"width": width, "height": height}, device_scale_factor=1
            )
            errors = []
            page.on("pageerror", lambda error, captured=errors: captured.append(str(error)))
            page.goto(args.url, wait_until="networkidle")
            page.locator("#question").fill(payload["question"])
            with page.expect_response("**/api/v1/query", timeout=180000) as incoming:
                page.locator("#searchButton").click()
            assert incoming.value.status == 200
            page.locator("#answerContent").wait_for(state="visible")
            assert page.locator("#citations a").count() > 0
            assert page.locator("#searchButton svg").count() == 1
            assert page.locator(".candidate").count() > 0
            overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            assert not overflow and not errors
            screenshot = output / f"query-{width}.png"
            page.screenshot(path=str(screenshot), full_page=True)
            with Image.open(screenshot) as rendered:
                variance = ImageStat.Stat(rendered.convert("RGB")).stddev
                assert min(variance) > 10
            # A failed new request must not leave the previous answer or citations visible.
            page.locator("#question").fill(" ")
            with page.expect_response("**/api/v1/query") as invalid:
                page.locator("#searchButton").click()
            assert invalid.value.status == 422
            page.locator("#degradation").wait_for(state="visible")
            assert page.locator("#answerContent").is_hidden()
            evidence["viewports"].append(
                {
                    "width": width,
                    "height": height,
                    "horizontal_overflow": overflow,
                    "page_errors": errors,
                    "pixel_stddev": variance,
                    "screenshot": screenshot.name,
                }
            )
            page.close()
        browser.close()
    write_json(output / "results.json", evidence)
    print(f"Real API and browser checks passed: {args.url}")


if __name__ == "__main__":
    main()
