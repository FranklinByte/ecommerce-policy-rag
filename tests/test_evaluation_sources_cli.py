import json

import httpx
import pytest
from typer.testing import CliRunner

from policy_rag.cli import app
from policy_rag.corpus import CorpusRepository
from policy_rag.evaluation import citation_metrics, load_cases, ranking_metrics, run_evaluation
from policy_rag.indexing import IndexBuilder
from policy_rag.paths import project_path
from policy_rag.sources import download, fetch_sources, import_snapshot, validate_source_url
from tests.conftest import FakeEmbedder, FakeReranker


def test_metrics_hand_calculated():
    metrics = ranking_metrics(["x", "a", "a", "b"], {"a": 1, "b": 1})
    assert metrics["recall@1"] == 0
    assert metrics["recall@3"] == 1
    assert metrics["mrr@5"] == 0.5
    assert metrics["ndcg@5"] == pytest.approx(0.6934264)
    assert citation_metrics([], ["a"])["citation_recall"] == 0
    assert citation_metrics([], ["a"])["citation_precision"] is None
    assert citation_metrics(["a", "b"], ["a"])["citation_precision"] == 0.5
    with pytest.raises(ValueError):
        ranking_metrics([], {})


def test_fixed_dataset_labels_and_counts(settings, tmp_path):
    valid = {
        entry.metadata.doc_id
        for entry in CorpusRepository(settings.source_manifest).read_manifest().sources
    }
    cases = load_cases(project_path("data/eval/queries.jsonl"), valid)
    assert len(cases) == 72 and sum(not case.answerable for case in cases) == 12
    assert all("AI-assisted" in case.annotation_source for case in cases)
    path = tmp_path / "bad.jsonl"
    for raw in [
        [cases[0].model_dump(mode="json")] * 2,
        [cases[0].model_dump(mode="json") | {"answerable": False}],
        [cases[0].model_dump(mode="json") | {"relevance_grades": {}}],
    ]:
        path.write_text("\n".join(json.dumps(item) for item in raw), encoding="utf-8")
        with pytest.raises(ValueError):
            load_cases(path, valid)
    with pytest.raises(ValueError):
        load_cases(project_path("data/eval/queries.jsonl"), set())


def test_full_evaluator_with_test_doubles(settings, tmp_path, monkeypatch):
    import policy_rag.evaluation as evaluation

    monkeypatch.setattr(evaluation, "SentenceTransformerEmbedder", lambda *_: FakeEmbedder())
    monkeypatch.setattr(evaluation, "CrossEncoderReranker", lambda *_: FakeReranker())
    builder = IndexBuilder(settings, FakeEmbedder())
    builder.build("structure")
    builder.build("sliding")
    output = tmp_path / "results" / "test-double-NOT-model-evaluation"
    report = run_evaluation(settings, project_path("data/eval/experiment.yaml"), output)
    assert len(report["experiments"]) == 8
    assert (output / "summary.csv").is_file() and (output / "report.md").is_file()
    assert report["llm_generation_evaluation"].startswith("not_executed")
    with pytest.raises(ValueError):
        run_evaluation(settings, project_path("data/eval/experiment.yaml"), output)


@pytest.mark.parametrize(
    "url",
    [
        "http://www.apple.com.cn",
        "https://127.0.0.1/",
        "https://evil.example",
        "https://user:pass@www.apple.com.cn",
        "https://www.apple.com.cn:444",
    ],
)
def test_source_url_allowlist(url):
    with pytest.raises(ValueError):
        validate_source_url(url)


def test_download_redirect_retry_limit_and_size(settings, respx_mock):
    url = "https://www.apple.com.cn/a"
    route = respx_mock.get(url)
    route.side_effect = [httpx.ConnectError("offline"), httpx.Response(200, content=b"policy")]
    assert download(url, settings) == b"policy"
    route.side_effect = None
    route.return_value = httpx.Response(302, headers={"Location": "https://evil.example"})
    with pytest.raises(ValueError):
        download(url, settings)
    route.return_value = httpx.Response(302, headers={"Location": url})
    with pytest.raises(ValueError, match="redirect"):
        download(url, settings)
    route.return_value = httpx.Response(200, content=b"a" * 2000)
    with pytest.raises(ValueError, match="size"):
        download(url, settings.model_copy(update={"max_download_bytes": 1000}))


def test_fetch_and_import_private_snapshot(settings, tmp_path, monkeypatch):
    import policy_rag.sources as sources

    manifest_path = tmp_path / "sources.yaml"
    manifest_path.write_bytes(settings.source_manifest.read_bytes())
    settings = settings.model_copy(update={"source_manifest": manifest_path})
    monkeypatch.setattr(sources, "download", lambda *_: b"<h1>Policy</h1><p>Test only.</p>")
    cache = tmp_path / "cache"
    results = fetch_sources(settings, cache, update_manifest=True)
    assert len(results) == 7 and all(item["status"] == "downloaded" for item in results)
    destination = tmp_path / "private.yaml"
    import_snapshot(settings, "apple-store-returns-cn-current", cache, destination)
    imported = CorpusRepository(destination).load_documents()
    assert len(imported) == 1
    assert imported[0].metadata.source_content_sha256 == results[0]["sha256"]
    with pytest.raises(ValueError):
        import_snapshot(settings, "missing", cache, destination)

    def failure(*_):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(sources, "download", failure)
    assert all(item["status"] == "failed" for item in fetch_sources(settings, cache))


def test_cli_contracts(monkeypatch, settings, tmp_path):
    import policy_rag.cli as cli

    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert runner.invoke(app, ["verify-corpus"]).exit_code == 0
    assert runner.invoke(app, ["index", "--strategy", "invalid"]).exit_code != 0
    path = tmp_path / "policy.md"
    path.write_text("# Test\nSynthetic content.", encoding="utf-8")
    assert runner.invoke(app, ["inspect-document", str(path)]).exit_code == 0
    monkeypatch.setattr(cli.uvicorn, "run", lambda *_, **__: None)
    assert runner.invoke(app, ["serve", "--port", "8020"]).exit_code == 0
