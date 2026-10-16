from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from policy_rag.config import Settings
from policy_rag.corpus import CorpusRepository
from policy_rag.evaluation import write_json

ALLOWED_HOSTS = {"www.apple.com.cn", "consumer.huawei.com", "order.mi.com"}


def validate_source_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Source URL must be HTTPS on an explicitly allowed official host")


@retry(
    retry=retry_if_exception_type(httpx.TransportError),
    wait=wait_exponential(multiplier=0.5, max=2),
    stop=stop_after_attempt(3),
    reraise=True,
)
def download(url: str, settings: Settings) -> bytes:
    validate_source_url(url)
    with httpx.Client(timeout=settings.download_timeout_seconds, follow_redirects=False) as client:
        current = url
        for _ in range(4):
            validate_source_url(current)
            with client.stream(
                "GET",
                current,
                headers={
                    "User-Agent": "PolicyRAG-Research/0.1 (private verification; no redistribution)"
                },
            ) as response:
                if response.is_redirect:
                    current = str(response.url.join(response.headers["location"]))
                    continue
                response.raise_for_status()
                data = bytearray()
                for block in response.iter_bytes():
                    data.extend(block)
                    if len(data) > settings.max_download_bytes:
                        raise ValueError("Source exceeds maximum download size")
                return bytes(data)
    raise ValueError("Source exceeded redirect limit")


def fetch_sources(
    settings: Settings, output: Path, *, update_manifest: bool = False
) -> list[dict[str, object]]:
    output.mkdir(parents=True, exist_ok=True)
    manifest = CorpusRepository(settings.source_manifest).read_manifest()
    results: list[dict[str, object]] = []
    for entry in manifest.sources:
        if entry.metadata.synthetic:
            continue
        meta = entry.metadata
        try:
            raw = download(meta.source_url, settings)
            suffix = ".pdf" if urlsplit(meta.source_url).path.endswith(".pdf") else ".html"
            destination = output / f"{meta.doc_id}{suffix}"
            destination.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            retrieved_at = datetime.now(UTC)
            meta.source_content_sha256 = digest
            meta.retrieved_at = retrieved_at
            for number, supporting in enumerate(meta.supporting_sources, 1):
                supporting_raw = download(supporting["url"], settings)
                supporting["sha256"] = hashlib.sha256(supporting_raw).hexdigest()
                supporting["retrieved_at"] = datetime.now(UTC).isoformat()
                supporting_path = output / f"{meta.doc_id}-support-{number}.html"
                supporting_path.write_bytes(supporting_raw)
            results.append(
                {
                    "doc_id": meta.doc_id,
                    "url": meta.source_url,
                    "status": "downloaded",
                    "sha256": digest,
                    "retrieved_at": retrieved_at.isoformat(),
                    "bytes": len(raw),
                    "filename": destination.name,
                }
            )
        except (httpx.HTTPError, ValueError) as exc:
            results.append(
                {
                    "doc_id": meta.doc_id,
                    "url": meta.source_url,
                    "status": "failed",
                    "error": type(exc).__name__,
                }
            )
    write_json(output / "fetch-results.json", results)
    if update_manifest:
        settings.source_manifest.write_text(
            yaml.safe_dump(manifest.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return results


def import_snapshot(settings: Settings, doc_id: str, cache: Path, output: Path) -> None:
    manifest = CorpusRepository(settings.source_manifest).read_manifest()
    entry = next((item for item in manifest.sources if item.metadata.doc_id == doc_id), None)
    if entry is None or entry.metadata.synthetic:
        raise ValueError("Choose a public source doc_id from data/sources.yaml")
    results = json.loads((cache / "fetch-results.json").read_text(encoding="utf-8"))
    result = next(
        item for item in results if item["doc_id"] == doc_id and item["status"] == "downloaded"
    )
    path = (cache / result["filename"]).resolve()
    if not path.is_relative_to(cache.resolve()):
        raise ValueError("Snapshot path escapes cache")
    entry.local_path = str(path)
    entry.metadata.content_sha256 = str(result["sha256"])
    entry.metadata.source_content_sha256 = str(result["sha256"])
    entry.metadata.retrieved_at = datetime.fromisoformat(str(result["retrieved_at"]))
    entry.metadata.source_type = "private_raw_snapshot"
    entry.metadata.redistribution_status = "private_cache_not_for_redistribution"
    manifest.sources = [entry]
    output.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
