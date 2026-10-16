from __future__ import annotations

import re
from collections.abc import Iterable

import jieba

jieba.setLogLevel(20)

ALPHANUMERIC = re.compile(r"[a-zA-Z][a-zA-Z0-9+._/-]*|\d+(?:\.\d+)?(?:天|日|年|个月|小时|%)?")
CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
PUNCT_ONLY = re.compile(r"^\W+$", re.UNICODE)

STOPWORDS = {
    "的",
    "了",
    "和",
    "是",
    "在",
    "我",
    "能",
    "可以",
    "是否",
    "请问",
    "一下",
    "什么",
    "怎么",
    "如果",
    "需要",
}


class ChineseTokenizer:
    """Jieba terms plus identifier tokens and CJK bigrams for colloquial matching."""

    def tokenize(self, text: str) -> list[str]:
        lowered = text.lower().strip()
        tokens = [
            token.strip()
            for token in jieba.lcut(lowered, cut_all=False)
            if token.strip() and token.strip() not in STOPWORDS and not PUNCT_ONLY.match(token)
        ]
        tokens.extend(f"id:{value}" for value in ALPHANUMERIC.findall(lowered))
        tokens.extend(self._cjk_bigrams(lowered))
        return tokens

    @staticmethod
    def _cjk_bigrams(text: str) -> Iterable[str]:
        for run in CJK_RUN.findall(text):
            if len(run) == 1:
                yield f"zh:{run}"
            else:
                yield from (f"zh:{run[index : index + 2]}" for index in range(len(run) - 1))
