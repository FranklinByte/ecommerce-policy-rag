import json
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from policy_rag.api import create_app
from policy_rag.generation import (
    ExtractiveAnswerGenerator,
    GenerationUnavailable,
    OpenAICompatibleAnswerGenerator,
    _sentences_have_citations,
    build_generator,
)
from policy_rag.models import CustomerContext, PolicyFilter, QueryRequest, RetrievalMode
from policy_rag.service import PolicyRAGService, ServiceBusy, effective_filter


def test_answer_citations_and_unknown_effective_date(retrieval, settings):
    service = PolicyRAGService(settings, retrieval)
    response = service.query(
        QueryRequest(question="AM115 有线耳机保修", filters=PolicyFilter(platform="huawei_cn"))
    )
    assert not response.answer.refused
    assert response.answer.citations
    assert "C1" in response.answer.policy_explanation
    assert response.answer.generator == "extractive-v1"
    assert any("生效日期" in item for item in response.answer.missing_information)
    assert all(
        citation.chunk_id in {candidate.chunk_id for candidate in response.candidates}
        for citation in response.answer.citations
    )


@pytest.mark.parametrize(
    "query,platform", [("不存在的退款条件", "missing"), ("天文学量子物理", "huawei_cn")]
)
def test_no_evidence_refusal(retrieval, settings, query, platform):
    response = PolicyRAGService(settings, retrieval).query(
        QueryRequest(question=query, filters=PolicyFilter(platform=platform))
    )
    assert response.answer.refused and response.answer.citations == []


def test_generate_false_context_merge_and_busy(retrieval, settings):
    service = PolicyRAGService(settings, retrieval)
    request = QueryRequest(
        question="AM115", generate=False, context=CustomerContext(platform="huawei_cn")
    )
    assert effective_filter(request).platform == "huawei_cn"
    assert service.query(request).answer is None
    service.lock.acquire()
    try:
        with pytest.raises(ServiceBusy):
            service.query(request)
    finally:
        service.lock.release()


def test_provider_error_falls_back(retrieval, settings):
    class BrokenGenerator:
        name = "broken"

        def generate(self, *_):
            raise GenerationUnavailable("offline")

    response = PolicyRAGService(settings, retrieval, BrokenGenerator()).query(
        QueryRequest(question="AM115", filters=PolicyFilter(platform="huawei_cn"))
    )
    assert response.degraded and response.answer.generator == "extractive-v1"


def test_provider_success_retry_and_invalid_citations(settings, retrieval, respx_mock):
    configured = settings.model_copy(
        update={
            "llm_provider": "openai_compatible",
            "llm_base_url": "https://provider.example/v1",
            "llm_model": "test",
        }
    )
    from pydantic import SecretStr

    configured.llm_api_key = SecretStr("top-secret")
    generator = build_generator(configured)
    candidates = retrieval.retrieve("AM115", PolicyFilter(), RetrievalMode.BM25, 5).candidates
    route = respx_mock.post("https://provider.example/v1/chat/completions")
    answer = {
        "policy_explanation": "仅按证据说明。[C1]",
        "applicable_conditions": ["条件 [C1]"],
        "inapplicable_conditions": [],
        "missing_information": [],
        "used_citation_ids": ["C1"],
    }
    route.side_effect = [
        httpx.ConnectError("offline"),
        httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]}),
    ]
    result = generator.generate("question", CustomerContext(), candidates)
    assert result.generator.endswith(":test") and route.call_count == 2
    for invalid in [
        answer | {"used_citation_ids": ["C999"]},
        answer | {"policy_explanation": "No citation"},
        answer | {"policy_explanation": "有凭证可申请维修。[C1] 所有商品都可永久无条件退款。"},
        answer | {"policy_explanation": "没有引用的第一句。第二句带引用。[C1]"},
        answer | {"applicable_conditions": ["有引用的条件 [C1]。还有一个无引用条件。"]},
        answer | {"applicable_conditions": "not-a-list"},
    ]:
        route.side_effect = None
        route.return_value = httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(invalid)}}]}
        )
        with pytest.raises(GenerationUnavailable) as error:
            generator.generate("question", CustomerContext(), candidates)
        assert "top-secret" not in str(error.value)
    with pytest.raises(ValueError):
        OpenAICompatibleAnswerGenerator(settings)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("政策说明。[C1] 第二条说明。[C2]", True),
        ("政策说明[C1]。第二条说明 [C2]。", True),
        ("Valid claim. [C1] Another claim [C2].", True),
        ("周期是 1.5 天 [C1]。", True),
        ("条件甲[C1]；条件乙[C2]。", True),
        ("条件甲。[C1]\n条件乙。[C2]", True),
        ("条件甲。[C1] 条件乙没有来源。", False),
        ("条件甲没有来源。条件乙。[C1]", False),
        ("条件甲没有来源\n条件乙[C1]", False),
        ("[C1] 没有句尾引用的条件", False),
        ("条件甲没有来源。\n[C1] 条件乙[C2]", False),
        ("[C1]", False),
        ("", False),
    ],
)
def test_citation_check_requires_each_sentence(text, expected):
    assert _sentences_have_citations(text) is expected


