from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from policy_rag.config import Settings
from policy_rag.models import (
    AnswerContent,
    Citation,
    CustomerContext,
    RetrievedCandidate,
)

SENTENCE_SPLIT = re.compile(r"(?<=[。！？；!?;])\s*|(?<=\.)\s+")
CITATION = re.compile(r"\[C\d+\]")


def _sentences_have_citations(text: str) -> bool:
    """Check citation placement, not whether evidence semantically supports a claim."""
    # Accept both "claim [C1]." and "claim.[C1]". Attach citations following
    # punctuation to that sentence before splitting; never borrow the next line's.
    boundary = r"[。！？；!?;]|(?<!\d)\.(?!\d)"
    normalized = re.sub(rf"({boundary})([ \t]*(?:\[C\d+\][ \t]*)+)", r"\2\1", text)
    statements = [
        part.strip() for part in re.split(rf"(?:{boundary})|\n+", normalized) if part.strip()
    ]
    return bool(statements) and all(
        bool(CITATION.sub("", statement).strip())
        and bool(re.search(r"(?:\[C\d+\]\s*)+[\"'”’）)]*\s*$", statement))
        for statement in statements
    )


class GenerationUnavailable(RuntimeError):
    pass


class ProviderAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    policy_explanation: str = Field(min_length=1, max_length=8000)
    applicable_conditions: list[str] = Field(max_length=10)
    inapplicable_conditions: list[str] = Field(max_length=10)
    missing_information: list[str] = Field(max_length=12)
    used_citation_ids: list[str] = Field(min_length=1, max_length=5)


class AnswerGenerator(Protocol):
    @property
    def name(self) -> str: ...

    def generate(
        self,
        question: str,
        context: CustomerContext,
        candidates: Sequence[RetrievedCandidate],
    ) -> AnswerContent: ...


def _citation(candidate: RetrievedCandidate, number: int) -> Citation:
    return Citation(
        citation_id=f"C{number}",
        chunk_id=candidate.chunk_id,
        doc_id=candidate.doc_id,
        document=candidate.title,
        section=" > ".join(candidate.section_path),
        version=candidate.version,
        effective_from=candidate.effective_from,
        effective_to=candidate.effective_to,
        source_url=candidate.source_url,
        additional_source_urls=candidate.additional_source_urls,
        synthetic=candidate.synthetic,
    )


def _sentences(candidate: RetrievedCandidate) -> list[str]:
    body = "\n".join(
        line for line in candidate.text.splitlines() if not line.startswith(("条款路径：", "#"))
    )
    return [part.strip() for part in SENTENCE_SPLIT.split(body) if len(part.strip()) >= 8]


class ExtractiveAnswerGenerator:
    @property
    def name(self) -> str:
        return "extractive-v1"

    def generate(
        self,
        question: str,
        context: CustomerContext,
        candidates: Sequence[RetrievedCandidate],
    ) -> AnswerContent:
        del question
        used = [candidate for candidate in candidates if _sentences(candidate)][:3]
        if not used:
            return refusal_answer("候选片段没有可引用的完整政策文本，请人工确认。", context)
        citations = [_citation(candidate, number) for number, candidate in enumerate(used, start=1)]
        evidence_lines: list[str] = []
        applicable: list[str] = []
        inapplicable: list[str] = []
        for number, candidate in enumerate(used, start=1):
            candidate_sentences = _sentences(candidate)
            if candidate_sentences:
                evidence_lines.append(f"{' '.join(candidate_sentences)} [C{number}]")
            for sentence in candidate_sentences:
                if any(
                    key in sentence
                    for key in (
                        "不适用",
                        "不属于",
                        "不予",
                        "不能",
                        "排除",
                        "不支持",
                        "超期",
                        "无维保",
                    )
                ):
                    inapplicable.append(f"{sentence} [C{number}]")
                elif any(
                    key in sentence for key in ("适用", "以内", "内，", "应", "须", "凭证", "保修")
                ):
                    applicable.append(f"{sentence} [C{number}]")
        missing = _missing_information(context)
        if any(item.effective_from is None for item in used):
            missing.append("来源未公布确定的生效日期，当前适用性须向实际销售方确认")
        return AnswerContent(
            policy_explanation="\n".join(evidence_lines),
            applicable_conditions=_deduplicate(applicable)[:5],
            inapplicable_conditions=_deduplicate(inapplicable)[:5],
            missing_information=missing,
            citations=citations,
            refused=False,
            generator=self.name,
        )


