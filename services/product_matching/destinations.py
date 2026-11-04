"""Offer link destinations: store identity, destination class and safe HTTP redirect resolution.

Only plain HTTP(S) redirects are followed (no JavaScript, forms, login, checkout or coupon calls).
"""
from ipaddress import ip_address
import re
import socket
import threading
import time
from urllib.parse import parse_qsl, urljoin, urlsplit

from .quality import offer_url

# The single place that maps a (final) domain to a store name.
STORE_DOMAINS = {
    'Kabum': ('kabum.com.br',),
    'Pichau': ('pichau.com.br',),
    'Terabyte': ('terabyteshop.com.br',),
    'Amazon': ('amazon.com.br', 'amazon.com'),
    'Mercado Livre': ('mercadolivre.com.br', 'mercadolivre.com', 'mercadolibre.com'),
    'Magazine Luiza': ('magazineluiza.com.br', 'magalu.com'),
    'Shopee': ('shopee.com.br',),
    'AliExpress': ('aliexpress.com',),
}
# Known shorteners/affiliate redirectors: the host says nothing about the store or the page.
SHORTENER_DOMAINS = (
    'meli.la', 'amzn.to', 'link.amazon', 'a.co', 'pruuu.me', 'aoferta.net', 'ofertou.ai', 'curt.link', 'cutt.ly',
    'tidd.ly', 'bit.ly', 's.click.aliexpress.com', 'a.aliexpress.com', 's.shopee.com.br', 'eioferta.com.br',
    'awin1.com', 'tinyurl.com', 'is.gd', 'shorturl.at',
)
KIND_RANK = {'product': 3, 'search': 2, 'homepage': 1, 'unknown': 0}

_SEARCH_PATH = re.compile(r'/(?:search|busca|procura|pesquisa|buscar|s|catalogsearch/result)(?:/|$)', re.I)
_SEARCH_QUERY = {'q', 'k', 'query', 'keyword', 'keywords', 'search', 'busca', 'text', 'searchtext', 'term'}
_PRODUCT_PATH = {
    'kabum.com.br': r'/produto/\d+', 'terabyteshop.com.br': r'/produto/\d+', 'amazon.com.br': r'/(?:dp|gp/product|gp/aw/d)/[A-Z0-9]{8,}',
    'amazon.com': r'/(?:dp|gp/product)/[A-Z0-9]{8,}', 'mercadolivre.com.br': r'/(?:MLB-?\d+|p/MLB\d+)',
    'mercadolivre.com': r'/(?:MLB-?\d+|p/MLB\d+)', 'magazineluiza.com.br': r'/p/[a-z0-9]+/',
    'shopee.com.br': r'/product/\d+/\d+|-i\.\d+\.\d+', 'aliexpress.com': r'/item/\d+',
}
# Pichau product pages are a single descriptive slug; stores below this line need that shape to be a product.
_SLUG = re.compile(r'^/[a-z0-9]+(?:-[a-z0-9]+){3,}/?$', re.I)


def _host(url):
    return (urlsplit(url).hostname or '').lower().rstrip('.')


def _matches(host, domain):
    return host == domain or host.endswith('.' + domain)


def is_shortener(url):
    host = _host(url) if isinstance(url, str) else ''
    return any(_matches(host, d) for d in SHORTENER_DOMAINS)


def store_from_url(url):
    """Store from the URL's own domain; None for shorteners and unknown domains."""
    if not isinstance(url, str):
        return None
    host = _host(url)
    if not host or is_shortener(url):
        return None
    for store, domains in STORE_DOMAINS.items():
        if any(_matches(host, d) for d in domains):
            return store
    return None


def classify_url(url):
    """product | search | homepage | unknown, from URL shape only."""
    if not offer_url(url):
        return 'unknown'
    parsed = urlsplit(url)
    host, path = _host(url), parsed.path or '/'
    if is_shortener(url):
        return 'unknown'
    query = {k.lower() for k, _ in parse_qsl(parsed.query)}
    if _SEARCH_PATH.search(path) or (query & _SEARCH_QUERY and not re.search(r'/(?:dp|produto|item|p)/', path)):
        return 'search'
    if not path.strip('/'):
        return 'homepage'
    for domain, pattern in _PRODUCT_PATH.items():
        if _matches(host, domain) and re.search(pattern, path):
            return 'product'
    if _matches(host, 'pichau.com.br') and _SLUG.match(path):
        return 'product'
    return 'unknown'


