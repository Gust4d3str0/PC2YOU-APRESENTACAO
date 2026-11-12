import ipaddress
import json
from datetime import datetime, timezone
import logging
import re
import socket
import threading
import time
import uuid
from urllib.parse import urljoin, urlparse

import requests
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, DuplicateKeyError, PyMongoError, ServerSelectionTimeoutError

import ml_service
import schemas
import services
from config import Settings, get_settings
from database import ensure_indexes, get_components_collection
from dependencies import get_current_user, require_admin
from seed import seed_components


settings = get_settings()
logger = logging.getLogger("api-catalogo")
logger.setLevel(logging.INFO)
app = FastAPI(
    title="OrcaPC API de Catálogo",
    version="1.1.0",
    description="Catálogo público de componentes e operações protegidas de administração.",
    openapi_tags=[
        {"name": "Saúde"},
        {"name": "Catálogo"},
        {"name": "Preços"},
        {"name": "Administração"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

proxy_session = requests.Session()


def _request_id_from_headers(request) -> str:
    candidate = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
    if candidate and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", candidate):
        return candidate
    return str(uuid.uuid4())


@app.middleware("http")
async def request_context_middleware(request, call_next):
    request_id = _request_id_from_headers(request)
    request.state.request_id = request_id
    started_at = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        response = JSONResponse(status_code=500, content={"detail": "Erro interno", "request_id": request_id})
    response.headers["X-Request-ID"] = request_id
    log_method = logger.error if response.status_code >= 500 else logger.info
    log_method(
        json.dumps(
            {
                "service": "api-catalogo",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "request_id": request_id,
            },
            ensure_ascii=False,
        )
    )
    return response


class RefreshCooldownCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, dict]] = {}
        self._in_flight: dict[str, threading.Event] = {}

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._in_flight.clear()

    def get_or_refresh(self, component_id: str, cooldown_seconds: int, refresh):
        while True:
            now = time.monotonic()
            with self._lock:
                cached = self._entries.get(component_id)
                if cached and now - cached[0] < cooldown_seconds:
                    return {**cached[1], "cached": True}
                event = self._in_flight.get(component_id)
                if event is None:
                    event = threading.Event()
                    self._in_flight[component_id] = event
                    break
            event.wait()

        try:
            result = refresh()
            with self._lock:
                self._entries[component_id] = (time.monotonic(), dict(result))
            return {**result, "cached": False}
        finally:
            with self._lock:
                completed = self._in_flight.pop(component_id, None)
                if completed:
                    completed.set()


refresh_cache = RefreshCooldownCache()


@app.on_event("startup")
def startup():
    last_error = None
    for _ in range(20):
        try:
            collection = get_components_collection()
            collection.database.command("ping")
            ensure_indexes(collection)
            seed_components()
            return
        except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
            last_error = exc
            time.sleep(2)
    if last_error:
        raise last_error


@app.get("/health/live", tags=["Saúde"], summary="Verifica se o processo está ativo")
def health_live():
    return {"status": "ok", "service": "api-catalogo"}


@app.get("/health/ready", tags=["Saúde"], summary="Verifica a conexão com o MongoDB")
def health_ready(collection: Collection = Depends(get_components_collection)):
    try:
        collection.database.command("ping")
    except PyMongoError:
        raise HTTPException(status_code=503, detail="MongoDB indisponível")
    return {"status": "ready", "service": "api-catalogo"}


@app.get("/health", tags=["Saúde"], summary="Health check compatível")
def health():
    return health_live()


def _validate_proxy_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URL de imagem não permitida")
    if hostname != "mlstatic.com" and not hostname.endswith(".mlstatic.com"):
        raise HTTPException(status_code=400, detail="Host de imagem não permitido")
    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail="Host de imagem inválido") from exc
    if not addresses:
        raise HTTPException(status_code=400, detail="Host de imagem inválido")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise HTTPException(status_code=400, detail="Endereço de imagem não permitido")
    return url