def refusal_answer(reason: str, context: CustomerContext) -> AnswerContent:
    return AnswerContent(
        policy_explanation="现有证据不足，无法可靠判断该售后请求。",
        applicable_conditions=[],
        inapplicable_conditions=[],
        missing_information=_missing_information(context),
        citations=[],
        refused=True,
        refusal_reason=reason,
        generator="refusal-policy-v1",
    )


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _missing_information(context: CustomerContext) -> list[str]:
    missing: list[str] = []
    if not context.platform:
        missing.append("实际购买平台或销售渠道")
    if not context.product_category:
        missing.append("商品类别与具体型号")
    elif not context.model:
        missing.append("具体型号")
    if not context.receipt_date and not context.purchase_date:
        missing.append("购买日期或签收日期")
    if context.opened is None:
        missing.append("是否拆封及包装、配件是否完整")
    if context.activated is None:
        missing.append("是否激活")
    if context.used is None:
        missing.append("是否使用、是否存在人为损坏")
    if not context.request_type:
        missing.append("诉求类型：退款、换货或维修")
    if not context.as_of_date:
        missing.append("查询所依据的日期")
    return missing


class OpenAICompatibleAnswerGenerator:
    def __init__(self, settings: Settings) -> None:
        if not settings.llm_base_url or not settings.llm_model or not settings.llm_api_key:
            raise ValueError("LLM provider configuration is incomplete")
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_model
        self.api_key = settings.llm_api_key.get_secret_value()
        self.timeout = settings.llm_timeout_seconds

    @property
    def name(self) -> str:
        return f"openai-compatible:{self.model}"

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=0.25, min=0.25, max=2),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    def generate(
        self,
        question: str,
        context: CustomerContext,
        candidates: Sequence[RetrievedCandidate],
    ) -> AnswerContent:
        evidence = [
            {
                "citation_id": f"C{number}",
                "chunk_id": candidate.chunk_id,
                "document": candidate.title,
                "section": " > ".join(candidate.section_path),
                "text": candidate.text,
            }
            for number, candidate in enumerate(candidates[:5], start=1)
        ]
        prompt = {
            "question": question,
            "customer_context": context.model_dump(mode="json"),
            "evidence": evidence,
            "rules": [
                "Only use supplied evidence.",
                "Every factual statement must end with one or more [C<n>] citations.",
                "Do not make a legal ruling or promise a refund.",
                "Return JSON with policy_explanation, applicable_conditions, "
                "inapplicable_conditions, missing_information, used_citation_ids.",
            ],
        }
        try:
            data = self._request(
                {
                    "model": self.model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是电商售后政策客服辅助，只能根据给定证据回答。",
                        },
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                }
            )
            raw = data["choices"][0]["message"]["content"]
            parsed = ProviderAnswer.model_validate_json(raw)
            allowed = {f"C{number}" for number in range(1, min(len(candidates), 5) + 1)}
            used_ids = list(dict.fromkeys(parsed.used_citation_ids))
            statements = [
                parsed.policy_explanation,
                *parsed.applicable_conditions,
                *parsed.inapplicable_conditions,
            ]
            inline_ids = set(re.findall(r"\[(C\d+)\]", " ".join(statements)))
            if not set(used_ids) <= allowed or inline_ids != set(used_ids):
                raise ValueError("Provider citation IDs are inconsistent with supplied evidence")
            if any(not _sentences_have_citations(statement) for statement in statements):
                raise ValueError("Provider returned an uncited statement")
            citation_map = {
                f"C{number}": _citation(candidate, number)
                for number, candidate in enumerate(candidates[:5], start=1)
            }
            return AnswerContent(
                policy_explanation=parsed.policy_explanation,
                applicable_conditions=parsed.applicable_conditions,
                inapplicable_conditions=parsed.inapplicable_conditions,
                missing_information=parsed.missing_information,
                citations=[citation_map[item] for item in used_ids],
                refused=False,
                generator=self.name,
            )
        except Exception as exc:
            raise GenerationUnavailable(
                f"Configured generation provider failed: {type(exc).__name__}"
            ) from exc


def build_generator(settings: Settings) -> AnswerGenerator:
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleAnswerGenerator(settings)
    return ExtractiveAnswerGenerator()
