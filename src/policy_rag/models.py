from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RetrievalMode(StrEnum):
    BM25 = "bm25"
    DENSE = "dense"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    title: str
    source_url: str
    source_type: str
    platform: str
    product_categories: list[str]
    models: list[str] = Field(default_factory=list)
    version: str
    effective_from: date | None = None
    effective_to: date | None = None
    retrieved_at: datetime
    content_sha256: str
    source_content_sha256: str | None = None
    redistribution_status: str
    license_note: str
    synthetic: bool = False
    annotation_note: str
    validity_basis: str = "unknown"
    supporting_sources: list[dict[str, str]] = Field(default_factory=list)
    section_sources: dict[str, str] = Field(default_factory=dict)
    policy_family: str | None = None


class SourceDocument(BaseModel):
    metadata: DocumentMetadata
    local_path: str
    sections: list[DocumentSection]


class DocumentSection(BaseModel):
    heading_path: list[str]
    text: str
    page: int | None = None


class PolicyChunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    section_path: list[str]
    ordinal: int
    page: int | None = None
    strategy: str
    content_sha256: str
    metadata: DocumentMetadata


class PolicyFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=128)

    platform: str | None = None
    product_category: str | None = None
    version: str | None = None
    as_of_date: date | None = None


class CustomerContext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=128)

    platform: str | None = None
    product_category: str | None = None
    model: str | None = None
    purchase_date: date | None = None
    receipt_date: date | None = None
    opened: bool | None = None
    activated: bool | None = None
    used: bool | None = None
    request_type: str | None = None
    as_of_date: date | None = None


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=1000)
    mode: RetrievalMode = RetrievalMode.HYBRID_RERANK
    top_k: int = Field(default=5, ge=1, le=20)
    filters: PolicyFilter = Field(default_factory=PolicyFilter)
    context: CustomerContext = Field(default_factory=CustomerContext)
    generate: bool = True

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("question must contain at least two non-whitespace characters")
        return normalized

    @model_validator(mode="after")
    def validate_context_consistency(self) -> QueryRequest:
        for name in ("platform", "product_category", "as_of_date"):
            explicit = getattr(self.filters, name)
            contextual = getattr(self.context, name)
            if explicit is not None and contextual is not None and explicit != contextual:
                raise ValueError(f"Conflicting filters and customer context: {name}")
        if (
            self.context.purchase_date
            and self.context.receipt_date
            and self.context.receipt_date < self.context.purchase_date
        ):
            raise ValueError("Receipt date cannot be earlier than purchase date")
        return self


class ScoreBreakdown(BaseModel):
    bm25: float | None = None
    dense: float | None = None
    rrf: float | None = None
    rerank: float | None = None
    evidence: float = 0.0


class RetrievedCandidate(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    text: str
    section_path: list[str]
    platform: str
    product_categories: list[str]
    version: str
    effective_from: date | None = None
    effective_to: date | None = None
    source_url: str
    additional_source_urls: list[str] = Field(default_factory=list)
    policy_family: str | None = None
    synthetic: bool = False
    initial_rank: int
    final_rank: int
    scores: ScoreBreakdown


class Citation(BaseModel):
    citation_id: str
    chunk_id: str
    doc_id: str
    document: str
    section: str
    version: str
    effective_from: date | None = None
    effective_to: date | None = None
    source_url: str
    additional_source_urls: list[str] = Field(default_factory=list)
    synthetic: bool = False


class AnswerContent(BaseModel):
    policy_explanation: str
    applicable_conditions: list[str]
    inapplicable_conditions: list[str]
    missing_information: list[str]
    citations: list[Citation]
    refused: bool
    refusal_reason: str | None = None
    generator: str


class QueryResponse(BaseModel):
    request_id: str
    requested_mode: RetrievalMode
    effective_mode: RetrievalMode
    degraded: bool
    degradation_reasons: list[str]
    index_version: str
    retrieval_ms: float
    generation_ms: float
    candidates: list[RetrievedCandidate]
    answer: AnswerContent | None = None


class IndexManifest(BaseModel):
    schema_version: str = "1"
    index_version: str
    strategy: str
    chunk_size: int = 520
    chunk_overlap: int = 80
    collection_name: str
    data_directory: str
    qdrant_backend: str = "local"
    embedding_model: str
    reranker_model: str
    embedding_revision: str
    reranker_revision: str
    vector_dimension: int
    source_manifest_sha256: str
    document_hashes: dict[str, str]
    document_count: int
    chunk_count: int
    created_at: datetime
    index_seconds: float
    peak_rss_mb: float
    index_size_bytes: int
    chunk_hashes_sha256: str = ""
    bm25_sha256: str = ""


class EvalCase(BaseModel):
    id: str
    query: str
    category: str
    answerable: bool
    filters: PolicyFilter = Field(default_factory=PolicyFilter)
    relevant_doc_ids: list[str] = Field(default_factory=list)
    relevance_grades: dict[str, int] = Field(default_factory=dict)
    relevant_sections: dict[str, list[str]] = Field(default_factory=dict)
    expected_facts: list[str] = Field(default_factory=list)
    case_source: str
    annotation_source: str
    notes: str = ""


class HealthResponse(BaseModel):
    status: str
    index_ready: bool
    index_version: str | None
    embedding_model: str
    reranker_model: str
    qdrant_backend: str
    details: dict[str, Any] = Field(default_factory=dict)
