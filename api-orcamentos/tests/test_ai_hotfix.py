"""Regressions against the actual presentation catalog, without external lookups."""
import json
import sys
from copy import deepcopy
from pathlib import Path

import mongomock
import pytest

from test_ai import post, request, setup  # noqa: F401 (shared endpoint fixture)
from ai_context import enrich

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from backfill_demo_specs import backfill_collection, backfill_jsonl, missing_fields


class SnapshotCatalog:
    def __init__(self):
        self.items = [json.loads(line) for line in (ROOT / "demo-data/components.jsonl").read_text(encoding="utf-8").splitlines()]

    def list_components(self, category):
        return [row for row in self.items if row["category"] == category]

    def search_components(self, category, query):
        # Deliberately literal, like the existing catalog query; normalization must
        # work even when the HTTP search yields no results.
        return [row for row in self.list_components(category)
                if query == row["id"] or query.casefold() in row["name"].casefold()]


@pytest.mark.parametrize("category,name,expected", [
    ("cpu", "Ryzen 5 5600 AMD", "ryzen-5-5600"),
    ("cpu", "  PROCESSADOR amd RYZEN 5-5600!! ", "ryzen-5-5600"),
    ("motherboard", "GIGABYTE Placa mae B550M AM4 DDR4", "b550m-am4-ddr4"),
    ("motherboard", "placa.mãe B550M AM4 DDR4 gigabyte", "b550m-am4-ddr4"),
    ("ram", "Fury Beast 16 GB DDR4 3200 MHz Kingston", "ram-16gb-ddr4"),
    ("gpu", "RTX 3060 12 GB NVIDIA GeForce", "rtx-3060"),
    ("storage", "nv3 1 TB NVMe M.2 Kingston", "ssd-nvme-1tb"),
    ("psu", "CORSAIR fonte 650 W 80 plus bronze", "fonte-650w"),
    ("motherboard", "b550m-am4-ddr4", "b550m-am4-ddr4"),
])
def test_normalized_names_use_real_catalog(category, name, expected):
    assert enrich(name, category, SnapshotCatalog())["catalog_id"] == expected


@pytest.mark.parametrize("category,name", [
    ("cpu", "Ryzen 5 5600 Intel"),
    ("motherboard", "Placa mae B550M AM4 DDR5"),
    ("motherboard", "Placa mae B550M AM4 DDR4 ASUS"),
    ("ram", "Kingston Fury Beast 17GB DDR4 3200MHz"),
    ("gpu", "RTX 3060 8 GB"), ("gpu", "RTX 3060 Ti 12GB"),
    ("storage", "Kingston NV3 2TB NVMe M.2"),
    ("psu", "Fonte 750W 80 Plus Bronze"), ("cpu", "Ryzen 5"),
])
def test_variants_conflicts_and_partial_names_remain_unverified(category, name):
    item = enrich(name, category, SnapshotCatalog())
    assert item["source"] == "user"
    assert item["catalog_id"] is None
    assert item["specifications"] == item["compatibility"] == {}


def test_ambiguity_is_checked_beyond_the_literal_search():
    catalog = SnapshotCatalog()
    row = deepcopy(next(row for row in catalog.items if row["id"] == "ryzen-5-5600"))
    row.update(id="another-5600", name="Ryzen 5 5600 AMD")
    catalog.items.append(row)
    assert enrich("AMD Ryzen 5 5600", "cpu", catalog)["source"] == "user"
    assert enrich("ryzen-5-5600", "cpu", catalog)["catalog_id"] == "ryzen-5-5600"
    assert enrich("ryzen-5-5600", "motherboard", catalog)["source"] == "user"


def test_existing_brand_alias_is_reused():
    catalog = SnapshotCatalog()
    catalog.items = [{"id": "wd-sn770", "category": "storage", "brand": "Western Digital", "name": "Western Digital SN770 1TB NVMe"}]
    assert enrich("SN770 1 TB NVMe WD", "storage", catalog)["catalog_id"] == "wd-sn770"


