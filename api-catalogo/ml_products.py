"""Mercado Livre Product API (product enrichment) and price capability. Backend only.

Two independent layers:
  1. `/products/{PRODUCT_ID}`  -> official images, specs and auxiliary identity (works today).
  2. `/items/{ITEM_ID}` + prices -> offer validation, ONLY where the API authorises the resource (today: 403 for third parties).

A 403 is a *capability*, never a verdict on an offer. Nothing here scrapes, drives a browser or bypasses a policy.
Tokens stay in this process: they are never logged, returned by an endpoint, or written to a report.
"""
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from product_matching.matcher import HIGH, compare_product
from product_matching.ml_ids import ITEM_ID_RE, PRODUCT_ID_RE
from product_matching.quality import date_value, money

log = logging.getLogger('pc2you.ml.products')
API_BASE = 'https://api.mercadolibre.com'
SOURCE = 'mercado_livre_product_api'
PRICE_SOURCE = 'mercado_livre_api'
COLLECTION = 'external_product_enrichment'
STATE_COLLECTION = 'ml_integration_state'


def _env(env, name):
    return (env.get('ML_' + name) or env.get('MERCADO_LIVRE_' + name) or '').strip()


def cache_ttl_hours(env=None):
    try:
        return float((env or os.environ).get('PC2YOU_ML_PRODUCT_CACHE_TTL_HOURS', 24))
    except ValueError:
        return 24.0


# --- tokens ---------------------------------------------------------------------------------------------

class MercadoLivreTokenManager:
    """Valid access token on demand; rotating refresh token; one refresh at a time; persisted outside `.env`.

    The refresh token rotates: after a refresh the new one replaces the old one on disk and the old one is never used again.
    Refresh is refused when no token file is configured (a rotated token that cannot be persisted would be lost)."""
    REFRESH_COOLDOWN = 60

    def __init__(self, session=None, token_file=None, env=None, clock=time.time):
        self.session = session or requests.Session()
        self.env = env if env is not None else os.environ
        self.clock = clock
        self.lock = threading.RLock()
        path = token_file or _env(self.env, 'TOKEN_FILE')
        self.token_file = Path(path) if path else None
        self.expires_at = None
        self.refresh_blocked_until = 0.0
        self.last_error = None
        self._access = _env(self.env, 'ACCESS_TOKEN')
        self._refresh = _env(self.env, 'REFRESH_TOKEN')
        self._load_file()

    @property
    def _fingerprint(self):
        # Identifies the .env refresh token without storing it: if .env changes (re-authorisation), an older file is ignored.
        return hashlib.sha256(_env(self.env, 'REFRESH_TOKEN').encode()).hexdigest()[:16]

    def _load_file(self):
        if not (self.token_file and self.token_file.is_file()):
            return
        try:
            data = json.loads(self.token_file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        if data.get('env_fingerprint') == self._fingerprint and data.get('access_token') and data.get('refresh_token'):
            self._access, self._refresh, self.expires_at = data['access_token'], data['refresh_token'], data.get('expires_at')

    def _persist(self):
        target = self.token_file
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps({'access_token': self._access, 'refresh_token': self._refresh, 'expires_at': self.expires_at,
                                         'env_fingerprint': self._fingerprint, 'saved_at': self.clock()}), encoding='utf-8')
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(target)

    @property
    def can_refresh(self):
        return bool(self._refresh and _env(self.env, 'CLIENT_ID') and _env(self.env, 'CLIENT_SECRET') and self.token_file)

    def access_token(self):
        with self.lock:
            if self.expires_at and self.expires_at <= self.clock() + 30:
                self.refresh(stale_token=self._access)
            return self._access or None

    def refresh(self, stale_token=None):
        """Renew once. `stale_token`: the token that just failed; if another thread already replaced it, nothing to do."""
        with self.lock:
            if stale_token and self._access and self._access != stale_token:
                return True
            if not self.can_refresh:
                self.last_error = 'refresh_unavailable'
                return False
            if self.clock() < self.refresh_blocked_until:
                return False
            try:
                response = self.session.post(API_BASE + '/oauth/token', timeout=(3, 10), data={
                    'grant_type': 'refresh_token', 'refresh_token': self._refresh,
                    'client_id': _env(self.env, 'CLIENT_ID'), 'client_secret': _env(self.env, 'CLIENT_SECRET')})
                data = response.json() if response.status_code == 200 else {}
            except (requests.RequestException, ValueError):
                data = {}
            if not data.get('access_token') or not data.get('refresh_token'):
                self.refresh_blocked_until = self.clock() + self.REFRESH_COOLDOWN   # no endless renewing
                self.last_error = 'refresh_failed'
                return False
            self._access, self._refresh = data['access_token'], data['refresh_token']
            self.expires_at = self.clock() + float(data.get('expires_in') or 0) if data.get('expires_in') else None
            try:
                self._persist()
                self.last_error = None
            except OSError:
                self.last_error = 'persist_failed'
            log.info('ML token refreshed')
            return True

    def state(self):
        with self.lock:
            return {'configured': bool(self._access or self._refresh), 'refresh_available': self.can_refresh,
                    'expires_at': datetime.fromtimestamp(self.expires_at, timezone.utc).isoformat() if self.expires_at else None,
                    'last_error': self.last_error}