def _download_image(url: str, config: Settings) -> tuple[bytes, str]:
    current_url = url
    for redirect_count in range(4):
        _validate_proxy_url(current_url)
        try:
            response = proxy_session.get(
                current_url,
                allow_redirects=False,
                stream=True,
                timeout=(config.proxy_connect_timeout, config.proxy_read_timeout),
            )
        except requests.RequestException as exc:
            raise HTTPException(status_code=404, detail="Imagem não disponível") from exc

        with response:
            if response.is_redirect or response.is_permanent_redirect:
                if redirect_count == 3 or not response.headers.get("location"):
                    raise HTTPException(status_code=400, detail="Redirecionamento de imagem inválido")
                current_url = urljoin(current_url, response.headers["location"])
                continue
            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                raise HTTPException(status_code=404, detail="Imagem não disponível") from exc

            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            allowed_image_types = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
            if content_type not in allowed_image_types:
                raise HTTPException(status_code=400, detail="Conteúdo não é imagem")
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > config.proxy_max_bytes:
                        raise HTTPException(status_code=413, detail="Imagem excede o tamanho permitido")
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail="Tamanho de imagem inválido") from exc

            body = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                body.extend(chunk)
                if len(body) > config.proxy_max_bytes:
                    raise HTTPException(status_code=413, detail="Imagem excede o tamanho permitido")
            if not body:
                raise HTTPException(status_code=404, detail="Imagem vazia")
            return bytes(body), content_type
    raise HTTPException(status_code=400, detail="Redirecionamento de imagem inválido")


@app.get("/images/proxy", tags=["Catálogo"], summary="Obtém imagem permitida do Mercado Livre")
def proxy_image(url: str = Query(..., max_length=2048), config: Settings = Depends(get_settings)):
    content, content_type = _download_image(url, config)
    return Response(content=content, media_type=content_type)


@app.post("/components", response_model=schemas.Component, status_code=201, tags=["Administração"])
def create_component(
    component: schemas.ComponentCreate,
    _: None = Depends(require_admin),
    collection: Collection = Depends(get_components_collection),
):
    try:
        return services.create_component(collection, component.model_dump(mode="json"))
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Peça já cadastrada") from exc


@app.get('/components/resolve-human', tags=['Catálogo'])
def resolve_human_components(
    category: str = Query(..., max_length=32),
    q: str = Query(..., min_length=1, max_length=300),
    collection: Collection = Depends(get_components_collection),
):
    from catalog_specs.human_input import parse_input
    from catalog_specs.human_resolver import mongo_bundle
    parsed = parse_input(q, category)
    result = mongo_bundle(collection, parsed) if not parsed['errors'] else {'candidates': [], 'overflow': False, 'family': None}
    result['candidates'] = [{**row, 'prices': [], 'price_history': []} for row in result['candidates']]
    return result


@app.get('/components/resolve', response_model=list[schemas.Component], tags=['Catálogo'])
def resolve_components(
    category: str = Query(..., max_length=32),
    q: str = Query(..., min_length=1, max_length=300),
    collection: Collection = Depends(get_components_collection),
):
    from catalog_specs.lookup import lookup_mongo
    # Technical lookup does not fan out into price-history or Telegram collections.
    return [{**row, 'prices': [], 'price_history': []} for row in lookup_mongo(collection, category, q)]


