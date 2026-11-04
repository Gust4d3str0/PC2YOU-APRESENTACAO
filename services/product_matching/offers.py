"""Offer conditions, status model and validators.

Deterministic and offline: conditions come from the announcement text with fixed patterns (no AI, no scraping).
Anything the text does not say stays `None` ("unknown"), never `False`.
"""
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .quality import (CONFIRMATION_TTL_HOURS, EXPLICIT_VALIDITY_MAX_DAYS, RECENT_HOURS, REDUCED_HOURS,
                      STALE_LIMIT_HOURS, date_value, money)

BRT = timezone(timedelta(hours=-3))


# Freshness thresholds live in quality.py (shared with the legacy state); see there to configure them.
PRICE_CHANGE_TOLERANCE = 0.01

STATUSES = ('announced', 'conditional', 'confirmed', 'stale', 'expired', 'invalid')
MANUAL_VALID = ('valid', 'working')          # 'working' / 'not_working' are accepted legacy spellings
MANUAL_INVALID = ('invalid', 'not_working')
MANUAL_STATUSES = MANUAL_VALID + MANUAL_INVALID
CONDITIONS_VERSION = 2
CONDITION_FLAGS = ('requires_coupon', 'first_purchase_only', 'new_customer_only', 'app_only',
                   'membership_required', 'minimum_order')


# --- condition extraction ----------------------------------------------------------------------------------

_URL = re.compile(r'https?://\S+|www\.\S+', re.I)
_AMOUNT = r'((?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?)'


def _plain(text):
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', _URL.sub(' ', text)).strip()


def _amount(value):
    try:
        return money(Decimal(value.replace('.', '').replace(',', '.')))
    except (InvalidOperation, AttributeError):
        return None


_FIRST = re.compile(r'primeira compra|primeiro pedido|1[ao]?\s*compra|1[ao]\s*pedido|first purchase')
_NEW_CUSTOMER = re.compile(r'novos? (?:clientes?|usuarios?)|cliente novo|usuario novo|clientes? novos?|novo cadastro')
_APP = re.compile(r'(?:somente|so|apenas|exclusivo|exclusiva)\s+(?:pelo|no|via|do|para|de)?\s*(?:app|aplicativo)\b'
                  r'|\bapp exclusivo|exclusivo app|compras? (?:pelo|no) (?:app|aplicativo)\b|primeira compra (?:pelo|no|via) (?:app|aplicativo)')
_PAYMENT = (('PIX', re.compile(r'\bpix\b')), ('NuPay', re.compile(r'\bnu\s?pay\b')), ('Nubank', re.compile(r'\bnubank\b')),
            ('Cartão da loja', re.compile(r'cartao (?:da loja|kabum|magalu|casas bahia|pichau|mercado pago|amazon)')))
_MEMBERSHIP = (('Prime', re.compile(r'\bprime\b')), ('Meli+', re.compile(r'\bmeli\s?\+')), ('Clube', re.compile(r'\bclube (?:kabum|magalu|do)\b')))
_MINIMUM = re.compile(r'(?:pedido minimo|valor minimo|compras? minim[ao]s?|minimo de|min\.?|acima de|compras? acima de|compras? superiores? a)\s*(?:de\s*)?r\$\s*' + _AMOUNT)
_CPF = re.compile(r'(?:\b1|\bum)\s*(?:uso|utilizacao|cupom|unidade|compra)?\s*por\s*(?:cpf|cliente|usuario|conta)|uso unico por (?:cpf|cliente)|limitad[oa] a (?:1|um) por (?:cpf|cliente)')
_DATE = re.compile(r'(?:valid[oa]s?(?:\s*(?:ate|de))?|ate|expira(?:\s*em)?|encerra(?:\s*em)?|termina(?:\s*em)?)\s*:?\s*(?:o dia\s*)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?'
                   r'(?:\s*(?:as|a|ate|-)?\s*(\d{1,2})(?::|h)(\d{2})?)?')
_UNTIL_TIME = re.compile(r'\bate\s*(?:as\s*)?(\d{1,2})(?::|h)(\d{2})?\b(?!\s*/)')
_TODAY = re.compile(r'(?:somente|so|apenas|valido|valida|ate|ultimo dia)\s*(?:so\s*)?hoje|ultimo dia|hoje ate')


def _local(sent_at):
    sent = date_value(sent_at)
    return sent.astimezone(BRT) if sent else None


