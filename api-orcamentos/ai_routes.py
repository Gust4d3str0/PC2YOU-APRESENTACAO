"""AI routes share the existing budget API; no separate server or database."""

import sys
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

# Local checkout: services/ai; Docker: /app/ai (copied in the image).
_services_path = Path(__file__).resolve().parents[1] / "services"
if _services_path.is_dir():
    sys.path.append(str(_services_path))

from ai import AIService
from ai.errors import AIError
from ai.schemas import AnalyzePCRequest, AnalyzePCResponse
from ai_context import build_context
from catalog_client import catalog_client
from ai.upgrade_schemas import RecommendUpgradesRequest, RecommendUpgradesResponse
from ai.upgrades import recommend_upgrades
from ai_upgrade_context import build_upgrade_bundle, replacement_compatibility
from promotion_source import PromotionSource


router = APIRouter(prefix="/ai", tags=["ai"])


@lru_cache
def get_ai_service():
    return AIService()


def get_ai_catalog():
    return catalog_client


@lru_cache
def get_promotion_source():
    return PromotionSource()


@router.post("/recommend-upgrades", response_model=RecommendUpgradesResponse)
def recommend_pc_upgrades(payload: RecommendUpgradesRequest, catalog=Depends(get_ai_catalog)):
    try:
        service = get_ai_service()
        service.ensure_available()
        source = get_promotion_source() if payload.include_promotions else None
        bundle = build_upgrade_bundle(payload, catalog, source)

        def check_combination(ids):
            return replacement_compatibility(bundle["build_internal"],
                                             [bundle["internal"][cid] for cid in ids]) is not None

        return recommend_upgrades(service, bundle, check_combination)
    except AIError as exc:
        headers = {"Retry-After": "60"} if exc.status == 429 else None
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}, headers=headers) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=503, detail={"code": "upgrade_context_invalid", "message": "Não foi possível preparar os dados dos upgrades. Tente novamente mais tarde."}) from exc


@router.post("/analyze-pc", response_model=AnalyzePCResponse)
def analyze_pc(payload: AnalyzePCRequest, catalog=Depends(get_ai_catalog)):
    try:
        service = get_ai_service()
        service.ensure_available()  # Disabled/key errors do not need catalog access.
        context = build_context(payload, catalog)
        return service.analyze_pc(context)
    except AIError as exc:
        headers = {"Retry-After": "60"} if exc.status == 429 else None
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}, headers=headers) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=503, detail={
            "code": "catalog_invalid", "message": "Os dados técnicos do catálogo estão indisponíveis. Tente novamente mais tarde.",
        }) from exc