def demo_request():
    return request(components={
        "cpu": "AMD Ryzen 5 5600", "gpu": "GeForce RTX 3060 12 GB",
        "motherboard": "Placa-mãe B550M AM4 DDR4", "ram": "kingston-kf432c16bb-16",
        "storage": ["Kingston NV3 1TB NVMe M.2"], "psu": "Fonte 650W 80 Plus Bronze",
        "case": "Gabinete Gamer Rise Mode Glass",
    })


def test_main_demo_has_specs_and_all_existing_rules_verified(setup):
    catalog = SnapshotCatalog()
    setup.catalog.items = catalog.items
    setup.catalog.search_components = catalog.search_components
    response = post(setup, demo_request())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["metadata"]["catalog_matches"] == 7
    assert data["compatibility"]["valid"] is True
    assert len(data["compatibility"]["checked_rules"]) == 7
    assert data["compatibility"]["unchecked_rules"] == []
    assert data["analysis"]["missing_information"] == []
    parts = {row["category"]: row for row in data["components"]}
    assert parts["cpu"]["compatibility"]["socket"] == parts["motherboard"]["compatibility"]["socket"] == "AM4"
    assert parts["ram"]["compatibility"]["memory_type"] == "DDR4"
    assert parts["gpu"]["specifications"]["memory"] == "12GB GDDR6"
    assert parts["storage"]["specifications"]["capacity"] == "1TB"
    assert parts["psu"]["specifications"]["wattage"] == 650


def test_alert_deduplication_does_not_change_validation_or_context(setup):
    body = request()
    body["components"]["motherboard"] = "Placa desconhecida"
    warning = "Compatibilidade parcial: faltam campos técnicos confiáveis para uma ou mais regras."
    setup.provider.output["warnings"] = [warning, "  Compatibilidade parcial: faltam campos tecnicos confiaveis para uma ou mais regras  ", "Confira os conectores."]
    setup.provider.output["missing_information"] = ["Placa-mae: especificacoes nao verificadas no catalogo"]
    data = post(setup, body).json()
    assert data["analysis"]["warnings"] == [warning, "Confira os conectores."]
    assert data['analysis']['missing_information'] == setup.provider.calls[0]['context']['trusted_context']['missing_information']
    assert all('confirmar' in m for m in data['analysis']['missing_information'])
    assert data["analysis"]["primary_limit"]["confidence"] == "low"
    assert data["compatibility"]["valid"] is None
    assert setup.provider.calls[0]["context"]["trusted_context"]["compatibility"] == data["compatibility"]
    setup.provider.output["warnings"].append("Compre RTX 6070 Ultra.")
    setup.service._cache.clear()
    assert post(setup, body).status_code == 502  # Validation still precedes formatting.


def test_bare_demo_id_cannot_authorize_a_hardcoded_128gb_backfill(tmp_path):
    row = {"id": "b550m-am4-ddr4", "category": "motherboard", "technical_specs": {"memory_slots": 4}}
    path = tmp_path / "components.jsonl"
    original = json.dumps(row) + "\n"
    path.write_text(original, encoding="utf-8")
    assert backfill_jsonl(path) == []
    assert path.read_text(encoding="utf-8") == original
    assert missing_fields(row) == {}
    collection = mongomock.MongoClient().demo.components
    collection.insert_one(deepcopy(row))
    assert backfill_collection(collection, apply=True) == []
    assert collection.find_one()["technical_specs"] == {"memory_slots": 4}


def test_new_5600x_is_a_distinct_real_identity():
    catalog = SnapshotCatalog()
    assert enrich("Ryzen 5 5600X AMD", "cpu", catalog)["catalog_id"] == "ryzen-5-5600x"
    assert enrich("Ryzen 5 5600 AMD", "cpu", catalog)["catalog_id"] == "ryzen-5-5600"