@app.get("/components", response_model=list[schemas.Component], tags=["Catálogo"])
def read_components(
    category: str | None = Query(default=None, max_length=120),
    q: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1),
    technical_only: bool = Query(default=False),
    collection: Collection = Depends(get_components_collection),
    config: Settings = Depends(get_settings),
):
    if q and len(q) > config.max_search_length:
        raise HTTPException(status_code=422, detail="Busca excede o tamanho permitido")
    if brand and len(brand) > config.max_search_length:
        raise HTTPException(status_code=422, detail="Marca excede o tamanho permitido")
    if limit is not None and limit > config.max_page_size:
        raise HTTPException(status_code=422, detail=f"limit deve ser no máximo {config.max_page_size}")
    effective_limit = config.max_page_size if limit is None else limit
    rows = services.list_components(
        collection,
        category=category,
        q=q,
        brand=brand,
        skip=skip,
        limit=effective_limit,
        technical_only=technical_only,
    )
    if technical_only:
        # Light technical view for the AI: not a full Component (no image/description), so it bypasses that model.
        return JSONResponse(jsonable_encoder(rows))
    return rows


@app.post("/components/batch", response_model=list[schemas.Component], tags=["Catálogo"])
def read_components_batch(
    payload: schemas.ComponentBatchRequest,
    collection: Collection = Depends(get_components_collection),
    config: Settings = Depends(get_settings),
):
    component_ids = list(dict.fromkeys(payload.component_ids))
    if len(component_ids) > config.max_batch_size:
        raise HTTPException(status_code=422, detail=f"Máximo de {config.max_batch_size} IDs por lote")
    if any(not component_id or len(component_id) > 120 for component_id in component_ids):
        raise HTTPException(status_code=422, detail="ID de componente inválido")
    return services.get_components_batch(collection, component_ids)


