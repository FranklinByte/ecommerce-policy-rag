from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from policy_rag.config import Settings
from policy_rag.corpus import CorpusRepository
from policy_rag.indexing import IndexBuilder
from policy_rag.models import SourceDocument
from policy_rag.retrieval.service import RetrievalService


class FakeEmbedder:
    """Test double, never used by the benchmark CLI or the production factory."""

    model_name = "BAAI/bge-small-zh-v1.5"

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        rows = []
        for text in texts:
            row = np.frombuffer(hashlib.sha256(text.encode()).digest(), dtype=np.uint8)[:16].astype(
                np.float32
            )
            rows.append(row / np.linalg.norm(row))
        return np.asarray(rows)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


class FakeReranker:
    model_name = "test-double-not-a-real-model"

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        return [0.9 if "AM115" in document and "AM115" in query else 0.01 for document in documents]


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        index_root=tmp_path / "index",
        artifact_root=tmp_path / "results",
        _env_file=None,
    )


@pytest.fixture()
def documents(settings: Settings) -> list[SourceDocument]:
    return CorpusRepository(settings.source_manifest).load_documents()


@pytest.fixture()
def built_settings(settings: Settings) -> Settings:
    builder = IndexBuilder(settings, FakeEmbedder())
    builder.build("structure")
    return settings


@pytest.fixture()
def retrieval(built_settings: Settings):
    service = RetrievalService(built_settings, embedder=FakeEmbedder(), reranker=FakeReranker())
    yield service
    service.close()
