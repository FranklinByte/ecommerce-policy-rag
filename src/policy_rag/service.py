from __future__ import annotations

import threading
import time
import uuid

from policy_rag.config import Settings
from policy_rag.generation import (
    AnswerGenerator,
    ExtractiveAnswerGenerator,
    GenerationUnavailable,
    build_generator,
    refusal_answer,
)
from policy_rag.models import (
    PolicyFilter,
    QueryRequest,
    QueryResponse,
    RetrievalMode,
    RetrievedCandidate,
)
from policy_rag.retrieval.service import RetrievalService


def effective_filter(request: QueryRequest) -> PolicyFilter:
    return PolicyFilter(
        platform=request.filters.platform or request.context.platform,
        product_category=request.filters.product_category or request.context.product_category,
        version=request.filters.version,
        as_of_date=request.filters.as_of_date or request.context.as_of_date,
    )


class PolicyRAGService:
    def __init__(
        self,
        settings: Settings,
        retrieval: RetrievalService | None = None,
        generator: AnswerGenerator | None = None,
    ) -> None:
        self.settings = settings
        self.retrieval = retrieval or RetrievalService(settings)
        self.generator = generator or build_generator(settings)
        self.fallback_generator = ExtractiveAnswerGenerator()
        self.lock = threading.Lock()

    def close(self) -> None:
        self.retrieval.close()

    def query(self, request: QueryRequest) -> QueryResponse:
        if not self.lock.acquire(blocking=False):
            raise ServiceBusy("A model request is still running")
        try:
            return self._query(request)
        finally:
            self.lock.release()

    def _query(self, request: QueryRequest) -> QueryResponse:
        filters = effective_filter(request)
        context = request.context.model_copy(
            update={
                "platform": filters.platform,
                "product_category": filters.product_category,
                "as_of_date": filters.as_of_date,
            }
        )
        retrieval_started = time.perf_counter()
        retrieval_query = " ".join(
            value
            for value in [request.question, request.context.model, request.context.request_type]
            if value
        )
        result = self.retrieval.retrieve(
            retrieval_query,
            filters,
            request.mode,
            request.top_k,
        )
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        generation_started = time.perf_counter()
        answer = None
        degradation_reasons = result.degradation_reasons.copy()
        degraded = result.degraded
        evidence = [
            candidate
            for candidate in result.candidates
            if has_evidence([candidate], result.effective_mode, self.settings)
        ]
        if request.generate:
            if not result.candidates:
                answer = refusal_answer("没有检索到满足元数据条件的政策证据。", context)
            elif not evidence:
                answer = refusal_answer("最高相关证据低于配置阈值，需补充信息或人工确认。", context)
            elif conflicting_versions(evidence):
                answer = refusal_answer(
                    "检索到同一政策系列的多个版本，请明确版本或提供可核实的适用日期。",
                    context,
                )
            else:
                try:
                    answer = self.generator.generate(request.question, context, evidence)
                except GenerationUnavailable as exc:
                    degraded = True
                    degradation_reasons.append(str(exc))
                    degradation_reasons.append("已回退到本地抽取式答案生成。")
                    answer = self.fallback_generator.generate(request.question, context, evidence)
        generation_ms = (time.perf_counter() - generation_started) * 1000
        return QueryResponse(
            request_id=str(uuid.uuid4()),
            requested_mode=result.requested_mode,
            effective_mode=result.effective_mode,
            degraded=degraded,
            degradation_reasons=degradation_reasons,
            index_version=result.index_version,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            candidates=result.candidates,
            answer=answer,
        )


class ServiceBusy(RuntimeError):
    pass


def conflicting_versions(candidates: list[RetrievedCandidate]) -> bool:
    families: dict[str, set[str]] = {}
    for candidate in candidates:
        if candidate.policy_family:
            families.setdefault(candidate.policy_family, set()).add(candidate.version)
    return any(len(versions) > 1 for versions in families.values())


def has_evidence(
    candidates: list[RetrievedCandidate], mode: RetrievalMode, settings: Settings
) -> bool:
    if not candidates:
        return False
    scores = candidates[0].scores
    if mode == RetrievalMode.BM25:
        return bool(scores.evidence >= settings.sparse_threshold)
    if mode == RetrievalMode.DENSE:
        return bool((scores.dense or 0) >= settings.dense_threshold)
    if mode == RetrievalMode.HYBRID_RERANK:
        return bool((scores.rerank or 0) >= settings.evidence_threshold)
    return bool((scores.dense or 0) >= settings.dense_threshold and scores.evidence >= 0.5)
