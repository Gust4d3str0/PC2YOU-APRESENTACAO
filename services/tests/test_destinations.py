import asyncio
from types import SimpleNamespace

import pytest

from services.product_matching import destinations as d
from services.telegram_collector import collector
from services.telegram_collector.collector import process_message


@pytest.mark.parametrize("url,store", [
    ("https://www.kabum.com.br/produto/1", "Kabum"), ("https://www.pichau.com.br/x", "Pichau"),
    ("https://www.terabyteshop.com.br/produto/1", "Terabyte"), ("https://www.amazon.com.br/dp/B0C1234567", "Amazon"),
    ("https://produto.mercadolivre.com.br/MLB-123", "Mercado Livre"), ("https://www.magazineluiza.com.br/p/abc/", "Magazine Luiza"),
    ("https://example.com/produto/1", None), ("https://pruuu.me/x", None), ("https://meli.la/abc", None), (None, None),
])
def test_store_is_identified_from_domain_only(url, store):
    assert d.store_from_url(url) == store


@pytest.mark.parametrize("url,kind", [
    ("https://www.kabum.com.br/produto/123456/placa", "product"), ("https://www.amazon.com.br/dp/B0C1234567?tag=x", "product"),
    ("https://www.pichau.com.br/placa-de-video-asus-dual-geforce-rtx-5060-8gb", "product"),
    ("https://www.mercadolivre.com.br/p/MLB123456", "product"),
    ("https://www.kabum.com.br/busca/rtx-5060", "search"), ("https://www.pichau.com.br/search?q=rtx", "search"),
    ("https://www.amazon.com.br/s?k=rtx+5060", "search"), ("https://www.terabyteshop.com.br/procura?q=x", "search"),
    ("https://www.kabum.com.br/", "homepage"), ("http://www.pichau.com.br", "homepage"),
    ("https://meli.la/abc", "unknown"), ("https://example.com/qualquer", "unknown"), ("javascript:alert(1)", "unknown"),
])
def test_destination_classification(url, kind):
    assert d.classify_url(url) == kind


def test_product_link_has_priority_and_original_is_preserved():
    product, search = "https://www.kabum.com.br/produto/1/x", "https://www.kabum.com.br/busca/x"
    assert d.choose_url(product, search) == product          # original product deep link is kept
    assert d.choose_url("https://pruuu.me/x", product) == product
    assert d.choose_url(search, product) == product
    assert d.choose_url("https://pruuu.me/x", "http://www.pichau.com.br") == "http://www.pichau.com.br"
    assert d.choose_url("https://pruuu.me/x", None) == "https://pruuu.me/x"
    assert d.choose_url(product, "https://www.kabum.com.br/") == product


class Resp:
    def __init__(self, status=200, location=None):
        self.status_code, self.headers = status, ({"Location": location} if location else {})

    def close(self):
        pass


class Session:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, **kwargs):
        assert kwargs["allow_redirects"] is False and kwargs["timeout"] and "PC2YOU" in kwargs["headers"]["User-Agent"]
        self.calls.append(url)
        route = self.routes[url]
        if isinstance(route, Exception):
            raise route
        return route


@pytest.fixture(autouse=True)
def public_hosts(monkeypatch):
    monkeypatch.setattr(d, "_public_host", lambda host: host != "localhost")
    d._cache.clear()


def test_redirect_chain_is_resolved_with_relative_location_and_cached():
    session = Session({"https://pruuu.me/a": Resp(302, "https://t.co/b"), "https://t.co/b": Resp(301, "/produto/9"),
                       "https://t.co/produto/9": Resp(200)})
    result = d.resolve_redirects("https://pruuu.me/a", session)
    assert (result["status"], result["hops"], result["resolved_url"]) == ("resolved", 2, "https://t.co/produto/9")
    d.resolve_redirects("https://pruuu.me/a", session)
    assert len(session.calls) == 3                               # second call served from cache


def test_no_redirect_is_unchanged_and_errors_never_raise():
    ok = d.resolve_redirects("https://a.com/x", Session({"https://a.com/x": Resp(200)}))
    assert ok["status"] == "unchanged" and ok["resolved_url"] is None
    boom = d.resolve_redirects("https://b.com/x", Session({"https://b.com/x": TimeoutError("slow")}))
    assert boom["status"] == "error" and boom["resolved_url"] is None


def test_redirect_loop_limit_and_private_hosts_are_refused():
    loop = Session({"https://l.com/a": Resp(302, "https://l.com/a")})
    assert d.resolve_redirects("https://l.com/a", loop)["resolved_url"] is None
    assert len(loop.calls) == d.MAX_REDIRECTS + 1
    local = Session({"https://l.com/s": Resp(302, "http://localhost:8000/admin")})
    result = d.resolve_redirects("https://l.com/s", local)
    assert result["resolved_url"] is None and local.calls == ["https://l.com/s"]
    assert d.resolve_redirects("ftp://x.com/a", Session({}))["status"] == "error"


def test_link_fields_are_additive_and_describe_best_destination():
    res = {"resolved_url": "https://www.kabum.com.br/produto/1/x", "status": "resolved", "hops": 1}
    fields = d.link_fields("https://pruuu.me/a", res, "now")
    assert fields["resolved_url"] and fields["url_kind"] == "product" and fields["resolved_store"] == "Kabum"
    failed = d.link_fields("https://pruuu.me/a", {"status": "error"}, "now")
    assert failed["resolved_url"] is None and failed["url_kind"] == "unknown"


def test_repository_stores_resolution_without_replacing_original_url(repository):
    repository.promotions.insert_one({"telegram": {"chat_id": -1, "message_id": 1}, "offer": {"url": "https://pruuu.me/a", "price": 1}})
    identity = {"telegram.chat_id": -1, "telegram.message_id": 1}
    calls = []
    resolver = lambda url: calls.append(url) or {"resolved_url": "https://www.kabum.com.br/produto/1/x", "status": "resolved", "hops": 1}
    assert repository.resolve_link(identity, resolver)
    offer = repository.promotions.find_one(identity)["offer"]
    assert offer["url"] == "https://pruuu.me/a" and offer["resolved_url"].endswith("/produto/1/x") and offer["url_kind"] == "product"
    assert repository.resolve_link(identity, resolver) is None and len(calls) == 1      # already checked
    crashing = lambda url: {"status": "error", "resolved_url": None}
    repository.resolve_link(identity, crashing, force=True)
    assert repository.promotions.find_one(identity)["offer"]["url"] == "https://pruuu.me/a"


def test_collector_resolves_new_promotion_in_background_and_failure_is_harmless(repository, settings, message, channel, monkeypatch):
    monkeypatch.setattr(collector, "LINK_RESOLUTION_ENABLED", True)
    seen = []

    def boom(identity, *a, **k):
        seen.append(identity)
        raise RuntimeError("network down")
    monkeypatch.setattr(repository, "resolve_link", boom)

    async def run():
        saved = await process_message(message, channel, settings, repository)
        await asyncio.gather(*list(collector._background))
        return saved
    assert asyncio.run(run()) and len(seen) == 1 and repository.promotions.count_documents({}) == 1
