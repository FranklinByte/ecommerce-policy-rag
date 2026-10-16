from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from policy_rag.models import PolicyChunk, PolicyFilter
from policy_rag.retrieval.tokenizer import ChineseTokenizer


def chunk_matches_filter(chunk: PolicyChunk, policy_filter: PolicyFilter) -> bool:
    metadata = chunk.metadata
    if metadata.synthetic and policy_filter.platform != metadata.platform:
        return False
    if policy_filter.platform and metadata.platform != policy_filter.platform:
        return False
    if (
        policy_filter.product_category
        and policy_filter.product_category not in metadata.product_categories
    ):
        return False
    if policy_filter.version and metadata.version != policy_filter.version:
        return False
    if policy_filter.as_of_date:
        if metadata.effective_from is None or metadata.effective_from > policy_filter.as_of_date:
            return False
        if metadata.effective_to and metadata.effective_to < policy_filter.as_of_date:
            return False
    return True


class SparseHit(BaseModel):
    chunk_id: str
    score: float
    rank: int


class BM25Index:
    def __init__(
        self,
        chunks: list[PolicyChunk],
        tokenized_documents: dict[str, list[str]] | None = None,
        *,
        k1: float = 1.5,
        b: float = 0.75,
        tokenizer: ChineseTokenizer | None = None,
    ) -> None:
        self.chunks = chunks
        self.chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self.k1 = k1
        self.b = b
        self.tokenizer = tokenizer or ChineseTokenizer()
        self.tokenized_documents = tokenized_documents or {
            chunk.chunk_id: self.tokenizer.tokenize(chunk.text) for chunk in chunks
        }

    def search(self, query: str, policy_filter: PolicyFilter, limit: int) -> list[SparseHit]:
        eligible = [chunk for chunk in self.chunks if chunk_matches_filter(chunk, policy_filter)]
        if not eligible:
            return []
        query_terms = self.tokenizer.tokenize(query)
        if not query_terms:
            return []
        lengths = [len(self.tokenized_documents[chunk.chunk_id]) for chunk in eligible]
        average_length = sum(lengths) / len(lengths) if lengths else 1.0
        document_frequency: Counter[str] = Counter()
        for chunk in eligible:
            document_frequency.update(set(self.tokenized_documents[chunk.chunk_id]))
        number_of_documents = len(eligible)
        scores: list[tuple[str, float]] = []
        for chunk in eligible:
            document_tokens = self.tokenized_documents[chunk.chunk_id]
            frequencies = Counter(document_tokens)
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if frequency == 0:
                    continue
                df = document_frequency[term]
                inverse_document_frequency = math.log(
                    1.0 + (number_of_documents - df + 0.5) / (df + 0.5)
                )
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * len(document_tokens) / max(average_length, 1.0)
                )
                score += inverse_document_frequency * (frequency * (self.k1 + 1.0) / denominator)
            if score > 0:
                scores.append((chunk.chunk_id, score))
        scores.sort(key=lambda item: (-item[1], item[0]))
        return [
            SparseHit(chunk_id=chunk_id, score=score, rank=index)
            for index, (chunk_id, score) in enumerate(scores[:limit], start=1)
        ]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1",
            "k1": self.k1,
            "b": self.b,
            "tokenized_documents": self.tokenized_documents,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, chunks: list[PolicyChunk]) -> BM25Index:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "1":
            raise ValueError("Unsupported BM25 index schema")
        return cls(
            chunks,
            tokenized_documents=payload["tokenized_documents"],
            k1=float(payload["k1"]),
            b=float(payload["b"]),
        )