def kind_rank(kind):
    return KIND_RANK.get(kind, 0)


def choose_url(original, resolved):
    """Best URL to show. The original is kept unless the resolved one is a clearly better destination."""
    original, resolved = offer_url(original), offer_url(resolved)
    if not resolved or resolved == original:
        return original or resolved
    if not original:
        return resolved
    ro, rr = kind_rank(classify_url(original)), kind_rank(classify_url(resolved))
    if rr > ro or (rr == ro and is_shortener(original) and not is_shortener(resolved)):
        return resolved
    return original


# --- safe redirect resolution -------------------------------------------------------------------------

USER_AGENT = 'PC2YOU-LinkResolver/1.0 (+redirect-only)'
MAX_REDIRECTS = 6
TIMEOUT = (3, 5)
_CACHE_TTL = 6 * 3600
_cache = {}
_lock = threading.Lock()


def _public_host(host):
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except (socket.gaierror, UnicodeError, OSError):
        return False
    return bool(addresses) and not any(not ip_address(a.split('%')[0]).is_global for a in addresses)


def _fetch(session, url):
    # GET without reading the body: many shorteners reject HEAD. Redirects are followed by us, hop by hop.
    response = session.get(url, allow_redirects=False, stream=True, timeout=TIMEOUT,
                           headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,*/*;q=0.5'})
    response.close()
    return response


def resolve_redirects(url, session=None, *, use_cache=True, now=None):
    """Follow HTTP redirects only. Never raises. Returns a dict describing the result.

    status: 'resolved' (reached another URL), 'unchanged' (no redirect), 'error'.
    """
    base = {'original_url': url, 'resolved_url': None, 'status': 'error', 'hops': 0, 'http_status': None}
    if not isinstance(url, str) or not re.match(r'^https?://', url, re.I):
        return base
    clock = time.monotonic() if now is None else now
    with _lock:
        hit = _cache.get(url) if use_cache else None
        if hit and hit[0] > clock:
            return dict(hit[1])
    if session is None:
        import requests
        session = requests.Session()
        session.max_redirects = MAX_REDIRECTS
    current, result = url, dict(base)
    try:
        for hop in range(MAX_REDIRECTS + 1):
            parsed = urlsplit(current)
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname or not _public_host(parsed.hostname):
                break  # unsafe or unresolvable host: keep status 'error'
            response = _fetch(session, current)
            result['http_status'] = response.status_code
            location = response.headers.get('Location')
            if response.status_code in {301, 302, 303, 307, 308} and location:
                current = urljoin(current, location)
                result['hops'] = hop + 1
                continue
            result['status'] = 'resolved' if current != url else 'unchanged'
            if current != url:
                result['resolved_url'] = current
            break
        else:
            result['status'] = 'error'
    except Exception:  # network/library failures must never break a promotion
        result.update(status='error', resolved_url=None)
    with _lock:
        if len(_cache) > 4096:
            _cache.clear()
        _cache[url] = (clock + _CACHE_TTL, dict(result))
    return result


def link_fields(original_url, resolution=None, checked_at=None):
    """Additive `offer.*` fields describing the best destination; never replaces `offer.url`."""
    resolved = offer_url((resolution or {}).get('resolved_url'))
    best = choose_url(original_url, resolved)
    return {'resolved_url': resolved, 'url_kind': classify_url(best) if best else 'unknown',
            'resolved_kind': classify_url(resolved) if resolved else None,
            'resolved_store': store_from_url(resolved) or store_from_url(original_url),
            'link_status': (resolution or {}).get('status', 'unresolved'),
            'link_hops': (resolution or {}).get('hops', 0), 'link_checked_at': checked_at}
