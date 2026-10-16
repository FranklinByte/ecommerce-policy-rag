from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psutil

from policy_rag.chunking import PolicyChunker
from policy_rag.config import Settings
from policy_rag.corpus import CorpusRepository, file_sha256
from policy_rag.logging import get_logger
from policy_rag.models import IndexManifest, PolicyChunk
from policy_rag.retrieval.bm25 import BM25Index
from policy_rag.retrieval.dense import DenseVectorStore
from policy_rag.retrieval.embedding import Embedder, SentenceTransformerEmbedder

logger = get_logger()


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _write_chunks(path: Path, chunks: list[PolicyChunk]) -> None:
    path.write_text("\n".join(chunk.model_dump_json() for chunk in chunks) + "\n", encoding="utf-8")


def load_chunks(path: Path) -> list[PolicyChunk]:
    return [
        PolicyChunk.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class IndexBuilder:
    def __init__(self, settings: Settings, embedder: Embedder | None = None) -> None:
        self.settings = settings
        self.embedder = embedder or SentenceTransformerEmbedder(
            settings.embedding_model,
            settings.embedding_device,
            settings.embedding_batch_size,
            settings.model_cache_dir,
            settings.embedding_revision,
            settings.torch_threads,
        )

    def build(self, strategy: str | None = None, *, force: bool = False) -> IndexManifest:
        strategy = strategy or self.settings.chunk_strategy
        index_dir = self.settings.strategy_index_dir(strategy)
        index_dir.mkdir(parents=True, exist_ok=True)
        corpus = CorpusRepository(self.settings.source_manifest)
        documents = corpus.load_documents(verify_hashes=True)
        chunker = PolicyChunker(strategy, self.settings.chunk_size, self.settings.chunk_overlap)
        chunks = [chunk for document in documents for chunk in chunker.split(document)]
        document_hashes = {
            document.metadata.doc_id: document.metadata.content_sha256 for document in documents
        }
        identity = json.dumps(
            {
                "schema": "1",
                "strategy": strategy,
                "size": self.settings.chunk_size,
                "overlap": self.settings.chunk_overlap,
                "embedding_model": self.embedder.model_name,
                "embedding_revision": self.settings.embedding_revision,
                "qdrant_backend": self.settings.qdrant_url or "local",
                "manifest_hash": corpus.manifest_sha256(),
                "document_hashes": document_hashes,
                "chunk_ids": [chunk.chunk_id for chunk in chunks],
            },
            sort_keys=True,
        )
        index_version = hashlib.sha256(identity.encode()).hexdigest()[:20]
        manifest_path = index_dir / "manifest.json"
        if not force and manifest_path.is_file():
            existing = IndexManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
            if existing.index_version == index_version and self._is_reusable(index_dir, existing):
                logger.info("index_reused", strategy=strategy, index_version=index_version)
                return existing

        started = time.perf_counter()
        build_id = f"{index_version}_{uuid.uuid4().hex[:8]}"
        build_dir = index_dir / "versions" / build_id
        build_dir.mkdir(parents=True)
        logger.info(
            "index_build_started",
            strategy=strategy,
            documents=len(documents),
            chunks=len(chunks),
            embedding_model=self.embedder.model_name,
        )
        _write_chunks(build_dir / "chunks.jsonl", chunks)
        BM25Index(chunks).save(build_dir / "bm25.json")
        vectors = self.embedder.embed_documents([chunk.text for chunk in chunks])
        dimension = int(vectors.shape[1])
        collection_name = f"{self.settings.collection_prefix}_{strategy}_{build_id}".replace(
            "-", "_"
        )
        dense_store = DenseVectorStore(
            collection_name,
            build_dir / "qdrant",
            self.settings.qdrant_url,
            self.settings.qdrant_api_key,
        )
        try:
            dense_store.build(chunks, vectors, dimension)
        finally:
            dense_store.close()
        elapsed = time.perf_counter() - started
        memory = psutil.Process().memory_info()
        peak_rss_mb = float(getattr(memory, "peak_wset", memory.rss)) / 1024 / 1024
        manifest = IndexManifest(
            index_version=index_version,
            strategy=strategy,
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
            collection_name=collection_name,
            qdrant_backend=self.settings.qdrant_url or "local",
            data_directory=f"versions/{build_id}",
            embedding_model=self.embedder.model_name,
            reranker_model=self.settings.reranker_model,
            embedding_revision=self.settings.embedding_revision,
            reranker_revision=self.settings.reranker_revision,
            vector_dimension=dimension,
            source_manifest_sha256=corpus.manifest_sha256(),
            document_hashes=document_hashes,
            document_count=len(documents),
            chunk_count=len(chunks),
            created_at=datetime.now(UTC),
            index_seconds=elapsed,
            peak_rss_mb=peak_rss_mb,
            index_size_bytes=_directory_size(build_dir),
            chunk_hashes_sha256=file_sha256(build_dir / "chunks.jsonl"),
            bm25_sha256=file_sha256(build_dir / "bm25.json"),
        )
        (build_dir / "manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        staging = index_dir / f"manifest-{build_id}.tmp"
        staging.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        staging.replace(manifest_path)
        logger.info(
            "index_build_finished",
            strategy=strategy,
            index_version=index_version,
            seconds=round(elapsed, 3),
            size_bytes=manifest.index_size_bytes,
        )
        return manifest

    def _is_reusable(self, index_dir: Path, manifest: IndexManifest) -> bool:
        directory = (index_dir / manifest.data_directory).resolve()
        if not directory.is_relative_to(index_dir.resolve()):
            raise ValueError("Index path escapes configured index directory")
        for name, expected in [
            ("chunks.jsonl", manifest.chunk_hashes_sha256),
            ("bm25.json", manifest.bm25_sha256),
        ]:
            path = directory / name
            if not path.is_file() or file_sha256(path) != expected:
                return False
        store = DenseVectorStore(
            manifest.collection_name,
            directory / "qdrant",
            self.settings.qdrant_url,
            self.settings.qdrant_api_key,
        )
        try:
            return bool(store.client.collection_exists(manifest.collection_name))
        finally:
            store.close()
