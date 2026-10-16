from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from policy_rag.config import Settings
from policy_rag.logging import configure_logging
from policy_rag.models import HealthResponse, QueryRequest, QueryResponse
from policy_rag.retrieval.service import IndexNotReady
from policy_rag.service import PolicyRAGService, ServiceBusy

logger = structlog.get_logger()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            app.state.policy_service = PolicyRAGService(resolved_settings)
            app.state.startup_error = None
        except IndexNotReady as exc:
            app.state.policy_service = None
            app.state.startup_error = str(exc)
            logger.warning("service_started_without_index", reason=str(exc))
        yield
        if app.state.policy_service is not None:
            app.state.policy_service.close()

    app = FastAPI(
        title="电商售后政策 Hybrid RAG",
        version="0.1.0",
        description="Version-aware policy retrieval and evidence QA; not a legal decision system.",
        lifespan=lifespan,
    )
    static_dir = Path(__file__).parent / "static"
    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.middleware("http")
    async def request_logging(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        logger.info(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return response

    @app.get("/", include_in_schema=False)
    async def home() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        service: PolicyRAGService | None = request.app.state.policy_service
        if service is None:
            return HealthResponse(
                status="degraded",
                index_ready=False,
                index_version=None,
                embedding_model=resolved_settings.embedding_model,
                reranker_model=resolved_settings.reranker_model,
                qdrant_backend=resolved_settings.qdrant_url or "local",
                details={"startup_error": request.app.state.startup_error},
            )
        return HealthResponse(
            status="ok" if service.retrieval.dense else "degraded",
            index_ready=True,
            index_version=service.retrieval.manifest.index_version,
            embedding_model=resolved_settings.embedding_model,
            reranker_model=resolved_settings.reranker_model,
            qdrant_backend=service.retrieval.dense.backend_name
            if service.retrieval.dense
            else "unavailable",
            details={"chunk_strategy": service.retrieval.manifest.strategy},
        )

    @app.post("/api/v1/query", response_model=QueryResponse)
    async def query(payload: QueryRequest, request: Request) -> QueryResponse:
        service: PolicyRAGService | None = request.app.state.policy_service
        if service is None:
            raise HTTPException(status_code=503, detail=request.app.state.startup_error)
        return await execute_query(service, payload)

    @app.get("/ready")
    async def ready(request: Request) -> dict[str, str]:
        service: PolicyRAGService | None = request.app.state.policy_service
        if service is None or service.retrieval.dense is None:
            raise HTTPException(status_code=503, detail="Index or vector store not ready")
        try:
            store = service.retrieval.dense
            exists = await asyncio.to_thread(store.client.collection_exists, store.collection_name)
            if not exists:
                raise HTTPException(status_code=503, detail="Vector collection missing")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Vector store unavailable") from exc
        return {"status": "ready"}

    @app.post("/api/v1/retrieve", response_model=QueryResponse)
    async def retrieve(payload: QueryRequest, request: Request) -> QueryResponse:
        service: PolicyRAGService | None = request.app.state.policy_service
        if service is None:
            raise HTTPException(status_code=503, detail=request.app.state.startup_error)
        return await execute_query(service, payload.model_copy(update={"generate": False}))

    async def execute_query(service: PolicyRAGService, payload: QueryRequest) -> QueryResponse:
        try:
            # The worker keeps the service lock after a timeout until CPU inference really ends.
            return await asyncio.wait_for(
                asyncio.to_thread(service.query, payload),
                timeout=resolved_settings.request_timeout_seconds,
            )
        except ServiceBusy as exc:
            raise HTTPException(status_code=429, detail="模型繁忙，请稍后重试") from exc
        except TimeoutError as exc:
            raise HTTPException(
                status_code=504, detail="查询超时；已有模型任务结束前不接受新的模型请求"
            ) from exc

    return app


app = create_app()
