from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from policy_rag.paths import PROJECT_ROOT, project_path


class Settings(BaseSettings):
    """Validated runtime configuration. Secrets are accepted only through environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="POLICY_RAG_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8010, ge=1, le=65535)
    log_level: str = "INFO"

    source_manifest: Path = Path("data/sources.yaml")
    index_root: Path = Path("data/index")
    artifact_root: Path = Path("eval-results")
    chunk_strategy: Literal["structure", "sliding"] = "structure"
    chunk_size: int = Field(default=520, ge=160, le=4000)
    chunk_overlap: int = Field(default=80, ge=0, le=1000)

    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"
    embedding_revision: str = "7999e1d3359715c523056ef9478215996d62a620"
    reranker_revision: str = "2cfc18c9415c912f9d8155881c133215df768a70"
    torch_threads: int = Field(default=4, ge=1, le=32)
    embedding_device: str = "cpu"
    reranker_device: str = "cpu"
    model_cache_dir: Path | None = None
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    reranker_batch_size: int = Field(default=16, ge=1, le=128)

    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    collection_prefix: str = "ecommerce_policy"

    candidate_k: int = Field(default=10, ge=5, le=100)
    default_top_k: int = Field(default=5, ge=1, le=20)
    rrf_k: int = Field(default=60, ge=1, le=200)
    evidence_threshold: float = Field(default=0.42, ge=0.0, le=1.0)
    dense_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    sparse_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    request_timeout_seconds: float = Field(default=120.0, ge=1, le=600)

    download_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    max_download_bytes: int = Field(default=20_000_000, ge=1024, le=100_000_000)

    llm_provider: Literal["none", "openai_compatible"] = "none"
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    llm_timeout_seconds: float = Field(default=30.0, ge=1.0, le=180.0)

    @field_validator("source_manifest", "index_root", "artifact_root", "model_cache_dir")
    @classmethod
    def resolve_paths(cls, value: Path | None) -> Path | None:
        return None if value is None else project_path(value)

    @model_validator(mode="after")
    def validate_related_values(self) -> "Settings":
        from urllib.parse import urlsplit

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.candidate_k < self.default_top_k:
            raise ValueError("candidate_k must be >= default_top_k")
        if self.llm_provider == "openai_compatible":
            if not self.llm_base_url or not self.llm_model or not self.llm_api_key:
                raise ValueError(
                    "openai_compatible generation requires LLM_BASE_URL, LLM_MODEL and LLM_API_KEY"
                )
            url = urlsplit(self.llm_base_url)
            if url.scheme != "https" and url.hostname not in {"localhost", "127.0.0.1"}:
                raise ValueError("LLM_BASE_URL must use HTTPS except for localhost")
            if url.username or url.password or url.query or url.fragment:
                raise ValueError("LLM_BASE_URL must not contain credentials, query or fragment")
        if self.qdrant_url:
            url = urlsplit(self.qdrant_url)
            if url.scheme not in {"http", "https"} or not url.hostname:
                raise ValueError("QDRANT_URL must be an HTTP(S) server URL")
            if url.username or url.password or url.query or url.fragment:
                raise ValueError("Use QDRANT_API_KEY, not credentials in QDRANT_URL")
        return self

    def strategy_index_dir(self, strategy: str | None = None) -> Path:
        return self.index_root / (strategy or self.chunk_strategy)
