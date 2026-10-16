"""Maintain factual provenance after digest edits; never infer real effective dates."""

from datetime import UTC, datetime

import yaml

from policy_rag.config import Settings
from policy_rag.corpus import file_sha256
from policy_rag.paths import project_path

path = Settings().source_manifest
data = yaml.safe_load(path.read_text(encoding="utf-8"))
for entry in data["sources"]:
    metadata = entry["metadata"]
    metadata["content_sha256"] = file_sha256(project_path(entry["local_path"]))
    if metadata["doc_id"].startswith("synthetic-starmall-electronics-"):
        metadata["policy_family"] = "synthetic-starmall-electronics"
    elif metadata["doc_id"].startswith("applecare-plus-cn-"):
        metadata["policy_family"] = "applecare-plus-cn"
    if metadata["doc_id"] == "apple-hardware-warranty-cn-current":
        urls = [
            "https://www.apple.com.cn/legal/statutory-warranty/",
            "https://www.apple.com.cn/legal/warranty/products/warranty-china.html",
        ]
        metadata.setdefault("supporting_sources", [{"url": url} for url in urls])
        if not metadata["supporting_sources"]:
            metadata["supporting_sources"] = [{"url": url} for url in urls]
        metadata["section_sources"] = {"Mac 与地区差异": urls[0], "保障边界": urls[1]}
    if not metadata["synthetic"]:
        metadata["effective_from"] = None
        metadata["effective_to"] = None
        metadata["validity_basis"] = "unknown; file and snapshot dates are not effective dates"
        metadata["annotation_note"] = (
            "AI-assisted factual digest of official public source; not human legal review. "
            "Effective interval unknown. Retrieved timestamp is digest verification time "
            "until fetch-sources records a byte download."
        )
        if metadata["source_content_sha256"] is None:
            metadata["retrieved_at"] = datetime.now(UTC).isoformat()
    else:
        metadata["validity_basis"] = "explicit synthetic fixture dates"
path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