def _deadline(text, sent_at):
    """Explicit validity as an aware datetime, or None. A missing year is the announcement's year (next one if already past)."""
    sent = _local(sent_at)
    match = _DATE.search(text)
    if match:
        day, month, year, hour, minute = match.groups()
        try:
            if year:
                year = int(year) + (2000 if int(year) < 100 else 0)
            elif sent:
                year = sent.year
            else:
                return None
            value = datetime(year, int(month), int(day), int(hour or 23), int(minute or (59 if hour is None else 0)), tzinfo=BRT)
            if not match.group(3) and sent and value < sent - timedelta(days=1):
                value = value.replace(year=year + 1)
            return value
        except ValueError:
            return None
    if not sent:
        return None
    if _TODAY.search(text):
        return sent.replace(hour=23, minute=59, second=0, microsecond=0)
    until = _UNTIL_TIME.search(text)
    if until:
        try:
            value = sent.replace(hour=int(until.group(1)), minute=int(until.group(2) or 0), second=0, microsecond=0)
        except ValueError:
            return None
        return value if value >= sent else None
    return None


def _relevant_text(text):
    """Original fragments that carry a condition, URLs removed. Never rewritten or invented."""
    patterns = (_FIRST, _NEW_CUSTOMER, _APP, _MINIMUM, _CPF, _DATE, _UNTIL_TIME, _TODAY, re.compile(r'cupom|\bpix\b|nu\s?pay|\bprime\b|cartao'))
    pieces = [p.strip(' -•*_|') for p in re.split(r'[\n|]+|(?<=[.!?])\s+', _URL.sub(' ', str(text or '')))]
    kept = [p for p in pieces if p and any(r.search(_plain(p)) for r in patterns)]
    return ' | '.join(dict.fromkeys(kept))[:300] or None


def extract_conditions(text, coupon=None, sent_at=None):
    """Conditions announced in the text. Unknown stays None; `coupon` is the already-parsed code."""
    plain = _plain(text)
    payment = [name for name, rule in _PAYMENT if rule.search(plain)]
    membership = [name for name, rule in _MEMBERSHIP if rule.search(plain)]
    minimum = _MINIMUM.search(plain)
    deadline = _deadline(plain, sent_at)
    return {
        'requires_coupon': True if coupon else None,
        'coupon_code': coupon or None,
        'first_purchase_only': True if _FIRST.search(plain) else None,
        'new_customer_only': True if _NEW_CUSTOMER.search(plain) else None,
        'app_only': True if _APP.search(plain) else None,
        'payment_methods': payment,
        'membership_required': ' / '.join(membership) or None,
        'minimum_order': _amount(minimum.group(1)) if minimum else None,
        'max_uses_per_customer': 1 if _CPF.search(plain) else None,
        'valid_until': deadline.isoformat() if deadline else None,
        'conditions_text': _relevant_text(text),
        'conditions_version': CONDITIONS_VERSION,
    }


def payment_methods_of(conditions):
    c = conditions or {}
    return list(c.get('payment_methods') or ([c['payment_method']] if c.get('payment_method') else []))


def is_conditional(conditions):
    c = conditions or {}
    return bool(payment_methods_of(c)) or any(c.get(flag) for flag in CONDITION_FLAGS)


def condition_labels(conditions):
    c = conditions or {}
    labels = []
    if c.get('requires_coupon'):
        labels.append('Exige cupom')
    if c.get('first_purchase_only'):
        labels.append('Somente primeira compra')
    if c.get('new_customer_only'):
        labels.append('Somente novos clientes')
    if c.get('app_only'):
        labels.append('Somente pelo app')
    for method in payment_methods_of(c):
        labels.append(f'Pagamento via {method}')
    if c.get('membership_required'):
        labels.append(f"Exclusivo para assinantes {c['membership_required']}")
    if c.get('minimum_order'):
        labels.append(f"Pedido mínimo R$ {c['minimum_order']:.2f}".replace('.', ','))
    uses = c.get('max_uses_per_customer') or (1 if c.get('one_use_per_cpf') else None)
    if uses:
        labels.append(f'Limite de {uses} uso por cliente')
    return labels


# --- status model ------------------------------------------------------------------------------------------

def freshness_of(age_hours):
    if age_hours is None:
        return 'unknown'
    if age_hours <= RECENT_HOURS:
        return 'very_recent'
    if age_hours <= REDUCED_HOURS:
        return 'recent'
    if age_hours <= STALE_LIMIT_HOURS:
        return 'aging'
    return 'stale'


def _latest_check(offer, price):
    """Most recent human/source check as (at, kind, ok, reason), or None."""
    checks = []
    manual, manual_at = offer.get('manual_validation_status'), date_value(offer.get('manual_validated_at'))
    if manual in MANUAL_STATUSES and manual_at:
        checks.append((manual_at, 'manual', manual in MANUAL_VALID, 'manual'))
    verified_at, verified_price = date_value(offer.get('verified_at')), money(offer.get('verified_price'))
    if verified_at and verified_price and price:
        same = abs(verified_price - price) / price <= PRICE_CHANGE_TOLERANCE
        checks.append((verified_at, offer.get('verification_source') or 'unknown', same, 'verified' if same else 'price_changed'))
    # Latest check wins; on a tie the negative one does (an observed price that differs beats a plain "works").
    return max(checks, key=lambda c: (c[0], not c[2])) if checks else None


