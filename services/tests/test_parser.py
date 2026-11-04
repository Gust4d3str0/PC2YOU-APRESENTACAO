from decimal import Decimal

import pytest

from services.telegram_collector.filters import is_possible_promotion
from services.telegram_collector.parser import extract_coupon, extract_prices, extract_urls, identify_store, parse_message


@pytest.mark.parametrize("text", ["PROMOÇÃO", "promocao", "cupom", "R$ 100", "PIX", "memória", "placa mãe", "GPU", "Pichau", "mercado livre"])
def test_filter_accepts_keywords(text):
    assert is_possible_promotion(text)


@pytest.mark.parametrize("text", [None, "", "  ", 42, {}, "Bom dia", "programacao", "campix", "transformar"])
def test_filter_rejects_empty_invalid_and_substrings(text):
    assert not is_possible_promotion(text)


@pytest.mark.parametrize("text,expected", [
    ("R$ 1.899", "1899"), ("R$ 1.899,90", "1899.90"),
    ("1899,90", "1899.90"), ("R$1899", "1899"), ("R$ 99,90", "99.90"),
    ("SSD por R$ 100.", "100"), ("Por R$ 100,00, aproveite", "100.00"),
])
def test_price_formats(text, expected):
    assert extract_prices(text) == (Decimal(expected), None)


def test_original_and_current_price(messages):
    assert extract_prices(messages["gpu"]) == (Decimal("3599.90"), Decimal("4099.90"))
    assert extract_prices(messages["cpu"]) == (Decimal("2399"), None)


def test_installments_and_shipping_do_not_replace_total(messages):
    assert extract_prices(messages["installments"]) == (Decimal("1899.90"), None)
    assert extract_prices("SSD em 12x de R$ 100,00") == (None, None)
    assert extract_prices("Frete R$ 20,00") == (None, None)


@pytest.mark.parametrize("text", ["RTX 5070 12GB", "10,00% de desconto", "https://shop.test/1899,90", "R$ 0", "De R$ 4.000", "R$ 100 e R$ 200"])
def test_price_ambiguity_and_non_prices(text):
    assert extract_prices(text)[0] is None


def test_multiple_current_prices_are_ambiguous(messages):
    assert extract_prices(messages["multiple"])[0] is None


@pytest.mark.parametrize("text,expected", [("Cupom: GPU10", "GPU10"), ("Cupom:GPU10", "GPU10"), ("cupom GPU10", "GPU10"), ("use GPU10", "GPU10"), ("Cupom AMD100", "AMD100"), ("use o cupom", None), ("Cupom: desconto", None), ("Cupom A10 ou cupom B20", None)])
def test_coupons(text, expected):
    assert extract_coupon(text) == expected


def test_urls_are_unique_and_include_hidden_links():
    assert extract_urls("Veja https://shop.test/item. https://shop.test/item", ["https://amzn.to/123", "tg://user?id=1", "https://[invalid"]) == ["https://shop.test/item", "https://amzn.to/123"]


@pytest.mark.parametrize("text,expected", [
    ("KaBuM", "KaBuM"), ("Pichau", "Pichau"), ("Terabyte", "Terabyte"),
    ("Amazon", "Amazon"), ("Mercado Livre", "Mercado Livre"),
    ("https://www.kabum.com.br/produto/10", "KaBuM"),
    ("https://www.terabyteshop.com.br/item", "Terabyte"),
    ("https://amzn.to/abcd", "Amazon"),
    ("https://mercadolivre.com.br/item", "Mercado Livre"),
    ("https://evilkabum.com.br/item", None),
    ("https://evil.test/kabum", None),
    ("Amazon ou Pichau", None), ("Loja desconhecida", None),
])
def test_known_stores_and_domain_boundaries(text, expected):
    assert identify_store(text) == expected


@pytest.mark.parametrize("text", [None, "", "  ", 42, [], {}])
def test_invalid_messages_return_null_fields(text):
    parsed = parse_message(text)
    assert all(value is None for value in parsed["offer"].values())
    assert all(value is None for value in parsed["product"].values())
    assert parsed["links"] == []


def test_parser_preserves_unknown_product_and_reliable_fields(messages):
    parsed = parse_message(messages["gpu"])
    assert parsed["product"] == {"name": None, "normalized_key": None, "component_id": None, "component_type": "gpu"}
    assert parsed["offer"]["coupon"] == "GPU10"
    assert parsed["offer"]["store"] == "KaBuM"
    assert parsed["offer"]["url"] == parsed["links"][0]
    assert parse_message("CPU Ryzen com GPU RTX 5070")["product"]["component_type"] is None
