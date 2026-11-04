"""Mercado Livre identifiers found in URLs. Pure functions: no network, no guessing.

PRODUCT_ID  catalog/PDP product, e.g. `.../p/MLB78085963`      -> API `/products/{PRODUCT_ID}`
ITEM_ID     one seller's listing, e.g. `?wid=MLB7833387058`    -> API `/items/{ITEM_ID}` (restricted for third parties)

The two are never interchangeable. An id that is not unambiguous is `None`.
"""
import re
from urllib.parse import parse_qsl, unquote, urlsplit

_HOSTS = ('mercadolivre.com.br', 'mercadolivre.com', 'mercadolibre.com', 'meli.la')
_PRODUCT_PATH = re.compile(r'/p/(MLB\d{5,})(?:[/?#]|$)', re.I)
_ITEM_PATH = re.compile(r'/(MLB)-?(\d{6,})(?:[-/?#]|$)', re.I)
_ITEM_QUERY_KEYS = ('wid', 'item_id')
_PDP_FILTER = re.compile(r'item_id:(MLB\d{6,})', re.I)
PRODUCT_ID_RE = re.compile(r'^MLB\d{5,}$')
ITEM_ID_RE = re.compile(r'^MLB\d{6,}$')


def is_mercado_livre_url(url):
    host = (urlsplit(url).hostname or '').lower().rstrip('.') if isinstance(url, str) else ''
    return any(host == d or host.endswith('.' + d) for d in _HOSTS)


def _parts(url):
    if not isinstance(url, str) or not is_mercado_livre_url(url):
        return None
    return urlsplit(url)


def extract_product_id(*urls):
    """PRODUCT_ID from the first URL that names exactly one (`/p/MLB123`). `/up/MLBU…` user products and bare item pages do not count."""
    found = set()
    for url in urls:
        parts = _parts(url)
        if parts:
            found.update(m.upper() for m in _PRODUCT_PATH.findall(parts.path))
    return next(iter(found)) if len(found) == 1 else None


def extract_item_id(*urls):
    """ITEM_ID only when unambiguous: `wid=` / `item_id=` / `pdp_filters=item_id:` or an item path `/MLB-123456789-title`.

    `/p/MLB…` is a product id and is never returned here."""
    found = set()
    for url in urls:
        parts = _parts(url)
        if not parts:
            continue
        for key, value in parse_qsl(parts.query):
            if key.lower() in _ITEM_QUERY_KEYS and ITEM_ID_RE.match(value.upper()):
                found.add(value.upper())
            if key.lower() == 'pdp_filters':
                found.update(m.upper() for m in _PDP_FILTER.findall(unquote(value)))
        if not _PRODUCT_PATH.search(parts.path):
            match = _ITEM_PATH.search(parts.path)
            if match:
                found.add(('MLB' + match.group(2)).upper())
    return next(iter(found)) if len(found) == 1 else None


def ml_ids_from_offer(offer):
    """(product_id, item_id) from a stored promotion offer: resolved URL first, then the original one."""
    urls = [(offer or {}).get('resolved_url'), (offer or {}).get('url')]
    return extract_product_id(*urls), extract_item_id(*urls)
