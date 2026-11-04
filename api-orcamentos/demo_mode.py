"""DEMO_MODE=true: presentation build. Everything except the AI/wizard calculations becomes read-only."""

import os
import json

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from ai.config import AISettings
from ai.errors import AIError
from ai.schemas import AnalyzePCRequest
from ai_context import build_context

# The only non-GET routes that stay open: AI (no persistence) and the wizard's pure calculations.
OPEN_POSTS = {"/ai/analyze-pc", "/ai/recommend-upgrades", "/build/next-options", "/compatibility/check"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def enabled() -> bool:
    return os.getenv("DEMO_MODE", "false").strip().lower() == "true"


def is_blocked(method: str, path: str) -> bool:
    return method.upper() not in SAFE_METHODS and not (method.upper() == "POST" and path.rstrip("/") in OPEN_POSTS)


router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/ai-status")
def ai_status():
    """Configuration flags only. Never the key, never a provider call."""
    try:
        settings = AISettings.from_env()
    except AIError:
        return {"demo_mode": True, "ai_enabled": False, "key_configured": False, "model": None, "config_valid": False}
    return {"demo_mode": True, "ai_enabled": settings.enabled, "key_configured": bool(settings.api_key),
            "model": settings.model, "config_valid": True}


@router.get("/ai-context")
def ai_context(configuration: str = Query(..., max_length=6000)):
    try:
        payload = AnalyzePCRequest.model_validate(json.loads(configuration))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Configuração inválida") from exc
    """The exact trusted/user context the backend would send to Gemini (no model call, no secrets)."""
    from ai_routes import get_ai_catalog
    try:
        return build_context(payload, get_ai_catalog())
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=503, detail="Catálogo indisponível para montar o contexto.") from exc


def install(app: FastAPI) -> None:
    if not enabled():
        return

    @app.middleware("http")
    async def read_only_guard(request, call_next):
        if is_blocked(request.method, request.url.path):
            return JSONResponse(status_code=403, content={"detail": "Desativado no modo demonstração (somente leitura)."})
        return await call_next(request)

    app.include_router(router)