# --- HTTP client ----------------------------------------------------------------------------------------

@dataclass
class ApiResult:
    kind: str                    # ok | not_found | forbidden | unauthorized | rate_limited | server_error | timeout | auth_unavailable | invalid | error
    status: int | None = None
    data: dict | None = None
    reason: str | None = None

    @property
    def ok(self):
        return self.kind == 'ok'


class MercadoLivreApi:
    """Read-only GET client. Never raises; every failure becomes an `ApiResult`."""

    def __init__(self, tokens, session=None, timeout=(3, 10), clock=time.monotonic, on_event=None):
        self.tokens, self.session, self.timeout, self.clock = tokens, session or requests.Session(), timeout, clock
        self.on_event = on_event
        self.blocked_until = 0.0

    def _emit(self, result, path):
        if self.on_event:
            try:
                self.on_event(result, path)
            except Exception:  # metrics must not break a request
                pass
        return result

    def get(self, path, params=None):
        if not isinstance(path, str) or not path.startswith('/') or '..' in path:
            return ApiResult('invalid', reason='bad_path')
        if self.clock() < self.blocked_until:
            return self._emit(ApiResult('rate_limited', 429, reason='backoff'), path)
        token = self.tokens.access_token()
        if not token:
            return self._emit(ApiResult('auth_unavailable', reason='no_token'), path)
        response = None
        for attempt in range(2):                    # a 401 triggers exactly one refresh and one retry
            try:
                response = self.session.get(API_BASE + path, params=params, headers={'Authorization': 'Bearer ' + token}, timeout=self.timeout)
            except requests.Timeout:
                return self._emit(ApiResult('timeout', reason='timeout'), path)
            except requests.RequestException:
                return self._emit(ApiResult('error', reason='network'), path)
            if response.status_code == 401 and attempt == 0:
                if not self.tokens.refresh(stale_token=token):
                    return self._emit(ApiResult('unauthorized', 401, reason='refresh_unavailable'), path)
                token = self.tokens.access_token()
                if not token:
                    return self._emit(ApiResult('unauthorized', 401), path)
                continue
            break
        code = response.status_code
        if code == 200:
            try:
                data = response.json()
            except ValueError:
                return self._emit(ApiResult('invalid', 200, reason='bad_json'), path)
            if not isinstance(data, dict):
                return self._emit(ApiResult('invalid', 200, reason='not_object'), path)
            return self._emit(ApiResult('ok', 200, data), path)
        if code == 401:
            return self._emit(ApiResult('unauthorized', 401), path)
        if code == 403:
            return self._emit(ApiResult('forbidden', 403, reason=self._policy_reason(response)), path)
        if code == 404:
            return self._emit(ApiResult('not_found', 404), path)
        if code == 429:
            try:
                wait = float(response.headers.get('Retry-After', 30))
            except (TypeError, ValueError):
                wait = 30.0
            self.blocked_until = self.clock() + min(max(wait, 1.0), 300.0)
            return self._emit(ApiResult('rate_limited', 429), path)
        if code >= 500:
            return self._emit(ApiResult('server_error', code), path)
        return self._emit(ApiResult('error', code), path)

    @staticmethod
    def _policy_reason(response):
        try:
            text = response.text or ''
        except Exception:
            return None
        return 'policy_denied' if any(k in text for k in ('PolicyAgent', 'access_denied', 'PA_UNAUTHORIZED_RESULT_FROM_POLICIES')) else None

    def get_product(self, product_id):
        if not isinstance(product_id, str) or not PRODUCT_ID_RE.match(product_id):
            return ApiResult('invalid', reason='bad_product_id')
        return self.get(f'/products/{product_id}')

    def get_item(self, item_id):
        if not isinstance(item_id, str) or not ITEM_ID_RE.match(item_id):
            return ApiResult('invalid', reason='bad_item_id')
        return self.get(f'/items/{item_id}')


