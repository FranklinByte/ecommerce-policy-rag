from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from policy_rag.models import DocumentSection, PolicyChunk, SourceDocument

SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？；!?;])\s*|(?<=\.)\s+|\n+")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _window_ranges(text: str, size: int, overlap: int) -> Iterable[tuple[int, int]]:
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            boundary = max(text.rfind(mark, start + size // 2, end) for mark in "。！？；\n")
            if boundary > start:
                end = boundary + 1
        if text[start:end].strip():
            yield start, end
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)


def _window_text(text: str, size: int, overlap: int) -> Iterable[str]:
    for start, end in _window_ranges(text, size, overlap):
        yield text[start:end].strip()


def _sentence_groups(text: str, size: int, overlap: int) -> Iterable[str]:
    sentences = [item.strip() for item in SENTENCE_BOUNDARY.split(text) if item.strip()]
    buffer = ""
    for sentence in sentences:
        if len(sentence) > size:
            if buffer:
                yield buffer
                buffer = ""
            yield from _window_text(sentence, size, overlap)
            continue
        candidate = f"{buffer}{sentence}" if buffer else sentence
        if len(candidate) <= size:
            buffer = candidate
            continue
        yield buffer
        retain_size = min(overlap, max(0, size - len(sentence)))
        retained = buffer[-retain_size:] if retain_size else ""
        buffer = f"{retained}{sentence}"
    if buffer:
        yield buffer


class PolicyChunker:
    def __init__(self, strategy: str, chunk_size: int, chunk_overlap: int) -> None:
        if strategy not in {"structure", "sliding"}:
            raise ValueError(f"Unknown chunk strategy: {strategy}")
        if chunk_size < 80 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("Invalid chunk size or overlap")
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, document: SourceDocument) -> list[PolicyChunk]:
        if self.strategy == "structure":
            pieces = self._structure_pieces(document.sections)
        else:
            pieces = self._sliding_pieces(document.sections)
        chunks: list[PolicyChunk] = []
        for ordinal, (section_path, page, text) in enumerate(pieces):
            identity = "|".join(
                [
                    document.metadata.doc_id,
                    document.metadata.version,
                    self.strategy,
                    "/".join(section_path),
                    str(ordinal),
                    text,
                ]
            )
            chunks.append(
                PolicyChunk(
                    chunk_id=f"chk_{_sha256(identity)[:20]}",
                    doc_id=document.metadata.doc_id,
                    text=text,
                    section_path=section_path,
                    ordinal=ordinal,
                    page=page,
                    strategy=self.strategy,
                    content_sha256=_sha256(text),
                    metadata=document.metadata,
                )
            )
        return chunks

    def _structure_pieces(
        self, sections: list[DocumentSection]
    ) -> Iterable[tuple[list[str], int | None, str]]:
        for section in sections:
            label = " > ".join(section.heading_path)
            prefix = f"条款路径：{label[: self.chunk_size // 3]}\n"
            available = self.chunk_size - len(prefix)
            for text in _sentence_groups(
                section.text, available, min(self.chunk_overlap, available - 1)
            ):
                yield section.heading_path, section.page, f"{prefix}{text}"

    def _sliding_pieces(
        self, sections: list[DocumentSection]
    ) -> Iterable[tuple[list[str], int | None, str]]:
        parts: list[str] = []
        spans: list[tuple[int, int, DocumentSection]] = []
        offset = 0
        for section in sections:
            part = f"## {' > '.join(section.heading_path)}\n{section.text}\n\n"
            parts.append(part)
            spans.append((offset, offset + len(part), section))
            offset += len(part)
        flattened = "".join(parts).rstrip()
        for start, end in _window_ranges(flattened, self.chunk_size, self.chunk_overlap):
            covered = [section for left, right, section in spans if left < end and right > start]
            paths = list(dict.fromkeys(" > ".join(section.heading_path) for section in covered))
            yield paths, covered[0].page, flattened[start:end].strip()
