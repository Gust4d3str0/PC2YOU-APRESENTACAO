"""Offer provenance, conservative price selection, equivalence and real observations."""
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlsplit, urlunsplit

from .matcher import HIGH, VERSION, compare_product
from .normalization import normalize_store


def _hours(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


# Freshness thresholds in hours since the announcement. Heuristics, configurable by environment.
RECENT_HOURS = _hours('PC2YOU_OFFER_RECENT_HOURS', 6)
REDUCED_HOURS = _hours('PC2YOU_OFFER_REDUCED_HOURS', 24)
STALE_LIMIT_HOURS = _hours('PC2YOU_OFFER_STALE_LIMIT_HOURS', 72)
CONFIRMATION_TTL_HOURS = _hours('PC2YOU_OFFER_CONFIRMATION_TTL_HOURS', 6)  # a manual confirmation ages quickly
EXPLICIT_VALIDITY_MAX_DAYS = _hours('PC2YOU_OFFER_EXPLICIT_MAX_DAYS', 7)


def fresh_days(source):
    return STALE_LIMIT_HOURS / 24 if source == 'telegram' else 7


def money(value):
    if isinstance(value, bool):
        return None
    try:
        amount = value.to_decimal() if hasattr(value, 'to_decimal') else Decimal(str(value))
        if not amount.is_finite() or not 0 < amount <= 1_000_000:
            return None
        rounded = float(amount.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
        return rounded if rounded > 0 else None
    except (ValueError, TypeError, InvalidOperation):
        return None


def date_value(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def recent(value, now, days):
    date = date_value(value)
    return date if date and now - timedelta(days=days) <= date <= now else None


def offer_state(offer, *, now=None, captured_at=None, source=None):
    """Announced validity only; never proof that a coupon succeeds at checkout."""
    now = now or datetime.now(timezone.utc)
    deadlines = [offer.get('valid_until')]
    if offer.get('coupon'):
        deadlines.append(offer.get('coupon_valid_until'))
    parsed = [date_value(v) for v in deadlines if v is not None]
    if any(d is not None and now > d for d in parsed):
        return 'expired'
    if any(d is None for d in parsed):
        return 'unknown'
    captured = date_value(captured_at or offer.get('captured_at') or offer.get('last_update'))
    # An explicit, still-open validity beats the generic freshness window (within a sanity cap).
    limit = EXPLICIT_VALIDITY_MAX_DAYS if parsed else fresh_days(source or offer.get('source'))
    if captured and now > captured + timedelta(days=limit):
        return 'expired'
    if captured and captured > now:
        return 'unknown'
    return 'active' if parsed or captured else 'unknown'


def valid_http_url(value):
    if not isinstance(value, str) or re.search(r'[\x00-\x20\x7f<>"\\]', value):
        return None
    try:
        parsed = urlsplit(value)
        parsed.port
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username is not None:
            return None
        return value
    except ValueError:
        return None


def offer_url(value):
    value = valid_http_url(value)
    if not value:
        return None
    parsed = urlsplit(value)
    host = parsed.hostname.lower().rstrip('.')
    if any(host == d or host.endswith('.' + d) for d in ('t.me', 'telegram.me', 'telegram.dog', 'instagram.com', 'facebook.com',
            'fb.com', 'twitter.com', 'x.com', 'youtube.com', 'youtu.be', 'tiktok.com', 'discord.gg', 'discord.com', 'whatsapp.com', 'wa.me')):
        return None
    if re.search(r'\.(?:png|jpe?g|webp|gif|svg|avif|bmp|ico)$', parsed.path, re.I):
        return None
    if host in {'www.mercadolivre.com.br', 'mercadolivre.com.br'} and not parsed.path.strip('/'):
        return None
    return value


def equivalence_key(component_id, offer):
    url = offer_url(offer.get('url'))
    if url:
        parsed = urlsplit(url)
        url = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ''))
    # Keep affiliate queries/coupons: equal products need not mean equal commercial offers.
    identity = [component_id, money(offer.get('price')), normalize_store(offer.get('store')),
                str(offer.get('coupon') or '').strip().upper(), url]
    if not component_id or identity[1] is None:
        return None
    return hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest()


def price_quality(offer, match=None, *, now=None, source=None, captured_at=None):
    now = now or datetime.now(timezone.utc)
    source = source or offer.get('source') or 'seed'
    source = source if source in {'seed', 'mercado_livre', 'telegram', 'manual'} else 'unknown'
    confidence = match.confidence if match is not None else 0
    level = match.confidence_level if match is not None else 'low'
    captured = date_value(captured_at or offer.get('captured_at') or offer.get('last_update'))
    freshness = recent(captured, now, EXPLICIT_VALIDITY_MAX_DAYS if offer.get('valid_until') or offer.get('coupon_valid_until') else fresh_days(source))
    availability = str(offer.get('availability', 'Disponível')).casefold()
    available = availability in {'disponível', 'disponivel', 'available'}
    state = offer_state(offer, now=now, captured_at=captured, source=source)
    verified = bool(source in {'telegram', 'mercado_livre', 'manual'} and match is not None and match.matched
                    and not match.conflicts and confidence >= HIGH and freshness and available and state == 'active' and money(offer.get('price')))
    return {'source': source, 'verified': verified, 'state': state, 'coupon_status': state if offer.get('coupon') else None, 'product_match_confidence': confidence,
            'product_match_level': level, 'captured_at': captured.isoformat(timespec='milliseconds') if captured else None,
            'url_valid': bool(offer_url(offer.get('url'))), 'url_source': offer.get('url_source') or 'unknown',
            'store_key': normalize_store(offer.get('store')), 'matcher_version': VERSION}


def best_known_price(offers, *, allow_medium=False, allow_reference=False, now=None):
    now = now or datetime.now(timezone.utc)
    def tier(o):
        q = o.get('quality') or o
        if q.get('state') == 'expired' or (not q.get('state') and any(date_value(o.get(k)) and now > date_value(o[k]) for k in ('valid_until', 'coupon_valid_until') if k == 'valid_until' or o.get('coupon'))):
            return 4
        if q.get('verified') is True and q.get('product_match_level') == 'high' and q.get('source') in {'telegram', 'mercado_livre', 'manual'}:
            return 0
        if allow_medium and q.get('product_match_level') == 'medium' and q.get('source') in {'telegram', 'mercado_livre', 'manual'}:
            return 1
        if q.get('source', 'seed') == 'seed':
            return 2
        if allow_reference and q.get('product_match_level') == 'high':
            return 3
        return 4
    valid = [o for o in offers if money(o.get('price')) is not None and tier(o) < 4]
    return min(valid, key=lambda o: (tier(o), money(o['price']))) if valid else None


def catalog_offers(component, now=None):
    result = []
    for offer in component.get('prices') or []:
        if not isinstance(offer, dict) or money(offer.get('price')) is None:
            continue
        # Recompute from supplied evidence; a persisted score is not permission to bypass conflicts.
        match = compare_product({'title': offer.get('title'), 'brand': offer.get('brand'),
                                 'category': component.get('category'), 'attributes': offer.get('attributes') or {}}, component)
        quality = price_quality(offer, match, now=now)
        result.append({**offer, 'price': money(offer['price']), 'quality': quality,
                       'equivalence_key': equivalence_key(component.get('id'), offer)})
    return result


def history_observation(component_id, offer, quality):
    if not quality.get('verified') or quality.get('product_match_level') != 'high':
        return None
    return {'date': quality['captured_at'], 'price': money(offer.get('price')), 'source': quality['source'],
            'store': offer.get('store'), 'store_key': quality['store_key'], 'component_id': component_id,
            'match_confidence': quality['product_match_confidence'], 'match_level': 'high',
            'verified': True, 'equivalence_key': equivalence_key(component_id, offer), 'matcher_version': VERSION,
            'coupon': offer.get('coupon') or None, 'observed_at': quality['captured_at']}