# --- normalizer -----------------------------------------------------------------------------------------

# Friendly keys the spec asks for -> the Mercado Livre attribute ids that may carry them (first present wins).
SPEC_ALIASES = {
    'memory_size': ('MEMORY_SIZE',), 'memory_type': ('GRAPHICS_MEMORY_TYPE', 'MEMORY_TYPE'),
    'motherboard_interface': ('MOTHERBOARD_INTERFACE',), 'memory_bus': ('MEMORY_BUS',), 'power_input': ('POWER_INPUT_TYPE',),
    'connectivity': ('CONNECTIVITY',), 'monitor_outputs': ('MONITOR_OUTPUTS_NUMBER',), 'total_graphics_power': ('TOTAL_GRAPHICS_POWER',),
    'release_year': ('RELEASE_YEAR',), 'height': ('HEIGHT',), 'width': ('WIDTH',), 'length': ('LENGTH',),
    'slot_size': ('GRAPHICS_CARDS_SLOT_SIZE',), 'cooling_type': ('REFRIGERATION_TYPE', 'COOLING_TYPE'), 'max_resolution': ('MAX_RESOLUTION',),
    'power_requirement': ('POWER_REQUIREMENT',), 'memory_speed': ('MEMORY_SPEED', 'SPEED'), 'memory_bandwidth': ('MEMORY_BANDWIDTH',),
    'core_count': ('CORES_NUMBER', 'CORES'), 'boost_clock': ('CORE_BOOST_FREQUENCY', 'BOOST_CLOCK'), 'socket': ('SOCKET', 'CPU_SOCKET'),
    'threads': ('THREADS', 'THREADS_NUMBER'), 'base_clock': ('BASE_CLOCK', 'CORE_FREQUENCY'), 'tdp': ('TDP', 'THERMAL_DESIGN_POWER'),
    'integrated_graphics': ('INTEGRATED_GRAPHICS',), 'latency': ('LATENCY', 'CAS_LATENCY'), 'modules': ('MODULES', 'MODULES_NUMBER'),
}
MAX_IMAGES = 8


class MercadoLivreProductNormalizer:
    """Raw `/products/{id}` JSON -> the PC2YOU shape. Missing fields are `None`; nothing is invented."""

    @staticmethod
    def _images(raw):
        urls = []
        for picture in raw.get('pictures') or []:
            url = (picture or {}).get('secure_url') or (picture or {}).get('url')
            if isinstance(url, str) and url.startswith('https://') and (url.split('/')[2].endswith('mlstatic.com')) and url not in urls:
                urls.append(url)
        return urls[:MAX_IMAGES]

    @classmethod
    def normalize(cls, raw):
        if not isinstance(raw, dict) or not raw.get('id'):
            return None
        attributes, specs_struct = {}, {}
        for attribute in raw.get('attributes') or []:
            if not isinstance(attribute, dict) or not attribute.get('id'):
                continue
            value = attribute.get('value_name')
            if value in (None, ''):
                continue
            attributes[attribute['id']] = {'name': attribute.get('name'), 'value': value}
            struct = ((attribute.get('values') or [{}])[0] or {}).get('struct')
            if isinstance(struct, dict) and struct.get('number') is not None:
                specs_struct[attribute['id']] = {'number': struct['number'], 'unit': struct.get('unit')}
        value_of = lambda *ids: next((attributes[i]['value'] for i in ids if i in attributes), None)  # noqa: E731
        specs = {key: value_of(*ids) for key, ids in SPEC_ALIASES.items() if value_of(*ids) is not None}
        short = raw.get('short_description')
        short = short.get('content') if isinstance(short, dict) else short if isinstance(short, str) else None
        return {
            'product_id': raw['id'], 'catalog_product_id': raw.get('catalog_product_id') or raw['id'],
            'name': raw.get('name'), 'family_name': raw.get('family_name'), 'status': raw.get('status'), 'domain_id': raw.get('domain_id'),
            'brand': value_of('BRAND'), 'manufacturer': value_of('MANUFACTURER'), 'model': value_of('MODEL'),
            'detailed_model': value_of('DETAILED_MODEL', 'DETAILED_MODEL_NEW'),
            'images': cls._images(raw), 'attributes': attributes, 'specs': specs, 'specs_struct': specs_struct,
            'short_description': short[:600] if isinstance(short, str) else None, 'last_updated': raw.get('last_updated'),
            'source': SOURCE,
        }


