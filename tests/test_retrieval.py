from datetime import date

import numpy as np
import pytest

from policy_rag.chunking import PolicyChunker
from policy_rag.indexing import IndexBuilder
from policy_rag.models import PolicyFilter, RetrievalMode
from policy_rag.retrieval.bm25 import BM25Index, chunk_matches_filter
from policy_rag.retrieval.dense import DenseVectorStore
from policy_rag.retrieval.embedding import EmbeddingUnavailable, SentenceTransformerEmbedder
from policy_rag.retrieval.reranker import CrossEncoderReranker, RerankerUnavailable
from policy_rag.retrieval.service import IndexNotReady, RetrievalService
from policy_rag.retrieval.tokenizer import ChineseTokenizer
from tests.conftest import FakeEmbedder


def test_tokenizer_identifiers_chinese():
    tokens = ChineseTokenizer().tokenize("AM115 有线耳机保修90天")
    assert "id:am115" in tokens and "zh:保修" in tokens
    assert not ChineseTokenizer().tokenize("？！")


def test_bm25_known_top_and_persistence(documents, tmp_path):
    chunks = [
        chunk for doc in documents for chunk in PolicyChunker("structure", 520, 80).split(doc)
    ]
    index = BM25Index(chunks)
    hits = index.search("AM115 有线耳机保修", PolicyFilter(platform="huawei_cn"), 5)
    assert hits[0].chunk_id in {chunk.chunk_id for chunk in chunks if "AM115" in chunk.text}
    assert not index.search("  ", PolicyFilter(), 5)
    assert not index.search("故障", PolicyFilter(platform="missing"), 5)
    path = tmp_path / "bm25.json"
    index.save(path)
    assert hits == BM25Index.load(path, chunks).search(
        "AM115 有线耳机保修", PolicyFilter(platform="huawei_cn"), 5
    )
    path.write_text('{"schema_version":"bad"}', encoding="utf-8")
    with pytest.raises(ValueError):
        BM25Index.load(path, chunks)


def test_sparse_dense_filters_consistent(retrieval):
    filters = [
        PolicyFilter(),
        PolicyFilter(platform="huawei_cn"),
        PolicyFilter(product_category="computer"),
        PolicyFilter(platform="starmall", version="v1", product_category="phone"),
        PolicyFilter(platform="starmall", as_of_date=date(2024, 12, 31)),
        PolicyFilter(platform="starmall", as_of_date=date(2025, 1, 1)),
        PolicyFilter(as_of_date=date(2026, 9, 6)),
        PolicyFilter(platform="missing"),
    ]
    vector = np.ones(16, dtype=np.float32) / 4
    for policy_filter in filters:
        allowed = {
            chunk.chunk_id
            for chunk in retrieval.chunks
            if chunk_matches_filter(chunk, policy_filter)
        }
        dense = retrieval.dense.search(vector, policy_filter, 100)
        assert {hit.chunk_id for hit in dense} == allowed


@pytest.mark.parametrize("mode", list(RetrievalMode))
def test_retrieval_modes_and_ranking_trace(retrieval, mode):
    result = retrieval.retrieve("AM115 耳机", PolicyFilter(platform="huawei_cn"), mode, 5)
    assert result.effective_mode == mode and not result.degraded
    assert 1 <= len(result.candidates) <= 5
    if mode == RetrievalMode.HYBRID_RERANK:
        assert result.candidates[0].scores.rerank == 0.9
        assert "AM115" in result.candidates[0].text


def test_dense_failure_explicit_bm25_fallback(retrieval, monkeypatch):
    def fail(_):
        raise EmbeddingUnavailable("offline")

    monkeypatch.setattr(retrieval.embedder, "embed_query", fail)
    result = retrieval.retrieve("AM115", PolicyFilter(), RetrievalMode.DENSE, 5)
    assert result.degraded and result.effective_mode == RetrievalMode.BM25
    assert "EmbeddingUnavailable" in result.degradation_reasons[0]


def test_reranker_failure_explicit_hybrid_fallback(retrieval, monkeypatch):
    def fail(*_):
        raise RerankerUnavailable("offline")

    monkeypatch.setattr(retrieval.reranker, "score", fail)
    result = retrieval.retrieve("AM115", PolicyFilter(), RetrievalMode.HYBRID_RERANK, 5)
    assert result.degraded and result.effective_mode == RetrievalMode.HYBRID


def test_index_reuse_model_mismatch_and_corruption(built_settings):
    builder = IndexBuilder(built_settings, FakeEmbedder())
    first = builder.build()
    assert first == builder.build()
    with pytest.raises(IndexNotReady, match="revision"):
        RetrievalService(built_settings.model_copy(update={"embedding_revision": "bad"}))
    with pytest.raises(IndexNotReady, match="Chunk configuration"):
        RetrievalService(built_settings.model_copy(update={"chunk_size": 480}))
    (built_settings.strategy_index_dir() / first.data_directory / "chunks.jsonl").write_text(
        "bad", encoding="utf-8"
    )
    with pytest.raises(IndexNotReady, match="integrity"):
        RetrievalService(built_settings)
    repaired = builder.build()
    assert repaired.data_directory != first.data_directory
    assert repaired.index_version == first.index_version


def test_failed_build_preserves_previous_manifest(built_settings):
    previous = (built_settings.strategy_index_dir() / "manifest.json").read_bytes()

    class Failure(FakeEmbedder):
        def embed_documents(self, texts):
            raise EmbeddingUnavailable("offline")

    with pytest.raises(EmbeddingUnavailable):
        IndexBuilder(built_settings, Failure()).build(force=True)
    assert (built_settings.strategy_index_dir() / "manifest.json").read_bytes() == previous


def test_missing_index(settings):
    with pytest.raises(IndexNotReady):
        RetrievalService(settings)


def test_dense_rebuild_and_count_validation(tmp_path, documents):
    chunks = PolicyChunker("structure", 520, 80).split(documents[0])
    store = DenseVectorStore("test", tmp_path / "qdrant")
    try:
        with pytest.raises(ValueError):
            store.build(chunks, np.ones((1, 16)), 16)
        vectors = FakeEmbedder().embed_documents([chunk.text for chunk in chunks])
        store.build(chunks, vectors, 16)
        store.build(chunks, vectors, 16)
        assert store.backend_name.startswith("local:")
    finally:
        store.close()


def test_model_adapters_real_interfaces_with_injected_models():
    class EmbeddingModel:
        def encode(self, texts, **kwargs):
            return np.ones((len(texts), 16))

    embedder = SentenceTransformerEmbedder("test")
    embedder._model = EmbeddingModel()
    assert embedder.embed_query("查询").shape == (16,)

    class PairModel:
        def predict(self, pairs, **kwargs):
            return np.array([-2, 2])

    reranker = CrossEncoderReranker("test")
    reranker._model = PairModel()
    assert reranker.score("q", []) == []
    scores = reranker.score("q", ["a", "b"])
    assert scores[0] < 0.5 < scores[1]
    embedder._model = object()
    reranker._model = object()
    with pytest.raises(EmbeddingUnavailable):
        embedder.embed_query("bad")
    with pytest.raises(RerankerUnavailable):
        reranker.score("bad", ["a"])
