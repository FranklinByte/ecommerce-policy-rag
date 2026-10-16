import pytest
import yaml
from pydantic import ValidationError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from policy_rag.chunking import PolicyChunker, _sentence_groups, _window_text
from policy_rag.config import Settings
from policy_rag.corpus import CorpusIntegrityError, CorpusRepository
from policy_rag.loaders import (
    DocumentLoadError,
    HtmlLoader,
    LoaderRegistry,
    MarkdownLoader,
    PdfLoader,
)
from policy_rag.models import QueryRequest


def test_manifest_real_unknown_dates_and_synthetic_explicit(documents):
    assert len(documents) == 11
    for document in documents:
        metadata = document.metadata
        assert len(metadata.content_sha256) == 64
        if metadata.synthetic:
            assert metadata.effective_from is not None
        else:
            assert metadata.effective_from is None
            assert metadata.source_url.startswith("https://")


@pytest.mark.parametrize("strategy", ["structure", "sliding"])
def test_chunks_reproducible_nonempty_bounded(documents, strategy):
    chunker = PolicyChunker(strategy, 220, 30)
    chunks = chunker.split(documents[0])
    assert chunks == chunker.split(documents[0])
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert all(
        chunk.text and chunk.metadata.doc_id == documents[0].metadata.doc_id for chunk in chunks
    )
    assert all(len(chunk.text) <= 220 for chunk in chunks)


def test_invalid_chunk_strategy():
    with pytest.raises(ValueError):
        PolicyChunker("bad", 200, 20)


def test_split_long_and_sentence_boundaries():
    assert len(list(_window_text("A" * 700, 200, 30))) == 4
    assert len(list(_sentence_groups("foo。" + "A" * 700, 200, 0))) > 3
    assert list(_window_text("", 200, 30)) == []


def test_markdown_nested_headings_frontmatter(tmp_path):
    path = tmp_path / "policy.md"
    path.write_text(
        "---\nsecret: no\n---\n# Policy\n## Returns\nWithin 7 days.\n### Opened\nNot eligible.\n",
        encoding="utf-8",
    )
    sections = MarkdownLoader().load(path, "Document")
    assert len(sections) == 2
    assert sections[-1].heading_path == ["Document", "Policy", "Returns", "Opened"]
    assert "secret" not in str(sections)


def test_html_removes_navigation_and_nested_duplicates(tmp_path):
    path = tmp_path / "policy.html"
    path.write_text(
        "<nav>ignore</nav><h2>Refunds</h2><p>A <b>real</b> term.</p>"
        "<li><p>Nested</p></li><script>alert(1)</script>",
        encoding="utf-8",
    )
    sections = HtmlLoader().load(path, "Document")
    text = "\n".join(item.text for item in sections)
    assert "ignore" not in text and "alert" not in text
    assert text.count("Nested") == 1


def test_pdf_text_and_page_number(tmp_path):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 100 Td (Synthetic return policy: 7 days.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    path = tmp_path / "synthetic.pdf"
    writer.write(path)
    sections = PdfLoader().load(path, "Synthetic")
    assert sections[0].page == 1
    assert "7 days" in sections[0].text


def test_loader_empty_unsupported_and_bad_pdf(tmp_path):
    path = tmp_path / "empty.md"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DocumentLoadError):
        LoaderRegistry().load(path, "Empty")
    with pytest.raises(DocumentLoadError):
        LoaderRegistry().load(path.with_suffix(".exe"), "Bad")
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(DocumentLoadError):
        PdfLoader().load(path, "Bad PDF")


@pytest.mark.parametrize("kind", ["hash", "missing"])
def test_manifest_rejects_corruption(tmp_path, settings, kind):
    raw = yaml.safe_load(settings.source_manifest.read_text(encoding="utf-8"))
    raw["sources"] = raw["sources"][:1]
    if kind == "hash":
        raw["sources"][0]["metadata"]["content_sha256"] = "bad"
    else:
        raw["sources"][0]["local_path"] = str(tmp_path / "missing.md")
    manifest = tmp_path / "sources.yaml"
    manifest.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(CorpusIntegrityError):
        CorpusRepository(manifest).load_documents()


@pytest.mark.parametrize(
    "config",
    [
        {"chunk_size": 200, "chunk_overlap": 200},
        {"candidate_k": 5, "default_top_k": 10},
        {"llm_provider": "openai_compatible"},
        {"port": 0},
    ],
)
def test_invalid_config(config):
    with pytest.raises(ValidationError):
        Settings(**config, _env_file=None)


def test_secret_redacted_and_base_url_validation():
    values = dict(
        llm_provider="openai_compatible",
        llm_base_url="https://example.com/v1",
        llm_model="demo",
        llm_api_key="private-secret",
    )
    assert "private-secret" not in str(Settings(**values, _env_file=None))
    with pytest.raises(ValidationError):
        Settings(**(values | {"llm_base_url": "http://example.com"}), _env_file=None)
    with pytest.raises(ValidationError):
        Settings(**(values | {"llm_base_url": "https://key@example.com"}), _env_file=None)


def test_question_whitespace_rejected():
    with pytest.raises(ValidationError):
        QueryRequest(question="   ")
    assert QueryRequest(question=" a   b ").question == "a b"


def test_decimal_versions_and_sliding_chapter_preservation(documents):
    from policy_rag.chunking import _sentence_groups

    parts = list(_sentence_groups("AppleCare+ v2.4 的条款标识需要保持完整。", 200, 20))
    assert "v2.4" in parts[0]
    for doc in documents:
        for chunk in PolicyChunker("sliding", 160, 40).split(doc):
            assert chunk.section_path and "滑动窗口" not in chunk.section_path
            assert len(chunk.text) <= 160