# --- match (the PC2YOU matcher stays the authority) -----------------------------------------------------

# A product of the wrong kind (e.g. a notebook that merely says "Ryzen 7") must never enrich a component.
DOMAIN_RULES = {'cpu': ('PROCESSORS',), 'motherboard': ('MOTHERBOARDS',), 'gpu': ('GRAPHICS_CARDS',), 'storage': ('HARD_DRIVES', 'SSD'),
                'ram': ('MEMORY',), 'kit-ram': ('MEMORY',), 'psu': ('POWER_SUPPL',), 'case': ('CASES', 'CABINETS'),
                'cooler': ('COOLER', 'COOLING', 'FANS', 'HEATSINK', 'REFRIGERATION')}


def domain_fits(domain_id, category):
    if not domain_id:
        return None
    return any(token in domain_id.upper() for token in DOMAIN_RULES.get(category, ()))


def evaluate_match(normalized, component, basis):
    """How well an ML product fits an internal component. Never creates a component link by itself.

    status: matched | conflict | ambiguous. A partner-brand variant of a generic chip component (e.g. a Gigabyte card for
    "NVIDIA RTX 5060 Ti 8GB") is accepted and flagged `brand_variant`; any other conflict blocks the enrichment."""
    attributes = {k.lower(): v['value'] for k, v in (normalized.get('attributes') or {}).items()}
    title = ' '.join(filter(None, [normalized.get('name'), normalized.get('model')]))
    result = compare_product({'title': title, 'brand': normalized.get('brand'), 'category': component.get('category'),
                              'attributes': {k: v for k, v in attributes.items() if k not in {'brand'}}}, component)
    conflicts = list(result.conflicts)
    fits = domain_fits(normalized.get('domain_id'), component.get('category'))
    if fits is False:
        conflicts.append('domain_mismatch')
    brand_variant = False
    if conflicts == ['brand_conflict'] and (component.get('brand') or '').casefold() in {'nvidia', 'amd', 'intel'}:
        conflicts, brand_variant = [], True
    if conflicts:
        status = 'conflict'
    elif fits is None:
        status = 'ambiguous'
    elif brand_variant or (result.matched and result.confidence >= HIGH):
        status = 'matched'
    else:
        status = 'ambiguous'
    return {'status': status, 'basis': basis, 'confidence': result.confidence, 'conflicts': conflicts, 'brand_variant': brand_variant}


# --- persistence, cache, metrics ------------------------------------------------------------------------

def record_state(database, inc=None, set_=None):
    """Counters and last status of the integration, in Mongo. No secrets."""
    update = {}
    if inc:
        update['$inc'] = {f'metrics.{k}': v for k, v in inc.items()}
    if set_:
        update['$set'] = set_
    if update:
        try:
            database[STATE_COLLECTION].update_one({'_id': 'state'}, update, upsert=True)
        except Exception:  # state is informational only
            pass


