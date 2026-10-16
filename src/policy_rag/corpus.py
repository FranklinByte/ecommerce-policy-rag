from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from policy_rag.loaders import LoaderRegistry
from policy_rag.models import DocumentMetadata, SourceDocument
from policy_rag.paths import project_path


class CorpusIntegrityError(RuntimeError):
    pass


class SourceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_path: str
    metadata: DocumentMetadata


class SourceManifest(BaseModel):
    schema_version: str
    description: str
    sources: list[SourceEntry]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class CorpusRepository:
    def __init__(self, manifest_path: Path, loader_registry: LoaderRegistry | None = None) -> None:
        self.manifest_path = manifest_path
        self.loader_registry = loader_registry or LoaderRegistry()

    def read_manifest(self) -> SourceManifest:
        raw = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8"))
        return SourceManifest.model_validate(raw)

    def manifest_sha256(self) -> str:
        return file_sha256(self.manifest_path)

    def load_documents(self, verify_hashes: bool = True) -> list[SourceDocument]:
        documents: list[SourceDocument] = []
        for entry in self.read_manifest().sources:
            path = project_path(entry.local_path)
            if not path.is_file():
                raise CorpusIntegrityError(f"Corpus file is missing: {path}")
            actual_hash = file_sha256(path)
            if verify_hashes and actual_hash != entry.metadata.content_sha256:
                raise CorpusIntegrityError(
                    f"Hash mismatch for {entry.metadata.doc_id}: expected "
                    f"{entry.metadata.content_sha256}, got {actual_hash}"
                )
            sections = self.loader_registry.load(path, entry.metadata.title)
            documents.append(
                SourceDocument(
                    metadata=entry.metadata,
                    local_path=str(path),
                    sections=sections,
                )
            )
        return documents
