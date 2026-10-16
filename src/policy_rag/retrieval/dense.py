from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, SecretStr
from qdrant_client import QdrantClient, models

from policy_rag.models import PolicyChunk, PolicyFilter


class DenseHit(BaseModel):
    chunk_id: str
    score: float
    rank: int


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"policy-rag:{chunk_id}"))


def _date_ordinal(value: date | None, *, upper: bool = False) -> int:
    if value is None:
        return date.max.toordinal() if upper else date.min.toordinal()
    return value.toordinal()


class DenseVectorStore:
    def __init__(
        self,
        collection_name: str,
        local_path: Path,
        url: str | None = None,
        api_key: SecretStr | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.local_path = local_path
        self.url = url
        if url:
            self.client = QdrantClient(
                url=url,
                api_key=api_key.get_secret_value() if api_key else None,
                timeout=30,
            )
        else:
            local_path.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(local_path))

    @property
    def backend_name(self) -> str:
        return self.url or f"local:{self.local_path}"

    def close(self) -> None:
        self.client.close()

    def build(
        self, chunks: Sequence[PolicyChunk], vectors: NDArray[np.float32], dimension: int
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and vector counts do not match")
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
        )
        batch: list[models.PointStruct] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            batch.append(
                models.PointStruct(
                    id=_point_id(chunk.chunk_id),
                    vector=vector.tolist(),
                    payload=self._payload(chunk),
                )
            )
            if len(batch) >= 64:
                self.client.upsert(self.collection_name, batch, wait=True)
                batch = []
        if batch:
            self.client.upsert(self.collection_name, batch, wait=True)

    def search(
        self, vector: NDArray[np.float32], policy_filter: PolicyFilter, limit: int
    ) -> list[DenseHit]:
        query_filter = self._query_filter(policy_filter)
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector.tolist(),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [
            DenseHit(
                chunk_id=str((point.payload or {})["chunk_id"]),
                score=float(point.score),
                rank=rank,
            )
            for rank, point in enumerate(response.points, start=1)
        ]

    @staticmethod
    def _payload(chunk: PolicyChunk) -> dict[str, Any]:
        metadata = chunk.metadata
        return {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "platform": metadata.platform,
            "product_categories": metadata.product_categories,
            "version": metadata.version,
            "synthetic": metadata.synthetic,
            "validity_known": metadata.effective_from is not None,
            "effective_from_ord": _date_ordinal(metadata.effective_from),
            "effective_to_ord": _date_ordinal(metadata.effective_to, upper=True),
        }

    @staticmethod
    def _query_filter(policy_filter: PolicyFilter) -> models.Filter | None:
        conditions: list[models.Condition] = []
        if policy_filter.platform != "starmall":
            conditions.append(
                models.FieldCondition(key="synthetic", match=models.MatchValue(value=False))
            )
        if policy_filter.platform:
            conditions.append(
                models.FieldCondition(
                    key="platform", match=models.MatchValue(value=policy_filter.platform)
                )
            )
        if policy_filter.product_category:
            conditions.append(
                models.FieldCondition(
                    key="product_categories",
                    match=models.MatchValue(value=policy_filter.product_category),
                )
            )
        if policy_filter.version:
            conditions.append(
                models.FieldCondition(
                    key="version", match=models.MatchValue(value=policy_filter.version)
                )
            )
        if policy_filter.as_of_date:
            conditions.append(
                models.FieldCondition(key="validity_known", match=models.MatchValue(value=True))
            )
            ordinal = float(policy_filter.as_of_date.toordinal())
            conditions.extend(
                [
                    models.FieldCondition(
                        key="effective_from_ord", range=models.Range(lte=ordinal)
                    ),
                    models.FieldCondition(key="effective_to_ord", range=models.Range(gte=ordinal)),
                ]
            )
        return models.Filter(must=conditions) if conditions else None