class MercadoLivreProductEnrichment:
    """Fetch (with a 24h cache) -> normalize -> match -> persist. Prices, coupons, Telegram data and `component_id` are never touched."""

    def __init__(self, database, api, ttl_hours=None, now=None):
        self.database, self.api = database, api
        self.ttl = timedelta(hours=cache_ttl_hours() if ttl_hours is None else ttl_hours)
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _cached(self, product_id):
        doc = self.database[COLLECTION].find_one({'_id': product_id})
        fetched = date_value((doc or {}).get('fetched_at'))
        return doc, bool(doc and fetched and self.now() - fetched <= self.ttl)

    def fetch(self, product_id, force=False):
        """(document or None, outcome) with outcome in cache | fetched | stale_cache | <api failure kind>."""
        doc, fresh = self._cached(product_id)
        if doc and fresh and not force:
            return doc, 'cache'
        result = self.api.get_product(product_id)
        if result.ok:
            normalized = MercadoLivreProductNormalizer.normalize(result.data)
            if normalized:
                payload = {**normalized, 'fetched_at': self.now().isoformat()}
                self.database[COLLECTION].update_one({'_id': product_id}, {'$set': payload}, upsert=True)
                record_state(self.database, {'ml_products_fetched': 1}, {'last_product_success': payload['fetched_at'], 'last_error': None, 'product_api': 'available'})
                return self.database[COLLECTION].find_one({'_id': product_id}), 'fetched'
            result.kind = 'invalid'
        record_state(self.database, {'ml_product_api_errors': 1}, {'last_error': result.kind, 'product_api': 'unavailable' if result.kind not in {'not_found'} else 'available'})
        return (doc, 'stale_cache') if doc else (None, result.kind)

    def enrich(self, product_id, component, *, basis, force=False):
        doc, outcome = self.fetch(product_id, force)
        if not doc:
            return {'product_id': product_id, 'component_id': component['id'], 'outcome': outcome, 'applied': False}
        match = evaluate_match(doc, component, basis)
        self.database[COLLECTION].update_one({'_id': product_id}, {'$set': {f'matches.{component["id"]}': match},
                                                                     '$addToSet': {'component_ids': component['id']}})
        existing = ((component.get('external_enrichment') or {}).get('mercado_livre') or {}).get('product_id')
        applied = match['status'] == 'matched' and (not existing or existing == product_id or force)
        if applied:
            payload = {k: doc.get(k) for k in ('product_id', 'catalog_product_id', 'name', 'family_name', 'brand', 'manufacturer', 'model',
                                               'detailed_model', 'images', 'attributes', 'specs', 'specs_struct', 'short_description',
                                               'domain_id', 'last_updated', 'fetched_at', 'source')}
            payload.update(match_status=match['status'], match_basis=basis, brand_variant=match['brand_variant'],
                           external_conflict=bool(match['conflicts']))
            self.database['components'].update_one({'id': component['id']}, {'$set': {'external_enrichment.mercado_livre': payload}})
            record_state(self.database, {'ml_products_enriched': 1, 'ml_images_added': 1 if payload['images'] else 0,
                                         'ml_specs_added': 1 if payload['specs'] else 0})
        return {'product_id': product_id, 'component_id': component['id'], 'outcome': outcome, 'match': match, 'applied': applied,
                'images': len(doc.get('images') or []), 'specs': len(doc.get('specs') or {})}


# --- price capability and (future) validation -----------------------------------------------------------

class MercadoLivrePriceCapability:
    """Does the official API let us read this listing? available | forbidden | not_found | error. Never judges an offer."""

    def __init__(self, api, database=None, now=None):
        self.api, self.database = api, database
        self.now = now or (lambda: datetime.now(timezone.utc))

    def probe(self, item_id):
        result = self.api.get_item(item_id)
        status = {'ok': 'available', 'forbidden': 'forbidden', 'not_found': 'not_found'}.get(result.kind, 'error')
        report = {'item_id': item_id, 'status': status, 'http_status': result.status, 'reason': result.reason,
                  'checked_at': self.now().isoformat()}
        if self.database is not None and result.kind != 'invalid':
            if status == 'forbidden':
                record_state(self.database, {'ml_item_api_forbidden': 1},
                             {'item_api': 'restricted', 'price_validation': 'unavailable', 'ml_price_validation_capability': 'forbidden',
                              'capability_checked_at': report['checked_at']})
            elif status == 'available':
                record_state(self.database, None, {'item_api': 'available', 'price_validation': 'available',
                                                   'ml_price_validation_capability': 'available', 'capability_checked_at': report['checked_at']})
        return report


VERIFICATION_STATUSES = ('confirmed', 'price_changed', 'expired', 'unavailable', 'coupon_not_verifiable', 'unverified')


def price_tolerance(price, absolute=1.0, relative=0.005):
    return max(absolute, relative * price)


