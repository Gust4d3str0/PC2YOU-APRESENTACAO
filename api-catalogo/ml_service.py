import sys
from pathlib import Path

_shared = Path(__file__).resolve().parents[1] / 'services'
if _shared.is_dir():
    sys.path.append(str(_shared))
from product_matching import compare_product
from product_matching.quality import equivalence_key, money, offer_url, price_quality

import os
import re
import unicodedata
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import services
from config import get_settings


ML_SITE_SEARCH_URL = "https://api.mercadolibre.com/sites/MLB/search"
ML_PRODUCTS_SEARCH_URL = "https://api.mercadolibre.com/products/search"
ML_ITEMS_MULTIGET_URL = "https://api.mercadolibre.com/items/bulk"
ML_ITEM_DETAIL_URL = "https://api.mercadolibre.com/items/{item_id}"
ML_PRODUCT_DETAIL_URL = "https://api.mercadolibre.com/products/{product_id}"
ML_PRODUCT_ITEMS_URL = "https://api.mercadolibre.com/products/{product_id}/items"

DEFAULT_LIMIT = 20
MAX_USED_OFFERS = 8
MAX_CATALOG_PRODUCTS_USED = 8

_retry_policy = Retry(
    total=2,
    connect=2,
    read=2,
    status=2,
    allowed_methods=frozenset({"GET"}),
    status_forcelist=(429, 500, 502, 503, 504),
    backoff_factor=0.3,
    respect_retry_after_header=True,
    raise_on_status=False,
)
ML_SESSION = requests.Session()
ML_SESSION.mount("https://", HTTPAdapter(max_retries=_retry_policy))

CATEGORY_PREFIX = {
    "cpu": "processador",
    "motherboard": "placa mae",
    "ram": "memoria ram",
    "kit-ram": "kit memoria ram",
    "storage": "ssd",
    "gpu": "placa de video",
    "psu": "fonte",
    "case": "gabinete",
    "cooler": "cooler processador",
}

EXCLUDED_TERMS = [
    "suporte",
    "cabo",
    "adaptador",
    "backplate",
    "fan",
    "ventoinha",
    "cooler para",
    "defeito",
    "usado",
    "semi novo",
    "seminovo",
    "caixa vazia",
    "apenas caixa",
    "pelicula",
    "película",
    "parafuso",
    "conector",
    "miniatura",
    "adesivo",
    "case para",
    "protector",
    "protetor",
]

RAM_EXCLUDED_TERMS = [
    "notebook",
    "sodimm",
    "so dimm",
    "servidor",
    "server",
    "ecc",
    "registrada",
    "registered",
    "rdimm",
    "udimm ecc",
]


class MercadoLivreError(RuntimeError):
    pass


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _has_term(clean_title: str, term: str) -> bool:
    clean_term = normalize_text(term)
    if not clean_term:
        return True
    return clean_term in clean_title or clean_term.replace(" ", "") in clean_title.replace(" ", "")


def _unique_terms(terms: list[str]) -> list[str]:
    seen = set()
    result = []
    for term in terms:
        clean = normalize_text(term)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _spec(component: dict, *keys: str) -> str:
    specs = component.get("technical_specs") or {}
    compatibility = component.get("compatibility") or {}
    for key in keys:
        value = specs.get(key)
        if value is None:
            value = compatibility.get(key)
        if value is not None:
            return str(value)
    return ""


def _storage_capacity_label(component: dict) -> str:
    value = _spec(component, "capacity")
    if value:
        return value.upper().replace(" ", "")

    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(tb|gb)", component.get("name", ""), re.IGNORECASE)
    if not match:
        return ""
    number = match.group(1).replace(",", ".")
    unit = match.group(2).upper()
    return f"{number}{unit}"


def _build_storage_search_query(component: dict) -> str:
    capacity = _storage_capacity_label(component)
    interface_text = normalize_text(f"{component.get('name', '')} {_spec(component, 'interface')}")

    if "nvme" in interface_text:
        return " ".join(part for part in ["SSD", "NVMe", capacity, "M.2"] if part)
    if "sata" in interface_text:
        return " ".join(part for part in ["SSD", "SATA", capacity] if part)
    if "hdd" in interface_text or normalize_text(component.get("name", "")).startswith("hd "):
        return " ".join(part for part in ["HD", capacity] if part)
    return " ".join(part for part in ["SSD", capacity] if part)


