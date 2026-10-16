"""Audit downloaded bytes and parse original formats; do not publish copyrighted text."""

from __future__ import annotations

import pypdfium2 as pdfium

from policy_rag.config import Settings
from policy_rag.corpus import CorpusRepository, file_sha256
from policy_rag.evaluation import write_json
from policy_rag.loaders import LoaderRegistry
from policy_rag.paths import project_path


def main() -> None:
    rows = []
    private = project_path("data/external")
    for entry in CorpusRepository(Settings().source_manifest).read_manifest().sources:
        meta = entry.metadata
        if meta.synthetic:
            continue
        suffix = ".pdf" if meta.source_url.endswith(".pdf") else ".html"
        path = private / f"{meta.doc_id}{suffix}"
        sections = LoaderRegistry().load(path, meta.title)
        row = {
            "doc_id": meta.doc_id,
            "url": meta.source_url,
            "format": suffix,
            "sha256": file_sha256(path),
            "hash_matches_manifest": file_sha256(path) == meta.source_content_sha256,
            "bytes": path.stat().st_size,
            "sections": len(sections),
            "extracted_characters": sum(len(s.text) for s in sections),
            "supporting_sources": [],
        }
        for index, supporting in enumerate(meta.supporting_sources, 1):
            extra = private / f"{meta.doc_id}-support-{index}.html"
            row["supporting_sources"].append(
                {
                    "url": supporting["url"],
                    "sha256": file_sha256(extra),
                    "hash_matches_manifest": file_sha256(extra) == supporting["sha256"],
                }
            )
        if suffix == ".pdf":
            document = pdfium.PdfDocument(str(path))
            try:
                row["pdf_pages"] = len(document)
                for index in (0, len(document) - 1):
                    page = document[index]
                    bitmap = page.render(scale=1.2)
                    bitmap.to_pil().save(private / f"{meta.doc_id}-page-{index + 1}.png")
                    bitmap.close()
                    page.close()
            finally:
                document.close()
        assert row["hash_matches_manifest"] and row["extracted_characters"] > 0
        assert all(item["hash_matches_manifest"] for item in row["supporting_sources"])
        rows.append(row)
    write_json(project_path("eval-results/source-audit.json"), rows)
    print(f"Audited {len(rows)} originals; PDF renders remain in ignored private cache")


if __name__ == "__main__":
    main()