class MercadoLivrePriceValidator:
    """Compares an announced price with the official one — only when the API authorises the listing.

    `forbidden`/errors -> `unavailable`: the offer is NOT invalidated and no field is written. A coupon price that differs from the
    official base price is `coupon_not_verifiable`, never `price_changed`."""

    def __init__(self, api, now=None, tolerance_absolute=1.0, tolerance_relative=0.005):
        self.api, self.tolerance = api, (tolerance_absolute, tolerance_relative)
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _outcome(self, status, **extra):
        return {'verification_status': status, 'fields': extra.pop('fields', {}), **extra}

    def validate(self, offer, item_id):
        advertised = money((offer or {}).get('price'))
        if not item_id or not advertised:
            return self._outcome('unverified')
        item = self.api.get_item(item_id)
        if item.kind == 'not_found':
            return self._outcome('expired', reason='item_not_found')
        if not item.ok:
            return self._outcome('unavailable', reason=item.kind)
        if str(item.data.get('status') or '').lower() in {'closed', 'paused', 'inactive'}:
            return self._outcome('expired', reason='item_' + str(item.data.get('status')).lower())
        sale = self.api.get(f'/items/{item_id}/sale_price', {'context': 'channel_marketplace'})
        official, regular, end = None, None, None
        if sale.ok and sale.data.get('currency_id') == 'BRL':
            official, regular = money(sale.data.get('amount')), money(sale.data.get('regular_amount'))
            end = date_value((sale.data.get('conditions') or {}).get('end_time'))
        else:
            official = money(item.data.get('price'))
        if official is None:
            return self._outcome('unavailable', reason=sale.kind)
        now = self.now()
        if end and end < now:
            return self._outcome('expired', official_price=official, reason='promotion_ended')
        coupon = bool((offer or {}).get('coupon') or ((offer or {}).get('conditions') or {}).get('requires_coupon'))
        if abs(official - advertised) <= price_tolerance(advertised, *self.tolerance):
            return self._outcome('confirmed', official_price=official, fields={
                'verification_source': PRICE_SOURCE, 'verified_price': official, 'verified_at': now.isoformat(), 'verification_status': 'confirmed'})
        if coupon:
            # The coupon may explain the gap: keep the official base price apart and do not call the announcement wrong.
            return self._outcome('coupon_not_verifiable', official_price=official, regular_price=regular, fields={
                'verification_status': 'coupon_not_verifiable', 'official_base_price': official, 'verification_source': PRICE_SOURCE})
        return self._outcome('price_changed', official_price=official, regular_price=regular, fields={
            'verification_source': PRICE_SOURCE, 'verified_price': official, 'verified_at': now.isoformat(), 'verification_status': 'price_changed'})


def record_official_price(database, component_id, item_id, price, observed_at=None):
    """Real price history entry from an official API answer. One per (item, day, price): polling does not duplicate."""
    price = money(price)
    if not (component_id and item_id and price):
        return False
    when = (observed_at or datetime.now(timezone.utc))
    day = when.date().isoformat()
    key = {'source': PRICE_SOURCE, 'item_id': item_id, 'price': price, 'day': day}
    if database['product_price_history'].find_one(key):
        return False
    database['product_price_history'].insert_one({**key, 'component_id': component_id, 'date': when.isoformat(), 'observed_at': when.isoformat(),
                                                  'verified': True, 'match_level': 'high', 'match_confidence': 1.0})
    record_state(database, {'ml_price_validations_successful': 1})
    return True


# --- status ---------------------------------------------------------------------------------------------

def integration_status(tokens, database=None):
    """Safe status for the status endpoint: no token, no raw error body."""
    token_state = tokens.state()
    state = {}
    if database is not None:
        try:
            state = database[STATE_COLLECTION].find_one({'_id': 'state'}) or {}
        except Exception:
            state = {}
    item_api = state.get('item_api', 'unknown')
    return {'configured': token_state['configured'], 'authorized': token_state['configured'] and state.get('last_error') not in {'unauthorized', 'auth_unavailable'},
            'refresh_available': token_state['refresh_available'], 'token_expires_at': token_state['expires_at'],
            'product_api': state.get('product_api', 'unknown'), 'item_api': item_api,
            'price_validation': state.get('price_validation', 'unavailable' if item_api in {'restricted', 'unknown'} else item_api),
            'last_product_success': state.get('last_product_success'), 'last_error': state.get('last_error'),
            'metrics': {k: (state.get('metrics') or {}).get(k, 0) for k in (
                'ml_products_detected', 'ml_products_enriched', 'ml_images_added', 'ml_specs_added', 'ml_product_api_errors',
                'ml_item_api_forbidden', 'ml_price_validations_successful')}}


tokens = MercadoLivreTokenManager()
api = MercadoLivreApi(tokens)