def _build_ram_search_query(component: dict) -> str:
    name = component.get("name", "").strip()
    brand = component.get("brand", "").strip()
    clean_name = normalize_text(name)
    query_name = name
    if brand and normalize_text(brand) not in clean_name:
        query_name = f"{brand} {name}".strip()

    terms = [query_name]
    clean_query = normalize_text(query_name)
    for term in [_spec(component, "modules"), _spec(component, "capacity"), _spec(component, "memory_type"), _spec(component, "speed")]:
        if term and not _has_term(clean_query, term):
            terms.append(term)
    return " ".join(_unique_terms(terms))


def build_search_query(component: dict) -> str:
    category = component.get("category", "")
    name = component.get("name", "")
    brand = component.get("brand", "")
    if category == "storage":
        return build_search_query_storage(component)
    if category in {"ram", "kit-ram"}:
        return _build_ram_search_query(component)

    terms = [CATEGORY_PREFIX.get(category, ""), name]

    if category == "psu":
        wattage = _spec(component, "wattage")
        terms.extend([f"{wattage}w" if wattage and wattage.isdigit() else wattage, _spec(component, "efficiency")])
    elif category == "motherboard":
        terms.extend([
            _spec(component, "chipset"),
            _spec(component, "socket"),
            _spec(component, "memory_type"),
        ])

    if category in {"cpu", "gpu"}:
        terms.append(brand)

    return " ".join(_unique_terms(terms))


def build_search_query_storage(component: dict) -> str:
    return _build_storage_search_query(component)


def _catalog_text(product: dict) -> str:
    parts = [
        product.get("name", ""),
        product.get("family_name", ""),
        product.get("domain_id", ""),
    ]
    for attribute in product.get("attributes", []) or []:
        parts.append(attribute.get("value_name") or "")
        for value in attribute.get("values", []) or []:
            parts.append(value.get("name") or "")
    return " ".join(str(part) for part in parts if part)


def is_relevant_catalog_product(component: dict, product: dict) -> bool:
    if product.get("status") and product.get("status") != "active":
        return False

    domain_id = normalize_text(product.get('domain_id', ''))
    if component.get('category') == 'gpu' and domain_id and 'graphics cards' not in domain_id:
        return False
    result = compare_product({'title': _catalog_text(product), 'category': component.get('category')}, component)
    return result.matched and result.confidence_level == 'high'


def _reference_price(component: dict) -> float | None:
    prices = []
    for item in component.get("prices", []):
        if item.get("source") == "mercado_livre" or item.get("store") == "Mercado Livre":
            continue
        price = item.get("price")
        if isinstance(price, (int, float)) and price > 0:
            prices.append(float(price))
    if not prices:
        return None
    return sum(prices) / len(prices)


def is_price_reasonable(price: float, reference_price: float | None, category: str | None = None) -> bool:
    if not reference_price:
        return True
    if category in {"ram", "kit-ram"}:
        lower, upper = 0.35, 5.5
    elif category == "storage":
        lower, upper = 0.35, 3.5
    elif reference_price >= 10000:
        lower, upper = 0.4, 2.2
    else:
        lower, upper = 0.5, 1.8
    return reference_price * lower <= price <= reference_price * upper


def is_relevant_offer(component: dict, offer: dict) -> bool:
    title = normalize_text(offer.get("title", "") or offer.get("name", ""))
    if not title:
        return False

    for term in EXCLUDED_TERMS:
        if _has_term(title, term):
            return False

    price = offer.get("price")
    if money(price) is None:
        return False
    if not is_price_reasonable(float(price), _reference_price(component), component.get("category")):
        return False

    result = compare_product({'title': offer.get('title') or offer.get('name'), 'category': component.get('category'),
                              'brand': offer.get('brand'), 'attributes': offer.get('attributes') or {}}, component)
    return result.matched and result.confidence_level == 'high'


def _ml_token() -> str:
    return os.getenv("MERCADO_LIVRE_ACCESS_TOKEN", "").strip()


