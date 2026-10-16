from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from policy_rag.config import Settings
from policy_rag.corpus import CorpusRepository, file_sha256
from policy_rag.indexing import load_chunks
from policy_rag.models import (
    IndexManifest,
    PolicyChunk,
    PolicyFilter,
    RetrievalMode,
    RetrievedCandidate,
    ScoreBreakdown,
)
from policy_rag.paths import project_path
from policy_rag.retrieval.bm25 import BM25Index, SparseHit
from policy_rag.retrieval.dense import DenseHit, DenseVectorStore
from policy_rag.retrieval.embedding import (
    Embedder,
    EmbeddingUnavailable,
    SentenceTransformerEmbedder,
)
from policy_rag.retrieval.reranker import CrossEncoderReranker, Reranker


class IndexNotReady(RuntimeError):
    pass


@dataclass
class _Candidate:
    chunk: PolicyChunk
    bm25: float | None = None
    dense: float | None = None
    rrf: float | None = None
    rerank: float | None = None
    initial_rank: int = 0
    final_rank: int = 0
    evidence: float = 0.0


@dataclass
class RetrievalResult:
    requested_mode: RetrievalMode
    effective_mode: RetrievalMode
    candidates: list[RetrievedCandidate]
    index_version: str
    degraded: bool = False
    degradation_reasons: list[str] = field(default_factory=list)