def evaluate_offer(offer, now=None, *, captured=None, conditions=None):
    """Status of one announced offer.

    status: announced | conditional | confirmed | stale | expired | invalid
    eligible: may compete for "best price" (never true for expired/invalid/old-without-confirmation/no price).
    Telegram alone never yields `confirmed`; only a manual check or a source verification does, and only for a while.
    """
    now = now or datetime.now(timezone.utc)
    conditions = conditions if conditions is not None else offer.get('conditions') or {}
    price = money(offer.get('price'))
    captured = date_value(captured or offer.get('captured_at'))
    age = (now - captured).total_seconds() / 3600 if captured else None
    conditional = is_conditional(conditions)
    result = {'status': 'announced', 'reason': None, 'eligible': False, 'freshness': freshness_of(age),
              'is_conditional': conditional, 'age_hours': round(age, 2) if age is not None else None}

    def done(status, reason=None, eligible=False):
        result.update(status=status, reason=reason, eligible=bool(eligible and price))
        return result

    check = _latest_check(offer, price)
    if check and captured and check[0] >= captured and not check[2]:
        return done('invalid', check[3])
    deadlines = [date_value(offer.get('valid_until') or conditions.get('valid_until'))]
    if offer.get('coupon'):
        deadlines.append(date_value(offer.get('coupon_valid_until')))
    deadlines = [d for d in deadlines if d]
    if any(now > d for d in deadlines):
        return done('expired', 'validity_ended')
    if captured is None or age < -0.01:
        return done('announced', 'no_capture_date')
    if check and check[0] >= captured and check[2] and now - check[0] <= timedelta(hours=CONFIRMATION_TTL_HOURS):
        return done('confirmed', check[1], True)
    if deadlines:  # explicit validity beats generic freshness, within a sanity cap
        if age <= EXPLICIT_VALIDITY_MAX_DAYS * 24:
            return done('conditional' if conditional else 'announced', 'explicit_validity', True)
        return done('stale', 'announcement_too_old')
    if age > STALE_LIMIT_HOURS:
        return done('stale', 'beyond_freshness_limit')
    if age > REDUCED_HOURS:
        return done('stale', 'needs_confirmation', True)
    return done('conditional' if conditional else 'announced', None, True)


# --- validators (architecture only: nothing here scrapes stores or calls a provider) --------------------

@dataclass(frozen=True)
class ValidationResult:
    outcome: str                       # 'working' | 'not_working' | 'unknown'
    source: str
    verified_price: float | None = None
    verified_at: datetime | None = None
    reason: str | None = None


class OfferValidator(ABC):
    source = 'unknown'

    @abstractmethod
    def validate(self, offer, now=None) -> ValidationResult:
        """Check one offer against this validator's source of truth."""

    def fields(self, result):
        """`offer.*` fields to persist for a result; empty when the source could not decide."""
        if result.outcome == 'unknown':
            return {}
        return {'verification_source': result.source, 'verified_price': result.verified_price,
                'verified_at': (result.verified_at or datetime.now(timezone.utc)).isoformat()}


class TelegramOfferValidator(OfferValidator):
    """Telegram has no source of truth: only a person's recorded check counts."""
    source = 'manual'

    def validate(self, offer, now=None):
        status, at = offer.get('manual_validation_status'), date_value(offer.get('manual_validated_at'))
        if status in MANUAL_STATUSES and at:
            return ValidationResult(status, 'manual', verified_at=at)
        return ValidationResult('unknown', 'manual', reason='no_manual_check')


class MercadoLivreOfferValidator(OfferValidator):
    """Future: compare with the official Mercado Livre API. Inert without an injected price lookup (no credentials here)."""
    source = 'mercado_livre_api'

    def __init__(self, price_lookup=None):
        self.price_lookup = price_lookup

    def validate(self, offer, now=None):
        if self.price_lookup is None:
            return ValidationResult('unknown', self.source, reason='mercado_livre_not_configured')
        try:
            price = money(self.price_lookup(offer))
        except Exception:
            return ValidationResult('unknown', self.source, reason='lookup_failed')
        if price is None:
            return ValidationResult('unknown', self.source, reason='no_price')
        advertised = money(offer.get('price'))
        same = bool(advertised) and abs(price - advertised) / advertised <= PRICE_CHANGE_TOLERANCE
        return ValidationResult('working' if same else 'not_working', self.source, price, now or datetime.now(timezone.utc),
                                None if same else 'price_changed')