@app.get("/components/{component_id}", response_model=schemas.Component, tags=["Catálogo"])
def read_component(component_id: str, collection: Collection = Depends(get_components_collection)):
    component = services.get_component(collection, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    return component


@app.put("/components/{component_id}", response_model=schemas.Component, tags=["Administração"])
def update_component(
    component_id: str,
    component_update: schemas.ComponentUpdate,
    _: None = Depends(require_admin),
    collection: Collection = Depends(get_components_collection),
):
    if not services.get_component(collection, component_id):
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    return services.update_component(collection, component_id, component_update.model_dump(exclude_unset=True, mode="json"))


@app.delete("/components/{component_id}", response_model=schemas.Component, tags=["Administração"])
def delete_component(
    component_id: str,
    _: None = Depends(require_admin),
    collection: Collection = Depends(get_components_collection),
):
    component = services.delete_component(collection, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    return component


def _component_or_404(collection: Collection, component_id: str) -> dict:
    component = services.get_component(collection, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    return component


@app.get("/components/{component_id}/prices", tags=["Preços"])
def read_prices(component_id: str, collection: Collection = Depends(get_components_collection)):
    component = _component_or_404(collection, component_id)
    return {"component_id": component_id, "prices": component.get("prices", [])}


@app.get("/components/{component_id}/best-price", tags=["Preços"])
def read_best_price(component_id: str, collection: Collection = Depends(get_components_collection)):
    component = _component_or_404(collection, component_id)
    price = services.best_price(component)
    if not price:
        raise HTTPException(status_code=404, detail="Peça sem preços")
    return {"component_id": component_id, "best_price": price}


@app.get("/components/{component_id}/price-summary", tags=["Preços"])
def read_price_summary(component_id: str, collection: Collection = Depends(get_components_collection)):
    return services.price_summary(_component_or_404(collection, component_id))


@app.get("/components/{component_id}/price-history", tags=["Preços"])
def read_price_history(component_id: str, collection: Collection = Depends(get_components_collection)):
    component = _component_or_404(collection, component_id)
    return {"component_id": component_id, "history": component.get("price_history", []), "source": "real_observations"}


@app.post("/seed", tags=["Administração"])
def seed(_: None = Depends(require_admin)):
    return {"status": "ok", "inserted": seed_components()}


@app.post("/components/{component_id}/sync-ml-price", tags=["Preços"])
def sync_ml_price(
    component_id: str,
    _: dict = Depends(get_current_user),
    collection: Collection = Depends(get_components_collection),
    config: Settings = Depends(get_settings),
):
    component = _component_or_404(collection, component_id)
    result = refresh_cache.get_or_refresh(
        component_id,
        config.refresh_cooldown_seconds,
        lambda: ml_service.refresh_component_real_prices(component, collection),
    )
    return {"ml_price": result.get("summary", {}).get("best_offer"), **result}


@app.post("/components/{component_id}/refresh-real-prices", tags=["Preços"])
def refresh_real_prices(
    component_id: str,
    _: dict = Depends(get_current_user),
    collection: Collection = Depends(get_components_collection),
    config: Settings = Depends(get_settings),
):
    component = _component_or_404(collection, component_id)
    return refresh_cache.get_or_refresh(
        component_id,
        config.refresh_cooldown_seconds,
        lambda: ml_service.refresh_component_real_prices(component, collection),
    )


@app.post("/components/sync-ml-prices", tags=["Administração"])
def sync_all_ml_prices(
    _: None = Depends(require_admin),
    collection: Collection = Depends(get_components_collection),
):
    return {"status": "ok", **ml_service.sync_all_components(collection)}


@app.get('/promotions', tags=['Comércio'])
def public_promotions(status: str = Query('active', pattern='^(active|recent|all)$'), component_id: str | None = None,
                      category: str | None = None, source: str | None = None, limit: int = Query(12, ge=1, le=100),
                      skip: int = Query(0, ge=0), collection: Collection = Depends(get_components_collection)):
    import commerce
    data = commerce.snapshot(collection.database)
    rows = [p for p in data['promotions'] if (status != 'active' or p['state'] == 'active')
            and (status != 'recent' or p['state'] != 'active') and (not component_id or p['component_id'] == component_id)
            and (not category or p['category'] == category or (category == 'ram' and p['category'] == 'kit-ram'))
            and (not source or p['source'] == source)]
    return {'items': rows[skip:skip+limit], 'total': len(rows), 'counts': data['counts'], 'refresh_seconds': 45}


@app.get('/components/{component_id}/offers', tags=['Comércio'])
def component_offers(component_id: str, collection: Collection = Depends(get_components_collection)):
    import commerce
    data = commerce.snapshot(collection.database)
    if component_id not in {c['id'] for c in data['components']}:
        raise HTTPException(404, 'Peça não encontrada')
    rows = data['offers'].get(component_id, [])
    return {'component_id': component_id, 'best_offer': data['best'].get(component_id), 'offers': rows,
            'best_general_offer': data['best_general'].get(component_id),
            'best_conditional_offer': data['best_conditional'].get(component_id),
            'history': data['history'].get(component_id, [])[:100]}


@app.post('/promotions/{promotion_id}/validation', tags=['Comércio'])
def validate_promotion(promotion_id: str, body: schemas.OfferValidation, user: dict = Depends(get_current_user),
                       collection: Collection = Depends(get_components_collection)):
    """Record a person's check ("works" / "no longer works"). Nothing is deleted: an invalid offer leaves current offers."""
    import commerce
    from bson import ObjectId
    from bson.errors import InvalidId
    database = collection.database
    row = next((r for r in commerce.snapshot(database)['promotions'] if r['id'] == promotion_id), None)
    if row is None:
        raise HTTPException(404, 'Promoção não encontrada')
    try:
        ids = [ObjectId(i) for i in [promotion_id, *row.get('merged_ids', [])]]
    except InvalidId:
        raise HTTPException(404, 'Promoção não encontrada')
    now = datetime.now(timezone.utc).isoformat()
    status = {'working': 'valid', 'not_working': 'invalid'}.get(body.status, body.status)
    if status == 'unknown':
        update = {'$unset': {'offer.manual_validation_status': '', 'offer.manual_validated_at': '', 'offer.manual_validated_by': ''}}
    else:
        fields = {'offer.manual_validation_status': status, 'offer.manual_validated_at': now,
                  'offer.manual_validated_by': str(user.get('sub'))}
        if body.observed_price:
            fields.update({'offer.verified_price': body.observed_price, 'offer.verification_source': 'manual', 'offer.verified_at': now})
        update = {'$set': fields}
    database['telegram_promotions'].update_many({'_id': {'$in': ids}}, update)
    if status == 'invalid' or (body.observed_price and abs(body.observed_price - row['price']) / row['price'] > 0.01):
        # The observation stays for audit but stops counting as a real, usable price.
        for doc in database['telegram_promotions'].find({'_id': {'$in': ids}}, {'telegram.chat_id': 1, 'telegram.message_id': 1}):
            chat_id, message_id = (doc.get('telegram') or {}).get('chat_id'), (doc.get('telegram') or {}).get('message_id')
            if chat_id is None or message_id is None:
                continue
            database['product_price_history'].update_many(
                {'telegram.chat_id': chat_id, 'telegram.message_id': message_id},
                {'$set': {'verified': False, 'invalidated_by': 'manual_validation'}})
    commerce._cache.clear()
    updated = next((r for r in commerce.snapshot(database)['promotions'] if r['id'] == promotion_id), None)
    return {'id': promotion_id, 'manual_validation_status': None if status == 'unknown' else status,
            'status': updated['status'] if updated else None, 'state': updated['state'] if updated else None,
            'updated_documents': len(ids)}


@app.get('/commerce/catalog', tags=['Comércio'])
def commerce_catalog(q: str = Query('', max_length=120), category: str = '',
                     skip: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100),
                     collection: Collection = Depends(get_components_collection)):
    """Lightweight paginated COMMERCIAL catalog straight from MongoDB (Telegram-matched or accepted Mercado Livre components only).

    Deliberately does NOT build the commerce snapshot (matcher over every component, promotions, history):
    offers are served separately by /promotions and /components/{id}/offers, so cards here carry no offers.
    """
    # Commercial catalog only: the technical base (BuildCores / PC Part Dataset) is never listed without commercial evidence.
    promoted_ids = [cid for cid in collection.database['telegram_promotions'].distinct(
        'product.component_id', {'is_demo': {'$ne': True}, 'product.match_level': 'high', 'offer.price': {'$ne': None}}) if cid]
    conditions: list[dict] = [{'$or': [
        {'id': {'$in': promoted_ids}},
        {'external_enrichment.mercado_livre.match_status': 'matched', 'external_enrichment.mercado_livre.external_conflict': {'$ne': True}}]}]
    if category:
        conditions.append({'category': {'$in': ['ram', 'kit-ram']} if category == 'ram' else category})
    if q.strip():
        pattern = re.escape(q.strip())
        conditions.append({'$or': [{f: {'$regex': pattern, '$options': 'i'}} for f in ('name', 'brand', 'description')]})
    query = {'$and': conditions}
    projection = {'_id': 0, **{f: 1 for f in ('id', 'name', 'category', 'brand', 'description', 'image', 'images',
                                               'technical_specs', 'compatibility', 'external_enrichment')}}
    rows = [{**doc, 'prices': [], 'current_offers': [], 'best_current_offer': None, 'best_general_offer': None,
             'best_conditional_offer': None, 'offers_count': 0}
            for doc in collection.find(query, projection).sort('_id', 1).skip(skip).limit(limit)]
    return {'items': rows, 'total': collection.count_documents(query), 'skip': skip, 'limit': limit}


@app.get('/integrations/mercado-livre/status', tags=['Comércio'])
def mercado_livre_status(collection: Collection = Depends(get_components_collection)):
    """Safe integration status: what works (Product API), what is restricted (Item API) and the counters. Never a token."""
    import ml_products
    from ml_commerce import client
    return {**client.public_status(), **ml_products.integration_status(ml_products.tokens, collection.database)}


import demo  # noqa: E402

demo.install(app)  # DEMO_MODE=true: read-only guard + /demo/* endpoints
