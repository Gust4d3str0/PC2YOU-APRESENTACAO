"""Read-only demonstration endpoints. No arbitrary Mongo queries, no writes, no secrets."""

import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.collection import Collection

from database import get_components_collection
from product_matching import CatalogMatcher, HIGH, MEDIUM, VERSION, match_product
from product_matching.destinations import classify_url, store_from_url
from product_matching.matcher import compare_product, features
from product_matching.normalization import normalize_text
from product_matching.offers import condition_labels
from product_matching.promotions import enrich_promotion

from .sanitize import sanitize, sanitize_document

# `services.telegram_collector.parser` (copied next to the app in Docker, repo root locally).
_root = Path(__file__).resolve().parents[2]
if (_root / "services").is_dir() and str(_root) not in sys.path:
    sys.path.append(str(_root / "services"))
from telegram_collector.filters import is_possible_promotion  # noqa: E402
from telegram_collector.parser import parse_message  # noqa: E402

router = APIRouter(prefix="/demo", tags=["Demonstração"])

# Whitelist: the ONLY collections reachable. Each lists its main fields (dotted paths) and its sort.
COLLECTIONS = {
    "components": {"fields": ["id", "name", "category", "brand", "external_enrichment.mercado_livre.product_id"],
                   "sort": [("id", 1)], "about": "Catálogo técnico (seed de 121 componentes + enriquecimento)."},
    "telegram_promotions": {"fields": ["product.component_id", "product.match_level", "offer.store", "offer.price",
                                       "offer.coupon", "offer.source", "status"],
                            "sort": [("created_at", -1)], "about": "Ofertas lidas de canais do Telegram (anonimizadas)."},
    "product_price_history": {"fields": ["component_id", "price", "source", "match_level", "verified", "date"],
                              "sort": [("date", -1)], "about": "Observações reais e verificadas de preço."},
    "external_product_enrichment": {"fields": ["product_id", "name", "brand", "model", "domain_id", "fetched_at"],
                                    "sort": [("fetched_at", -1)], "about": "Cache da Product API do Mercado Livre."},
    "ml_integration_state": {"fields": ["product_api", "item_api", "price_validation", "last_product_success"],
                             "sort": [("_id", 1)], "about": "Estado e contadores da integração Mercado Livre."},
    "telegram_service_status": {"fields": ["connected", "source_count", "updated_at"],
                                "sort": [("_id", 1)], "about": "Sinal de vida do coletor Telegram."},
}
MAX_PAGE_SIZE = 10
MAX_PAGE = 100
_cache: dict = {}
_lock = threading.Lock()


def cached(key, ttl, build):
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
    value = build()
    with _lock:
        _cache[key] = (time.monotonic(), value)
    return value


def dotted(document, path):
    for part in path.split("."):
        document = document.get(part) if isinstance(document, dict) else None
    return document


# --- database explorer ---------------------------------------------------------------------------

@router.get("/database")
def database_overview(collection: Collection = Depends(get_components_collection)):
    db = collection.database

    def build():
        return {"database": "MongoDB", "read_only": True, "terms": "collections e documentos (não tabelas/linhas)",
                "collections": [{"name": name, "count": db[name].estimated_document_count(), "fields": meta["fields"],
                                 "about": meta["about"]} for name, meta in COLLECTIONS.items()]}
    return cached(("overview", id(db)), 15, build)


@router.get("/database/{name}")
def database_collection(name: str, page: int = Query(1, ge=1, le=MAX_PAGE),
                        page_size: int = Query(5, ge=1, le=MAX_PAGE_SIZE),
                        collection: Collection = Depends(get_components_collection)):
    meta = COLLECTIONS.get(name)
    if meta is None:
        raise HTTPException(status_code=404, detail="Collection não disponível na demonstração")
    target = collection.database[name]
    projection = {field: 1 for field in meta["fields"] + ["created_at", "fetched_at", "updated_at"]}
    rows = list(target.find({}, projection).sort(meta["sort"]).skip((page - 1) * page_size).limit(page_size))
    documents = [sanitize_document(row) for row in rows]
    return {"collection": name, "page": page, "page_size": page_size, "total": target.estimated_document_count(),
            "fields": meta["fields"],
            "table": [{field: dotted(doc, field) for field in meta["fields"]} for doc in documents],
            "documents": documents}


# --- Product Matcher -----------------------------------------------------------------------------

class MatcherRequest(BaseModel):
    text: str = Field(min_length=3, max_length=300)


def _catalog_matcher(collection):
    def build():
        return CatalogMatcher(list(collection.find({}, {"_id": 0})))
    return cached(("matcher", id(collection.database)), 60, build)


def _listify(values):
    return sorted(str(v) for v in values)


