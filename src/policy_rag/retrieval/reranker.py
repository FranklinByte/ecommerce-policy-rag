from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np


class RerankerUnavailable(RuntimeError):
    pass


class Reranker(Protocol):
    @property
    def model_name(self) -> str: ...

    def score(self, query: str, documents: Sequence[str]) -> list[float]: ...


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        batch_size: int = 16,
        cache_dir: Path | None = None,
        revision: str = "2cfc18c9415c912f9d8155881c133215df768a70",
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
                from sentence_transformers import CrossEncoder

                torch.set_num_threads(self.threads)

                self._model = CrossEncoder(
                    self._model_name,
                    device=self.device,
                    max_length=512,
                    trust_remote_code=False,
                    revision=self.revision,
                    cache_folder=str(self.cache_dir) if self.cache_dir else None,
                    activation_fn=torch.nn.Identity(),
                )
            except Exception as exc:
                raise RerankerUnavailable(
                    f"Reranker model {self._model_name} could not be loaded: {exc}"
                ) from exc
        return self._model

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        try:
            model = self._load()
            raw_scores = np.asarray(
                model.predict(  # type: ignore[attr-defined]
                    [(query, document) for document in documents],
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                )
            ).reshape(-1)
            return [1.0 / (1.0 + math.exp(-float(np.clip(score, -40, 40)))) for score in raw_scores]
        except RerankerUnavailable:
            raise
        except Exception as exc:
            raise RerankerUnavailable(f"Reranking failed: {exc}") from exc