class RetrievalService:
    def __init__(
        self,
        settings: Settings,
        *,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        index_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.index_dir = index_dir or settings.strategy_index_dir()
        manifest_path = self.index_dir / "manifest.json"
        if not manifest_path.is_file():
            raise IndexNotReady(
                f"Index manifest not found at {manifest_path}; run policy-rag index"
            )
        self.manifest = IndexManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if (self.manifest.chunk_size, self.manifest.chunk_overlap) != (
            settings.chunk_size,
            settings.chunk_overlap,
        ):
            raise IndexNotReady("Chunk configuration differs from index; rebuild required")
        if file_sha256(settings.source_manifest) != self.manifest.source_manifest_sha256:
            raise IndexNotReady("Source manifest changed; rebuild the index")
        for source in CorpusRepository(settings.source_manifest).read_manifest().sources:
            path = project_path(source.local_path)
            if not path.is_file() or file_sha256(path) != self.manifest.document_hashes.get(
                source.metadata.doc_id
            ):
                raise IndexNotReady("Source document changed; rebuild the index")
        if self.manifest.qdrant_backend != (settings.qdrant_url or "local"):
            raise IndexNotReady("Vector backend changed; rebuild the index for this backend")
        data_dir = (self.index_dir / self.manifest.data_directory).resolve()
        if not data_dir.is_relative_to(self.index_dir.resolve()):
            raise IndexNotReady("Index path escapes configured index directory")
        self.index_dir = data_dir
        if (self.manifest.embedding_model, self.manifest.embedding_revision) != (
            settings.embedding_model,
            settings.embedding_revision,
        ):
            raise IndexNotReady("Embedding model or revision differs from index; rebuild required")
        for filename, expected in [
            ("chunks.jsonl", self.manifest.chunk_hashes_sha256),
            ("bm25.json", self.manifest.bm25_sha256),
        ]:
            path = self.index_dir / filename
            if not path.is_file() or file_sha256(path) != expected:
                raise IndexNotReady(f"Index integrity check failed: {filename}")
        self.chunks = load_chunks(self.index_dir / "chunks.jsonl")
        self.chunk_by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        self.bm25 = BM25Index.load(self.index_dir / "bm25.json", self.chunks)
        self.embedder = embedder or SentenceTransformerEmbedder(
            settings.embedding_model,
            settings.embedding_device,
            settings.embedding_batch_size,
            settings.model_cache_dir,
            settings.embedding_revision,
            settings.torch_threads,
        )
        self.reranker = reranker or CrossEncoderReranker(
            settings.reranker_model,
            settings.reranker_device,
            settings.reranker_batch_size,
            settings.model_cache_dir,
            settings.reranker_revision,
            settings.torch_threads,
        )
        self.dense: DenseVectorStore | None = None
        self.dense_error: str | None = None
        try:
            self.dense = DenseVectorStore(
                self.manifest.collection_name,
                self.index_dir / "qdrant",
                settings.qdrant_url,
                settings.qdrant_api_key,
            )
        except Exception as exc:
            self.dense_error = type(exc).__name__

    def close(self) -> None:
        if self.dense:
            self.dense.close()

    def retrieve(
        self,
        query: str,
        policy_filter: PolicyFilter,
        requested_mode: RetrievalMode,
        top_k: int,
    ) -> RetrievalResult:
        candidate_k = max(top_k, self.settings.candidate_k)
        sparse_hits = self.bm25.search(query, policy_filter, candidate_k)
        if requested_mode == RetrievalMode.BM25:
            ranked = self._rank_sparse(sparse_hits)
            return self._result(requested_mode, RetrievalMode.BM25, ranked[:top_k])

        try:
            if self.dense is None:
                raise EmbeddingUnavailable(f"Vector store unavailable: {self.dense_error}")
            query_vector = self.embedder.embed_query(query)
            dense_hits = self.dense.search(query_vector, policy_filter, candidate_k)
        except Exception as exc:
            ranked = self._rank_sparse(sparse_hits)
            return self._result(
                requested_mode,
                RetrievalMode.BM25,
                ranked[:top_k],
                degraded=True,
                reasons=[f"Dense retrieval unavailable: {type(exc).__name__}"],
            )

        if requested_mode == RetrievalMode.DENSE:
            ranked = self._rank_dense(dense_hits)
            return self._result(requested_mode, RetrievalMode.DENSE, ranked[:top_k])

        ranked = self._rank_rrf(sparse_hits, dense_hits)[:candidate_k]
        if requested_mode == RetrievalMode.HYBRID:
            return self._result(requested_mode, RetrievalMode.HYBRID, ranked[:top_k])

        try:
            rerank_scores = self.reranker.score(query, [item.chunk.text for item in ranked])
            for candidate, score in zip(ranked, rerank_scores, strict=True):
                candidate.rerank = score
                candidate.evidence = score
            ranked.sort(key=lambda item: (-(item.rerank or 0.0), item.chunk.chunk_id))
            for rank, candidate in enumerate(ranked, start=1):
                candidate.final_rank = rank
            return self._result(requested_mode, RetrievalMode.HYBRID_RERANK, ranked[:top_k])
        except Exception as exc:
            return self._result(
                requested_mode,
                RetrievalMode.HYBRID,
                ranked[:top_k],
                degraded=True,
                reasons=[f"Reranker unavailable: {type(exc).__name__}"],
            )

    def _rank_sparse(self, hits: list[SparseHit]) -> list[_Candidate]:
        ranked: list[_Candidate] = []
        for hit in hits:
            score = float(hit.score)
            rank = int(hit.rank)
            ranked.append(
                _Candidate(
                    chunk=self.chunk_by_id[hit.chunk_id],
                    bm25=score,
                    initial_rank=rank,
                    final_rank=rank,
                    evidence=1.0 - math.exp(-score / 8.0),
                )
            )
        return ranked

    def _rank_dense(self, hits: list[DenseHit]) -> list[_Candidate]:
        return [
            _Candidate(
                chunk=self.chunk_by_id[hit.chunk_id],
                dense=hit.score,
                initial_rank=hit.rank,
                final_rank=hit.rank,
                evidence=max(0.0, min(1.0, hit.score)),
            )
            for hit in hits
        ]

    def _rank_rrf(
        self, sparse_hits: list[SparseHit], dense_hits: list[DenseHit]
    ) -> list[_Candidate]:
        by_id: dict[str, _Candidate] = {}
        for hit in sparse_hits:
            chunk_id = hit.chunk_id
            candidate = by_id.setdefault(chunk_id, _Candidate(chunk=self.chunk_by_id[chunk_id]))
            candidate.bm25 = float(hit.score)
            candidate.rrf = (candidate.rrf or 0.0) + 1.0 / (self.settings.rrf_k + hit.rank)
        for dense_hit in dense_hits:
            candidate = by_id.setdefault(
                dense_hit.chunk_id, _Candidate(chunk=self.chunk_by_id[dense_hit.chunk_id])
            )
            candidate.dense = dense_hit.score
            candidate.rrf = (candidate.rrf or 0.0) + 1.0 / (self.settings.rrf_k + dense_hit.rank)
        ranked = sorted(by_id.values(), key=lambda item: (-(item.rrf or 0.0), item.chunk.chunk_id))
        max_rrf = max((item.rrf or 0.0 for item in ranked), default=1.0)
        for rank, candidate in enumerate(ranked, start=1):
            candidate.initial_rank = rank
            candidate.final_rank = rank
            sparse_confidence = (
                1.0 - math.exp(-(candidate.bm25 or 0.0) / 8.0) if candidate.bm25 else 0.0
            )
            dense_confidence = max(0.0, min(1.0, candidate.dense or 0.0))
            rank_confidence = (candidate.rrf or 0.0) / max(max_rrf, 1e-12)
            candidate.evidence = (
                0.45 * sparse_confidence + 0.45 * dense_confidence + 0.10 * rank_confidence
            )
        return ranked

    def _result(
        self,
        requested: RetrievalMode,
        effective: RetrievalMode,
        candidates: list[_Candidate],
        *,
        degraded: bool = False,
        reasons: list[str] | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(
            requested_mode=requested,
            effective_mode=effective,
            candidates=[self._to_public(candidate) for candidate in candidates],
            index_version=self.manifest.index_version,
            degraded=degraded,
            degradation_reasons=reasons or [],
        )

    @staticmethod
    def _to_public(candidate: _Candidate) -> RetrievedCandidate:
        metadata = candidate.chunk.metadata
        return RetrievedCandidate(
            chunk_id=candidate.chunk.chunk_id,
            doc_id=candidate.chunk.doc_id,
            title=metadata.title,
            text=candidate.chunk.text,
            section_path=candidate.chunk.section_path,
            platform=metadata.platform,
            product_categories=metadata.product_categories,
            version=metadata.version,
            effective_from=metadata.effective_from,
            effective_to=metadata.effective_to,
            source_url=metadata.section_sources.get(
                candidate.chunk.section_path[-1], metadata.source_url
            ),
            additional_source_urls=[source["url"] for source in metadata.supporting_sources],
            policy_family=metadata.policy_family,
            synthetic=metadata.synthetic,
            initial_rank=candidate.initial_rank,
            final_rank=candidate.final_rank,
            scores=ScoreBreakdown(
                bm25=candidate.bm25,
                dense=candidate.dense,
                rrf=candidate.rrf,
                rerank=candidate.rerank,
                evidence=candidate.evidence,
            ),
        )
