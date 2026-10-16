from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class EmbeddingUnavailable(RuntimeError):
    pass


class Embedder(Protocol):
    @property
    def model_name(self) -> str: ...

    def embed_documents(self, texts: Sequence[str]) -> NDArray[np.float32]: ...

    def embed_query(self, text: str) -> NDArray[np.float32]: ...


class SentenceTransformerEmbedder:
    query_instruction = "为这个句子生成表示以用于检索相关文章："

    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        batch_size: int = 32,
        cache_dir: Path | None = None,
        revision: str = "7999e1d3359715c523056ef9478215996d62a620",
        threads: int = 4,
    ) -> None:
        self._model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.cache_dir = cache_dir
        self.revision = revision
        self.threads = threads
        self._model: object | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def _load(self) -> object:
        if self._model is None:
            try:
                import torch
                from sentence_transformers import SentenceTransformer

                torch.set_num_threads(self.threads)

                self._model = SentenceTransformer(
                    self._model_name,
                    device=self.device,
                    cache_folder=str(self.cache_dir) if self.cache_dir else None,
                    revision=self.revision,
                    trust_remote_code=False,
                )
            except Exception as exc:
                raise EmbeddingUnavailable(
                    f"Embedding model {self._model_name} could not be loaded: {exc}"
                ) from exc
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> NDArray[np.float32]:
        try:
            model = self._load()
            vectors = model.encode(  # type: ignore[attr-defined]
                list(texts),
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return np.asarray(vectors, dtype=np.float32)
        except EmbeddingUnavailable:
            raise
        except Exception as exc:
            raise EmbeddingUnavailable(f"Embedding documents failed: {exc}") from exc

    def embed_query(self, text: str) -> NDArray[np.float32]:
        return np.asarray(
            self.embed_documents([f"{self.query_instruction}{text}"])[0], dtype=np.float32
        )
