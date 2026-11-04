"""Presentation (DEMO_MODE) support for api-catalogo: read-only guard + /demo/* endpoints."""

import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger("api-catalogo.demo")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Non-GET routes that remain open in the demo: pure reads (batch) and the stateless demonstrations.
OPEN_POSTS = {"/components/batch"}


def enabled() -> bool:
    return os.getenv("DEMO_MODE", "false").strip().lower() == "true"


def is_blocked(method: str, path: str) -> bool:
    return method.upper() not in SAFE_METHODS and not (method.upper() == "POST" and path.rstrip("/") in OPEN_POSTS)


def install(app: FastAPI) -> None:
    if not enabled():
        return
    from .loader import load_demo_data
    from .routes import router

    @app.middleware("http")
    async def read_only_guard(request, call_next):
        if is_blocked(request.method, request.url.path):
            return JSONResponse(status_code=403, content={"detail": "Desativado no modo demonstração (somente leitura)."})
        return await call_next(request)

    app.include_router(router)

    def _load():
        try:
            logger.info("Demo data: %s", load_demo_data())
        except Exception as exc:  # the site must start even without the snapshot
            logger.warning("Demo data not loaded (%s)", type(exc).__name__)

    app.add_event_handler("startup", _load)
