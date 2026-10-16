"""Container startup: bounded Qdrant readiness wait, idempotent index build, single worker."""

import httpx
import uvicorn
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from policy_rag.config import Settings
from policy_rag.indexing import IndexBuilder
from policy_rag.logging import configure_logging


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(15),
    wait=wait_fixed(1),
    reraise=True,
)
def wait_for_qdrant(url: str) -> None:
    response = httpx.get(f"{url.rstrip('/')}/healthz", timeout=3)
    response.raise_for_status()


if __name__ == "__main__":
    settings = Settings()
    configure_logging(settings.log_level)
    if settings.qdrant_url:
        wait_for_qdrant(settings.qdrant_url)
    IndexBuilder(settings).build()
    uvicorn.run("policy_rag.api:app", host="0.0.0.0", port=8010, workers=1)