@router.get("/matcher")
def demo_matcher(body: MatcherRequest = Depends(), collection: Collection = Depends(get_components_collection)):
    """The REAL deterministic matcher (no AI, no network) applied to the typed text."""
    catalog = _catalog_matcher(collection)
    product = {"title": body.text, "source": "telegram"}
    feat = features(product)
    scored = []
    for component in catalog.rows:
        result = compare_product(product, component, _product_features=feat,
                                 _component_features=catalog.features[str(component["id"])])
        scored.append((result, component))
    scored.sort(key=lambda item: (item[0].confidence, len(item[0].matched_by)), reverse=True)
    final = match_product(product, catalog)
    by_id = {str(c["id"]): c for c in catalog.rows}
    return {
        "algorithm": "determinístico, baseado em regras e heurísticas — não usa IA/Gemini", "version": VERSION,
        "thresholds": {"high": HIGH, "medium": MEDIUM, "note": "o score é evidência heurística, não probabilidade"},
        "text": body.text, "normalized": normalize_text(body.text),
        "features": {"category": feat["category"], "model": _listify(feat["model"]), "brands": _listify(feat["brands"]),
                     "capacity_gb": _listify(feat["capacity"]), "memory_type": _listify(feat["memory_type"]),
                     "frequency": _listify(feat["frequency"]), "socket": _listify(feat["socket"]),
                     "multiple_products": bool(feat["multiple"])},
        "candidates": [{"component_id": str(c["id"]), "name": c["name"], "score": r.confidence, "level": r.confidence_level,
                        "matched_by": r.matched_by, "conflicts": r.conflicts} for r, c in scored[:5]],
        "result": {"matched": final.matched, "component_id": final.component_id,
                   "component_name": by_id[final.component_id]["name"] if final.component_id in by_id else None,
                   "score": final.confidence, "level": final.confidence_level, "matched_by": final.matched_by,
                   "conflicts": final.conflicts},
    }


# --- Telegram pipeline ---------------------------------------------------------------------------

SAMPLES_FILE = Path(__file__).with_name("samples.json")


def load_samples():
    return json.loads(SAMPLES_FILE.read_text(encoding="utf-8"))


@router.get("/telegram-samples")
def telegram_samples():
    return {"samples": load_samples(), "note": "Mensagens de exemplo (fixture): nenhuma rede ou conta Telegram é usada."}


class TelegramParseRequest(BaseModel):
    text: str = Field(min_length=3, max_length=1500)


@router.get("/telegram-parse")
def telegram_parse(body: TelegramParseRequest = Depends(), collection: Collection = Depends(get_components_collection)):
    """Filter -> parser -> matcher -> status, on an example message. Nothing is persisted."""
    now = datetime.now(timezone.utc)
    passed = is_possible_promotion(body.text)
    parsed = parse_message(body.text, sent_at=now)
    document = {"telegram": {"sent_at": now}, "raw_text": body.text, **parsed, "status": "parsed", "created_at": now}
    matcher = _catalog_matcher(collection)
    enriched = enrich_promotion(document, matcher, now)
    product, offer, evaluation = enriched["product"], enriched["offer"], enriched["evaluation"]
    by_id = {str(c["id"]): c for c in matcher.rows}
    url = offer.get("url")
    return sanitize({
        "filter": {"passed": passed, "rule": "contém R$ ou palavra-chave de promoção/hardware"},
        "parser": {"store": offer.get("store"), "price": offer.get("price"), "original_price": offer.get("original_price"),
                   "coupon": offer.get("coupon"), "component_type": product.get("component_type")},
        "url": {"url": url, "source": offer.get("url_source"), "kind": classify_url(url) if url else None,
                "store_from_domain": store_from_url(url) if url else None,
                "note": "classificação só pela forma da URL; o redirect real é resolvido em background pelo coletor"},
        "conditions": offer.get("conditions") or {}, "condition_labels": condition_labels(offer.get("conditions")),
        "matcher": {"component_id": product.get("component_id"),
                    "component_name": by_id[product["component_id"]]["name"] if product.get("component_id") in by_id else None,
                    "level": product.get("match_level"), "confidence": product.get("match_confidence"),
                    "matched_by": product.get("matched_by"), "conflicts": product.get("conflicts"),
                    "note": "o matcher lê o texto bruto (product.name é None no parser)"},
        "evaluation": {k: evaluation[k] for k in ("status", "reason", "eligible", "freshness", "is_conditional")},
        "verified": offer.get("verified"),
        "stored": False,
    })


# --- status, metrics, ML example -----------------------------------------------------------------

@router.get("/status")
def demo_status(collection: Collection = Depends(get_components_collection)):
    """Cached (30 s). Reads Mongo only; never calls Mercado Livre, Telegram or Gemini."""
    db = collection.database

    def build():
        import ml_products
        result = {"checked_at": datetime.now(timezone.utc).isoformat()}
        try:
            db.command("ping")
            result["mongodb"] = "ONLINE"
        except Exception:
            result["mongodb"] = "OFFLINE"
            return {**result, "telegram": "NÃO VERIFICADO", "mercado_livre_product_api": "NÃO VERIFICADO",
                    "mercado_livre_item_api": "NÃO VERIFICADO"}
        heartbeat = db["telegram_service_status"].find_one({"_id": "collector"}) or {}
        updated = heartbeat.get("updated_at")
        if updated is not None and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        online = bool(heartbeat.get("connected") and updated
                      and (datetime.now(timezone.utc) - updated).total_seconds() < 120)
        result["telegram"] = "ONLINE" if online else "OFFLINE"
        result["telegram_detail"] = ("coletor com sinal recente" if online
                                     else "sem sinal recente do coletor (dados armazenados continuam disponíveis)")
        ml = ml_products.integration_status(ml_products.tokens, db)
        result["mercado_livre_product_api"] = ("CONFIGURADO" if ml.get("configured") and ml.get("product_api") == "available"
                                               else "OFFLINE")
        result["mercado_livre_product_detail"] = "último sucesso registrado: " + str(ml.get("last_product_success") or "nenhum")
        result["mercado_livre_item_api"] = ("RESTRITO" if ml.get("item_api") == "restricted"
                                            else str(ml.get("item_api", "unknown")).upper())
        return result
    return cached(("status", id(db)), 30, build)


