from __future__ import annotations

from datetime import date
from pathlib import Path

import typer
import uvicorn

from policy_rag.config import Settings
from policy_rag.corpus import CorpusRepository
from policy_rag.evaluation import run_evaluation
from policy_rag.indexing import IndexBuilder
from policy_rag.loaders import LoaderRegistry
from policy_rag.logging import configure_logging
from policy_rag.models import PolicyFilter, QueryRequest, RetrievalMode
from policy_rag.paths import project_path
from policy_rag.service import PolicyRAGService
from policy_rag.sources import fetch_sources, import_snapshot

app = typer.Typer(no_args_is_help=True)


@app.command()
def index(strategy: str = "both", force: bool = False) -> None:
    """Build immutable indexes and atomically publish manifests."""
    settings = Settings()
    configure_logging(settings.log_level)
    if strategy not in {"both", "structure", "sliding"}:
        raise typer.BadParameter("strategy must be both, structure or sliding")
    builder = IndexBuilder(settings)
    for value in ["structure", "sliding"] if strategy == "both" else [strategy]:
        typer.echo(builder.build(value, force=force).model_dump_json(indent=2))


@app.command()
def query(
    question: str,
    mode: RetrievalMode = RetrievalMode.HYBRID_RERANK,
    platform: str | None = None,
    category: str | None = None,
    version: str | None = None,
    as_of: str | None = None,
) -> None:
    """Query indexed evidence with optional metadata filters."""
    service = PolicyRAGService(Settings())
    try:
        request = QueryRequest(
            question=question,
            mode=mode,
            filters=PolicyFilter(
                platform=platform,
                product_category=category,
                version=version,
                as_of_date=date.fromisoformat(as_of) if as_of else None,
            ),
        )
        typer.echo(service.query(request).model_dump_json(indent=2))
    finally:
        service.close()


@app.command("eval")
def evaluate(
    output: Path, config: Path = Path("data/eval/experiment.yaml"), provider: bool = False
) -> None:
    """Run fixed retrieval and generation evaluations into a new output directory."""
    settings = Settings()
    configure_logging(settings.log_level)
    run_evaluation(settings, project_path(config), project_path(output), provider=provider)
    typer.echo(str(project_path(output) / "report.md"))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8010) -> None:
    """Start the local demo and API (single worker for Qdrant Local)."""
    uvicorn.run("policy_rag.api:app", host=host, port=port, workers=1)


@app.command("verify-corpus")
def verify_corpus() -> None:
    documents = CorpusRepository(Settings().source_manifest).load_documents()
    typer.echo(f"Verified {len(documents)} documents and all SHA256 hashes")


@app.command("fetch-sources")
def fetch(output: Path = Path("data/external"), update_manifest: bool = False) -> None:
    """Download allowlisted originals to private cache, recording hash/time/status."""
    import json

    results = fetch_sources(Settings(), project_path(output), update_manifest=update_manifest)
    typer.echo(json.dumps(results, ensure_ascii=False, indent=2))


@app.command("import-snapshot")
def import_source(doc_id: str, output: Path, cache: Path = Path("data/external")) -> None:
    """Create an alternative private manifest from a downloaded raw snapshot."""
    import_snapshot(Settings(), doc_id, project_path(cache), project_path(output))


@app.command("inspect-document")
def inspect_document(path: Path) -> None:
    """Parse HTML, PDF or Markdown and print structured sections."""
    sections = LoaderRegistry().load(project_path(path), path.stem)
    for section in sections:
        typer.echo(section.model_dump_json())


@app.command("download-models")
def download_models() -> None:
    """Download only the pinned model artifacts; no paid key required."""
    from huggingface_hub import snapshot_download

    settings = Settings()
    for model, revision in [
        (settings.embedding_model, settings.embedding_revision),
        (settings.reranker_model, settings.reranker_revision),
    ]:
        path = snapshot_download(
            repo_id=model,
            revision=revision,
            cache_dir=str(settings.model_cache_dir) if settings.model_cache_dir else None,
            allow_patterns=[
                "*.json",
                "*.safetensors",
                "vocab.txt",
                "sentencepiece.bpe.model",
                "tokenizer.model",
            ],
            max_workers=2,
        )
        typer.echo(f"{model}@{revision}: {path}")


if __name__ == "__main__":
    app()