def test_complete_context_has_no_missing_fields(retrieval):
    from datetime import date

    context = CustomerContext(
        platform="starmall",
        product_category="phone",
        model="NEBULA-P2",
        purchase_date=date(2025, 1, 1),
        opened=True,
        activated=True,
        used=False,
        request_type="refund",
        as_of_date=date(2025, 1, 2),
    )
    candidates = retrieval.retrieve(
        "手机退货", PolicyFilter(platform="starmall", version="v2"), RetrievalMode.BM25, 5
    ).candidates
    answer = ExtractiveAnswerGenerator().generate("q", context, candidates)
    assert answer.missing_information == []


def test_api_index_missing_and_input_validation(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/assets/styles.css").status_code == 200
        assert not client.get("/health").json()["index_ready"]
        assert client.post("/api/v1/query", json={"question": "hello"}).status_code == 503
        assert client.post("/api/v1/retrieve", json={"question": "hello"}).status_code == 503
        assert client.post("/api/v1/query", json={"question": " "}).status_code == 422


def test_api_query_retrieve_timeout_and_busy(built_settings, retrieval, monkeypatch):
    import policy_rag.api as api

    service = PolicyRAGService(built_settings, retrieval)
    monkeypatch.setattr(api, "PolicyRAGService", lambda _: service)
    api_settings = built_settings.model_copy(update={"request_timeout_seconds": 5.0})
    with TestClient(create_app(api_settings)) as client:
        assert client.get("/health").json()["status"] == "ok"
        payload = {"question": "AM115", "mode": "bm25"}
        assert client.post("/api/v1/retrieve", json=payload).json()["answer"] is None
        assert client.post("/api/v1/query", json=payload).status_code == 200
        service.lock.acquire()
        try:
            assert client.post("/api/v1/query", json=payload).status_code == 429
        finally:
            service.lock.release()
        original = service._query
        release = threading.Event()

        def slow(request):
            release.wait(timeout=5)
            return original(request)

        monkeypatch.setattr(service, "_query", slow)
        api_settings.request_timeout_seconds = 0.02
        try:
            assert client.post("/api/v1/query", json=payload).status_code == 504
            assert client.post("/api/v1/query", json=payload).status_code == 429
        finally:
            release.set()


def test_context_validation_and_limits():
    from pydantic import ValidationError

    for payload in [
        {"context": {"model": "a" * 129}},
        {"context": {"platform": "a"}, "filters": {"platform": "b"}},
        {"context": {"purchase_date": "2025-02-02", "receipt_date": "2025-01-01"}},
        {"filters": {"typo": "unexpected"}},
    ]:
        with pytest.raises(ValidationError):
            QueryRequest.model_validate({"question": "test", **payload})


def test_policy_version_conflicts_and_per_candidate_evidence(retrieval, settings):
    from policy_rag.service import conflicting_versions, has_evidence

    result = retrieval.retrieve(
        "手机退货", PolicyFilter(platform="starmall"), RetrievalMode.BM25, 20
    )
    assert conflicting_versions(result.candidates)
    assert not conflicting_versions([c for c in result.candidates if c.version == "v2"])
    candidate = result.candidates[0]
    candidate.scores.evidence = 0.0
    assert not has_evidence([candidate], RetrievalMode.BM25, settings)
    response = PolicyRAGService(
        settings.model_copy(update={"sparse_threshold": 0}), retrieval
    ).query(
        QueryRequest(
            question="手机退货",
            mode=RetrievalMode.BM25,
            filters=PolicyFilter(platform="starmall"),
            top_k=20,
        )
    )
    assert response.answer.refused
    assert "版本" in response.answer.refusal_reason