@router.get("/metrics")
def demo_metrics(collection: Collection = Depends(get_components_collection)):
    """Live counters (cached 30 s by commerce.snapshot)."""
    import commerce
    data = commerce.snapshot(collection.database)
    return {"components": len(data["components"]), "counts": data["counts"],
            "components_with_current_offer": len(data["best"]), "source": "api-catalogo ao vivo"}


ML_MATCHED = {"external_enrichment.mercado_livre.match_status": "matched",
              "external_enrichment.mercado_livre.external_conflict": False}


@router.get("/ml-components")
def ml_components(collection: Collection = Depends(get_components_collection)):
    """Components that already carry an accepted Mercado Livre enrichment (persisted data)."""
    rows = collection.find(ML_MATCHED, {"_id": 0, "id": 1, "name": 1, "external_enrichment.mercado_livre.product_id": 1}
                           ).sort("id", 1).limit(60)
    return {"items": [{"component_id": r["id"], "name": r["name"],
                       "product_id": r["external_enrichment"]["mercado_livre"].get("product_id")} for r in rows]}


@router.get("/ml-example")
def ml_example(component_id: str | None = Query(None, max_length=120),
               collection: Collection = Depends(get_components_collection)):
    """A stored (already persisted) Mercado Livre enrichment: PRODUCT_ID -> name, brand, model, image, specs."""
    selector = {**ML_MATCHED, **({"id": component_id} if component_id else {})}
    row = collection.find_one(selector, {"_id": 0}, sort=[("id", 1)])
    if not row:
        return {"available": False}
    ml = row["external_enrichment"]["mercado_livre"]
    return sanitize({"available": True, "component_id": row["id"], "component_name": row["name"],
                     "product_id": ml.get("product_id"), "name": ml.get("name"), "brand": ml.get("brand"),
                     "model": ml.get("model"), "image": (ml.get("images") or [None])[0],
                     "images": len(ml.get("images") or []), "specs": ml.get("specs"),
                     "match_status": ml.get("match_status"), "match_basis": ml.get("match_basis"),
                     "fetched_at": ml.get("fetched_at"), "source": "snapshot persistido (nenhuma chamada externa)"})


# --- latest REAL Telegram promotion (stored) -----------------------------------------------------

def _latest_view(row, matcher, now):
    enriched = enrich_promotion(row, matcher, now)
    product, offer, evaluation = enriched["product"], enriched["offer"], enriched["evaluation"]
    by_id = {str(c["id"]): c for c in matcher.rows}
    sent = (row.get("telegram") or {}).get("sent_at") or row.get("created_at")
    if isinstance(sent, datetime) and sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)
    age = round((now - sent).total_seconds() / 60) if isinstance(sent, datetime) else None
    return sanitize({
        "id": str(row["_id"]), "received_at": sent, "age_minutes": age,
        "channel": "Canal de ofertas (anonimizado)", "text": row.get("raw_text"),
        "extracted": {"store": offer.get("store"), "price": offer.get("price"), "original_price": offer.get("original_price"),
                      "coupon": offer.get("coupon"), "url": offer.get("url"), "component_type": product.get("component_type")},
        "match": {"component_id": product.get("component_id"),
                  "component_name": by_id[product["component_id"]]["name"] if product.get("component_id") in by_id else None,
                  "level": product.get("match_level"), "confidence": product.get("match_confidence"),
                  "conflicts": product.get("conflicts")},
        "status": evaluation["status"], "eligible": evaluation["eligible"],
    })


@router.get("/telegram-latest")
def telegram_latest(matched: bool = False, collection: Collection = Depends(get_components_collection)):
    """Most recent stored real promotion (optionally the most recent High match). Always labeled as stored."""
    selector = {"is_demo": {"$ne": True}}
    if matched:
        selector["product.match_level"] = "high"
    row = collection.database["telegram_promotions"].find_one(selector, sort=[("telegram.sent_at", -1), ("created_at", -1)])
    if not row:
        return {"available": False}
    now = datetime.now(timezone.utc)
    return {"available": True, "label": "promoção real armazenada no MongoDB (não é uma mensagem recebida agora)",
            "promotion": _latest_view(row, _catalog_matcher(collection), now),
            "collector": demo_status(collection).get("telegram")}