def _ml_headers() -> dict:
    token = _ml_token()
    if not token:
        raise MercadoLivreError("MERCADO_LIVRE_ACCESS_TOKEN não configurado.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }


def _request_json(url: str, params: dict | None = None) -> tuple[int, dict | list | None, str]:
    from ml_commerce import client, MLUnavailable
    from urllib.parse import urlsplit
    try:
        path = urlsplit(url).path
        code, payload = client.get(path, params, ttl=10800 if path.startswith('/products') and not path.endswith('/items') else 180)
        return code, payload, 'Mercado Livre temporariamente indisponível' if code != 200 else ''
    except MLUnavailable as exc:
        raise MercadoLivreError(str(exc)) from exc


def search_ml_catalog_products(component: dict, limit: int = DEFAULT_LIMIT) -> dict:
    query = _spec(component, 'part_number', 'sku', 'model') or build_search_query(component)
    params = {
        "site_id": "MLB",
        "q": query,
        "status": "active",
        "limit": limit,
    }
    status_code, payload, raw_text = _request_json(ML_PRODUCTS_SEARCH_URL, params=params)

    if status_code in {401, 403}:
        raise MercadoLivreError(
            f"Mercado Livre retornou {status_code} em /products/search. "
            "Token recebido, mas a API recusou a consulta."
        )
    if status_code >= 400:
        raise MercadoLivreError(
            f"Erro em /products/search. Status: {status_code}. Resposta: {raw_text}"
        )

    results = payload.get("results", []) if isinstance(payload, dict) else []
    return {
        "query": query,
        "status_code": status_code,
        "raw_count": len(results),
        "products": results,
    }


def _extract_items(payload: dict | list | None) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ["results", "items", "seller_items"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    if payload.get("id") or payload.get("item_id") or payload.get("price"):
        return [payload]

    return []


def fetch_catalog_product_items(product_id: str) -> dict:
    status_code, payload, raw_text = _request_json(ML_PRODUCT_ITEMS_URL.format(product_id=product_id))
    items = _extract_items(payload) if status_code == 200 else []
    return {
        "product_id": product_id,
        "status_code": status_code,
        "items": items,
        "error": None if status_code == 200 else raw_text,
    }


def fetch_catalog_product_detail(product_id: str) -> dict:
    status_code, payload, raw_text = _request_json(ML_PRODUCT_DETAIL_URL.format(product_id=product_id))
    product = payload if status_code == 200 and isinstance(payload, dict) else None
    return {
        "product_id": product_id,
        "status_code": status_code,
        "product": product,
        "error": None if status_code == 200 else raw_text,
    }


def _candidate_item_id(candidate: dict) -> str | None:
    for key in ["id", "item_id"]:
        value = candidate.get(key)
        if isinstance(value, str) and value.startswith("MLB"):
            return value
    return None


def _body_from_multiget_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    if item.get("code") == 200 and isinstance(item.get("body"), dict):
        return item["body"]
    if item.get("id") or item.get("price"):
        return item
    return None


def fetch_items_multiget(item_ids: list[str]) -> dict:
    ids = list(dict.fromkeys(item_ids))
    if not ids:
        return {"status_code": None, "items": []}

    status_code, payload, raw_text = _request_json(
        ML_ITEMS_MULTIGET_URL,
        params={
            "ids": ",".join(ids[:20]),
            "attributes": "id,title,price,permalink,thumbnail,pictures,status,condition,seller_id,available_quantity,catalog_product_id",
        },
    )
    if status_code >= 400:
        return {"status_code": status_code, "items": [], "error": raw_text}

    items = []
    if isinstance(payload, list):
        items = [body for body in (_body_from_multiget_item(item) for item in payload) if body]
    elif isinstance(payload, dict):
        body = _body_from_multiget_item(payload)
        items = [body] if body else []

    return {"status_code": status_code, "items": items}


def fetch_item_detail(item_id: str) -> dict:
    status_code, payload, raw_text = _request_json(
        ML_ITEM_DETAIL_URL.format(item_id=item_id),
        params={
            "attributes": "id,title,price,permalink,thumbnail,pictures,status,condition,seller_id,available_quantity,catalog_product_id",
        },
    )
    item = payload if status_code == 200 and isinstance(payload, dict) else None
    return {
        "item_id": item_id,
        "status_code": status_code,
        "item": item,
        "error": None if status_code == 200 else raw_text,
    }


def _merge_item_data(candidate: dict, detail: dict | None) -> dict:
    if not detail:
        return candidate
    merged = dict(candidate)
    for key, value in detail.items():
        if value not in (None, "", []):
            merged[key] = value
    return merged


def _enrich_item_candidate(candidate: dict) -> dict:
    item_id = _candidate_item_id(candidate)
    if not item_id:
        return candidate

    has_real_url = bool(candidate.get("permalink")) and candidate.get("permalink") != "https://www.mercadolivre.com.br/"
    if has_real_url and candidate.get("title") and candidate.get("price"):
        return candidate

    detail = fetch_item_detail(item_id)
    return _merge_item_data(candidate, detail.get("item"))


def _extract_image_urls(*sources: dict | None) -> list[str]:
    urls = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        for picture in source.get("pictures", []) or []:
            if not isinstance(picture, dict):
                continue
            url = picture.get("secure_url") or picture.get("url")
            if url:
                urls.append(url)
        thumbnail = source.get("thumbnail")
        if thumbnail:
            urls.append(thumbnail)
    return list(dict.fromkeys(urls))


def _offer_from_item(item: dict, component: dict, product: dict | None = None) -> dict | None:
    body = item.get("body") if isinstance(item.get("body"), dict) else item
    price = body.get("price")
    if money(price) is None:
        return None
    if body.get("status") and body.get("status") != "active":
        return None
    if body.get("condition") and body.get("condition") != "new":
        return None

    title = body.get("title") or body.get("name") or (product or {}).get("name") or "Oferta Mercado Livre"
    attributes = {a.get('id', '').lower(): a.get('value_name') for a in body.get('attributes', []) if isinstance(a, dict)}
    brand = attributes.pop('brand', None)
    offer_probe = {'title': title, 'price': price, 'brand': brand, 'attributes': attributes}
    if not is_relevant_offer(component, offer_probe):
        return None

    available_quantity = body.get("available_quantity")
    product_id = body.get("catalog_product_id") or (product or {}).get("id") or (product or {}).get("catalog_product_id")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    external_id = body.get("id") or body.get("item_id") or ""
    url = body.get("permalink") or (product or {}).get("permalink") or ""
    if url == "https://www.mercadolivre.com.br/":
        url = ""
    url = offer_url(url) or ''
    image_urls = _extract_image_urls(body, product)
    thumbnail = image_urls[0] if image_urls else ""

    match = compare_product({**offer_probe, 'category': component.get('category')}, component)
    quality = price_quality({'price': price, 'url': url, 'last_update': now,
                             'availability': 'Disponível' if available_quantity is None or available_quantity > 0 else 'Indisponível',
                             'url_source': 'marketplace_api' if url else 'unknown'}, match, source='mercado_livre')
    return {
        'product_match': match.to_dict(), 'quality': quality, 'brand': brand, 'attributes': attributes,
        'url_source': quality['url_source'],
        'equivalence_key': equivalence_key(component.get('id'), {'price': price, 'store': 'Mercado Livre', 'url': url}),
        "store": "Mercado Livre",
        "title": title,
        "price": float(price),
        "url": url,
        "thumbnail": thumbnail,
        "images": image_urls,
        "last_update": now,
        "source": "mercado_livre",
        "availability": "Disponível" if available_quantity is None or available_quantity > 0 else "Indisponível",
        "external_id": external_id,
        "condition": body.get("condition") or "new",
        "seller": str(body.get("seller_id") or body.get("seller", {}).get("id") or ""),
        "catalog_product_id": product_id or "",
    }


def _item_candidates_from_product_detail(detail: dict) -> list[dict]:
    product = detail.get("product") or {}
    candidates = []
    buy_box_winner = product.get("buy_box_winner")
    if isinstance(buy_box_winner, dict):
        candidates.append(buy_box_winner)
    if product.get("price"):
        candidates.append(product)
    return candidates


def fetch_mercado_livre_offers(component: dict) -> list[dict]:
    return fetch_mercado_livre_offers_with_stats(component)["offers"]


def fetch_mercado_livre_offers_with_stats(component: dict) -> dict:
    catalog = search_ml_catalog_products(component)
    raw_products = catalog["products"]
    relevant_products = [
        product
        for product in raw_products
        if is_relevant_catalog_product(component, product)
    ]
    used_products = relevant_products[:MAX_CATALOG_PRODUCTS_USED]

    offers_by_id = {}
    diagnostics = []
    raw_offer_candidates = 0

    for product in used_products:
        product_id = product.get("id") or product.get("catalog_product_id")
        if not product_id:
            continue

        detail = fetch_catalog_product_detail(product_id)
        product_for_offer = detail.get("product") or product
        detail_candidates = _item_candidates_from_product_detail(detail)

        items_result = fetch_catalog_product_items(product_id)
        item_candidates = detail_candidates + items_result.get("items", [])

        item_ids = [
            item_id
            for item_id in (_candidate_item_id(candidate) for candidate in item_candidates)
            if item_id
        ]
        multiget = fetch_items_multiget(item_ids)
        item_candidates.extend(multiget.get("items", []))
        item_candidates = [_enrich_item_candidate(candidate) for candidate in item_candidates]

        raw_offer_candidates += len(item_candidates)
        diagnostics.append(
            {
                "product_id": product_id,
                "product_name": product.get("name"),
                "items_status": items_result.get("status_code"),
                "detail_status": detail.get("status_code"),
                "multiget_status": multiget.get("status_code"),
                "candidates": len(item_candidates),
            }
        )

        for candidate in item_candidates:
            from ml_commerce import client, MercadoLivrePriceService
            current_price = MercadoLivrePriceService(client).current(_candidate_item_id(candidate))
            if not current_price:
                continue
            candidate = {**candidate, **current_price}
            offer = _offer_from_item(candidate, component, product_for_offer)
            if offer:
                offer.update({k: current_price[k] for k in ('currency', 'valid_until', 'regular_price')})
            if not offer:
                continue
            key = offer.get("external_id") or f"{offer['catalog_product_id']}:{offer['price']}"
            offers_by_id[key] = offer

    offers = sorted(offers_by_id.values(), key=lambda item: item["price"])
    selected = offers[:MAX_USED_OFFERS]

    rejected_samples = [
        product.get("name", "")
        for product in raw_products
        if not is_relevant_catalog_product(component, product)
    ][:5]
    relevant_samples = [product.get("name", "") for product in relevant_products[:5]]

    external_error = None
    if not raw_products:
        external_error = "Token válido, mas o Mercado Livre não retornou produtos de catálogo para esta busca."
    elif not relevant_products:
        external_error = "Token válido, mas nenhum produto de catálogo relevante corresponde exatamente ao componente."
    elif not selected:
        external_error = (
            "Encontramos produtos no catálogo do Mercado Livre, mas nenhuma oferta com preço foi liberada pela API. "
            "Mantivemos os preços demonstrativos."
        )

    return {
        "query": catalog["query"],
        "strategy": "products_search",
        "catalog_products_found": catalog["raw_count"],
        "catalog_products_used": len(used_products),
        "offers_found": len(offers),
        "offers_used": len(selected),
        "offers_discarded": max(raw_offer_candidates - len(selected), 0),
        "external_error": external_error,
        "debug_samples": rejected_samples or relevant_samples,
        "product_diagnostics": diagnostics,
        "offers": selected,
    }


def _merge_prices(component: dict, ml_prices: list[dict]) -> list[dict]:
    local_prices = [
        price
        for price in component.get("prices", [])
        if price.get("source") != "mercado_livre" and price.get("store") != "Mercado Livre"
    ]
    return local_prices + ml_prices


def _image_update_from_offers(ml_prices: list[dict]) -> dict:
    for offer in ml_prices:
        images = [url for url in offer.get("images", []) if url]
        if offer.get("thumbnail"):
            images.append(offer["thumbnail"])
        images = list(dict.fromkeys(images))
        if not images:
            continue
        return {
            "real_image": images[0],
            "image_source": "mercado_livre",
            "image_external_id": offer.get("external_id", ""),
            "images": images,
        }
    return {}


def _failed_refresh_payload(component: dict, collection, now: str, query: str, error: str) -> dict:
    component_id = component.get("id")
    snapshot = services.build_price_snapshot(component, date_value=now, external_status="failed")
    history = services.upsert_price_snapshot(component.get("price_history", []), snapshot) if snapshot else component.get("price_history", [])
    collection.update_one(
        {"id": component_id},
        {
            "$set": {
                "price_history": history,
                "last_external_price_update": now,
                "last_external_price_status": "failed",
                "last_external_price_error": error,
                "last_external_price_strategy": "products_search",
            }
        },
    )
    return {
        "component_id": component_id,
        "updated_external": False,
        "query": query,
        "strategy": "products_search",
        "catalog_products_found": 0,
        "catalog_products_used": 0,
        "offers_found": 0,
        "offers_used": 0,
        "offers_discarded": 0,
        "external_error": error,
        "debug_samples": [],
        "summary": services.price_summary(component),
        "snapshot": snapshot,
        "history": history,
    }


def refresh_component_real_prices(component: dict, collection) -> dict:
    component_id = component.get("id")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    query = build_search_query(component)

    try:
        fetched = fetch_mercado_livre_offers_with_stats(component)
    except MercadoLivreError as exc:
        return _failed_refresh_payload(component, collection, now, query, str(exc))

    ml_prices = fetched["offers"]
    if not ml_prices:
        snapshot = services.build_price_snapshot(component, date_value=now, external_status="no_real_offers")
        history = services.upsert_price_snapshot(component.get("price_history", []), snapshot) if snapshot else component.get("price_history", [])
        collection.update_one(
            {"id": component_id},
            {
                "$set": {
                    "price_history": history,
                    "last_external_price_update": now,
                    "last_external_price_status": "no_real_offers",
                    "last_external_price_error": fetched["external_error"],
                    "last_external_price_strategy": fetched["strategy"],
                }
            },
        )
        return {
            "component_id": component_id,
            "updated_external": False,
            **{key: fetched[key] for key in (
                "query",
                "strategy",
                "catalog_products_found",
                "catalog_products_used",
                "offers_found",
                "offers_used",
                "offers_discarded",
                "external_error",
                "debug_samples",
            )},
            "summary": services.price_summary(component),
            "snapshot": snapshot,
            "history": history,
        }

    merged_prices = _merge_prices(component, ml_prices)
    updated_component = {**component, "prices": merged_prices}
    image_update = _image_update_from_offers(ml_prices)
    if component.get('real_image') and component.get('image_source') != 'mercado_livre':
        image_update = {}
    updated_component.update(image_update)
    snapshot = services.build_price_snapshot(updated_component, date_value=now, external_status="success")
    history = services.upsert_price_snapshot(component.get("price_history", []), snapshot)

    update_data = {
        "prices": merged_prices,
        "price_history": history,
        "last_external_price_update": now,
        "last_external_price_status": "success",
        "last_external_price_error": None,
        "last_external_price_strategy": fetched["strategy"],
    }
    update_data.update(image_update)

    collection.update_one(
        {"id": component_id},
        {"$set": update_data},
    )

    updated_component["price_history"] = history
    return {
        "component_id": component_id,
        "updated_external": True,
        **{key: fetched[key] for key in (
            "query",
            "strategy",
            "catalog_products_found",
            "catalog_products_used",
            "offers_found",
            "offers_used",
            "offers_discarded",
            "external_error",
            "debug_samples",
        )},
        "summary": services.price_summary(updated_component),
        "snapshot": snapshot,
        "history": history,
    }


def sync_component_ml(component: dict, collection) -> dict | None:
    result = refresh_component_real_prices(component, collection)
    if not result.get("updated_external"):
        return None
    offers = [
        price
        for price in result["summary"].get("all_offers", [])
        if price.get("source") == "mercado_livre"
    ]
    return offers[0] if offers else result["summary"].get("best_offer")


def sync_all_components(collection) -> dict:
    components = list(collection.find({}))
    updated, failed = 0, 0

    for comp in components:
        comp.pop("_id", None)
        result = refresh_component_real_prices(comp, collection)
        if result.get("updated_external"):
            updated += 1
        else:
            failed += 1

    return {"total": len(components), "updated": updated, "failed": failed}
