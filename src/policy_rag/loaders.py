from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar, Protocol

from bs4 import BeautifulSoup, Tag
from pypdf import PdfReader

from policy_rag.models import DocumentSection


class DocumentLoadError(RuntimeError):
    pass


class DocumentLoader(Protocol):
    def load(self, path: Path, title: str) -> list[DocumentSection]: ...


def _flush_section(
    sections: list[DocumentSection],
    heading_path: list[str],
    lines: list[str],
    page: int | None = None,
) -> None:
    text = "\n".join(line.strip() for line in lines if line.strip()).strip()
    if text:
        sections.append(DocumentSection(heading_path=heading_path.copy(), text=text, page=page))


class MarkdownLoader:
    def load(self, path: Path, title: str) -> list[DocumentSection]:
        text = path.read_text(encoding="utf-8")
        sections: list[DocumentSection] = []
        headings = [title]
        lines: list[str] = []
        in_front_matter = False
        for number, raw in enumerate(text.splitlines()):
            if number == 0 and raw.strip() == "---":
                in_front_matter = True
                continue
            if in_front_matter:
                if raw.strip() == "---":
                    in_front_matter = False
                continue
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", raw)
            if match:
                _flush_section(sections, headings, lines)
                lines = []
                level = len(match.group(1))
                headings = headings[:level]
                while len(headings) < level:
                    headings.append(title)
                headings.append(match.group(2).strip())
            else:
                lines.append(raw)
        _flush_section(sections, headings, lines)
        return sections


class HtmlLoader:
    content_tags: ClassVar[set[str]] = {"p", "li", "blockquote", "td", "th"}

    def load(self, path: Path, title: str) -> list[DocumentSection]:
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer"]):
            tag.decompose()
        sections: list[DocumentSection] = []
        headings = [title]
        lines: list[str] = []
        for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", *self.content_tags]):
            if not isinstance(node, Tag):
                continue
            text = node.get_text(" ", strip=True)
            if not text:
                continue
            if node.name and node.name.startswith("h"):
                _flush_section(sections, headings, lines)
                lines = []
                level = int(node.name[1])
                headings = headings[:level]
                while len(headings) < level:
                    headings.append(title)
                headings.append(text)
            elif not any(
                parent.name in self.content_tags for parent in node.parents if parent != node
            ):
                lines.append(text)
        _flush_section(sections, headings, lines)
        return sections


class PdfLoader:
    def load(self, path: Path, title: str) -> list[DocumentSection]:
        try:
            reader = PdfReader(path)
            return [
                DocumentSection(
                    heading_path=[title, f"PDF 第 {page_number} 页"],
                    text=page.extract_text().strip(),
                    page=page_number,
                )
                for page_number, page in enumerate(reader.pages, start=1)
                if page.extract_text().strip()
            ]
        except Exception as exc:  # pypdf raises several parser-specific exceptions
            raise DocumentLoadError(f"Failed to load PDF {path}: {exc}") from exc


class LoaderRegistry:
    def __init__(self) -> None:
        self._loaders: dict[str, DocumentLoader] = {
            ".md": MarkdownLoader(),
            ".markdown": MarkdownLoader(),
            ".html": HtmlLoader(),
            ".htm": HtmlLoader(),
            ".pdf": PdfLoader(),
        }

    @property
    def supported_extensions(self) -> Iterable[str]:
        return self._loaders.keys()

    def load(self, path: Path, title: str) -> list[DocumentSection]:
        loader = self._loaders.get(path.suffix.lower())
        if loader is None:
            raise DocumentLoadError(
                f"Unsupported document format {path.suffix}; expected one of "
                f"{sorted(self.supported_extensions)}"
            )
        sections = loader.load(path, title)
        if not sections:
            raise DocumentLoadError(f"No usable text found in {path}")
        return sections
