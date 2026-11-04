from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128

from services.telegram_collector.matcher import matches_alert, normalize_terms, product_identity


def promotion(text="🔥 GALAX GeForce RTX-5070 12 GB", price=3599, store="KaBuM", original=4099):
    return {"raw_text": text, "product": {}, "offer": {"price": price, "store": store, "original_price": original, "coupon": "GPU10"}, "status": "parsed"}


def alert(query="RTX 5070", **kwargs):
    return {"query": query, "enabled": True, "max_price": Decimal("3800"), **kwargs}


def test_normalization_preserves_variants_and_units():
    assert normalize_terms("GeForce RTX-5070 12 GB") == ["rtx", "5070", "12gb"]
    assert normalize_terms("RTX5070Ti SUPER") == ["rtx", "5070", "ti", "super"]
    assert normalize_terms("7800X3D") != normalize_terms("7900X3D")


@pytest.mark.parametrize("query,text,expected", [
    ("RTX 5070", "GALAX GeForce RTX-5070 12 GB", True),
    ("RTX 5070", "RTX 5070 Ti", False), ("RTX 5070 Ti", "RTX5070TI", True),
    ("RTX 5070 Ti", "RTX 5070", False), ("RTX 5070", "RTX 5070 SUPER", False),
    ("RTX 4060", "RTX 4060 Ti", False), ("RTX 5070", "RTX 5070 ou RTX 5070 Ti", False),
    ("RX 9070", "Sapphire RX 9070 XT", False), ("RX 9070 XT", "XFX RX9070XT", True),
    ("RX 9070 XT", "RX 9070 XTX", False),
    ("7800X3D", "Ryzen 7 7800X3D", True), ("7800X3D", "Ryzen 9 7900X3D", False),
    ("DDR5 6000", "Memória DDR5 6000", True), ("B650", "ASUS B650", True),
    ("RTX 5070 12GB", "RTX 5070 12 GB", True),
    ("5070", "RTX 5070 Ti", False), ("5070 Ti", "RTX 5070 Ti", True),
    ("5070", "RTX 4060 por R$ 5070", False),
    ("RTX 5070", "Uma peça qualquer\nCupom RTX5070", False),
])
def test_exact_matching_and_variants(query, text, expected):
    assert matches_alert(promotion(text), alert(query)) is expected


@pytest.mark.parametrize("price,maximum,expected", [(3800, 3800, True), (3801, 3800, False), (Decimal128("3599.90"), None, True), (None, None, False), ("NaN", None, False), (0, None, False)])
def test_price_limits_and_missing_price(price, maximum, expected):
    assert matches_alert(promotion(price=price), alert(max_price=maximum)) is expected


@pytest.mark.parametrize("filters,expected", [
    ({"brands": ["galax"]}, True), ({"brands": ["MSI"]}, False),
    ({"ignored_brands": ["GaLaX"]}, False),
    ({"brands": ["GALAX"], "ignored_brands": ["galax"]}, False),
    ({"stores": ["kabum"]}, True), ({"stores": ["Amazon"]}, False),
    ({"ignored_stores": ["KaBuM"]}, False), ({"stores": []}, True),
    ({"minimum_discount": Decimal128("10")}, True),
    ({"minimum_discount": 20}, False), ({"enabled": False}, False),
    ({"component_type": "cpu"}, False),
])
def test_filters(filters, expected):
    assert matches_alert(promotion(), alert(**filters)) is expected


def test_missing_store_and_discount_data():
    assert matches_alert(promotion(store=None), alert())
    assert not matches_alert(promotion(store=None), alert(stores=["KaBuM"]))
    assert matches_alert(promotion(original=None), alert())
    assert matches_alert(promotion(original=None), alert(minimum_discount=10))


def test_product_keys_for_equivalent_messages():
    assert product_identity(promotion("RTX 5070\nKaBuM")) == product_identity(promotion("🔥 GeForce RTX-5070\nOferta KaBuM"))
    assert product_identity(promotion()) != product_identity(promotion("MSI RTX 5070 12 GB"))
    assert product_identity(promotion("Uma peça desconhecida")) is None
