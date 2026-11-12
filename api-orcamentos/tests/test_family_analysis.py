"""Family bounds, backend sufficiency, upgrade assessment and provider fallback (no Gemini, no Atlas)."""
import sys
from copy import deepcopy
from pathlib import Path

import pytest

SERVICES = Path(__file__).resolve().parents[2] / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))

from ai.errors import AIError, AIInvalidResponseError
from ai.schemas import AnalyzePCRequest
from ai.service import AIService
from ai.config import AISettings
from ai_context import build_context, check_compatibility, trusted_field
from catalog_specs.external_identity import search_metadata
from catalog_specs.family_bounds import summarize_field
from catalog_specs.human_index import family_projections
from catalog_specs.lookup import LocalCatalog
from catalog_specs.human_resolver import resolve_input
from catalog_specs.human_input import parse_input


def row(category, name, scope=None, **parts):
    result = {"id": name.lower().replace(" ", "-"), "name": name, "category": category,
              "brand": parts.pop("brand", "Marca"), "technical_specs": parts.pop("specs", {}),
              "compatibility": parts.pop("compat", {}), "prices": [],
              "identity_scope": scope or ("model" if category == "cpu" else "sku")}
    result.update(parts)
    result.update(search_metadata(result))
    return result


def board(name, slots, max_gb, scope="sku", form="Micro-ATX"):
    return row("motherboard", name, scope, specs={"memory_slots": slots, "max_memory_gb": max_gb} if slots else {},
               compat={"socket": "AM4", "memory_type": "DDR4", "form_factor": form}, brand=name.split()[0])


def gpu(name, length=None, psu=None, scope="sku"):
    return row("gpu", name, scope, specs={"memory": "8GB", **({"length_mm": length} if length else {})},
               compat={"min_psu_watts": psu} if psu else {}, brand="NVIDIA")


def rows(extra=()):
    return [
        row("cpu", "AMD Ryzen 7 5700X", specs={"cores": 8, "threads": 16, "tdp_watts": 65}, compat={"socket": "AM4"}, brand="AMD"),
        board("Placa-mãe B550M AM4 DDR4", 4, 128, scope="family"),
        board("Gigabyte B550M K", 4, 128), board("ASUS B550M-A", 4, 128), board("MSI B550M-X", 2, 64),
        gpu("GeForce RTX 4060 Ti", psu=550, scope="family"),
        gpu("Asus GeForce RTX 4060 Ti Dual 8GB", 227), gpu("MSI GeForce RTX 4060 Ti Ventus 8GB", 250),
        row("kit-ram", "Kingston Fury 32GB (2x16GB) DDR4 3200", specs={"capacity": "32GB", "modules": "2x16GB", "speed": "3200MHz"},
            compat={"memory_type": "DDR4"}),
        *extra,
    ]


def pc(**changes):
    base = dict(cpu="Ryzen 7 5700X", motherboard="B550M", ram="2x16GB DDR4 3200", gpu="RTX 4060 Ti",
                storage=["1TB NVMe"], psu="650W", case="ATX")
    base.update(changes)
    return {key: value for key, value in base.items() if value}


def context(components, catalog=None, **request):
    catalog = catalog or LocalCatalog(rows())
    return build_context(AnalyzePCRequest(components=components, usage=request.pop("usage", ["gaming"]), **request), catalog)


def analysis(**changes):
    value = {"summary": "O conjunto está bem posicionado para o uso informado.", "overall_rating": "good",
             "balance": {"status": "balanced", "explanation": "Os componentes formam um conjunto coerente."},
             "primary_limit": None, "strengths": ["A memória é ampla."], "weaknesses": ["Nenhum ponto crítico identificado no cenário informado."],
             "upgrade_priorities": [], "warnings": [], "missing_information": [],
             "final_recommendation": "Nenhum upgrade urgente é necessário."}
    value.update(changes)
    return value


class Provider:
    name = "double"

    def __init__(self, output=None, error=None):
        self.output, self.error, self.calls = output if output is not None else analysis(), error, []

    def generate(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if self.error:
            raise self.error
        return deepcopy(self.output)


def service(provider):
    return AIService(AISettings(enabled=True, api_key="x", cache_ttl=300, requests_per_minute=100), provider)


# ---- family statistics -------------------------------------------------------------------------

def test_family_statistics_report_coverage_min_max_and_consensus():
    stats = summarize_field(rows()[2:5], "technical_specs.memory_slots", numeric=True)
    assert (stats["candidate_count"], stats["known_count"], stats["min"], stats["max"]) == (3, 3, 2, 4)
    assert stats["consensus"] is None and stats["safe_min"] == 2 and stats["safe_max"] == 4
    same = summarize_field(rows()[2:4], "technical_specs.memory_slots", numeric=True)
    assert same["consensus"] == 4


def test_unknown_candidates_make_a_bound_unsafe():
    members = [board("A B550M", 4, 128), board("B B550M", None, None)]
    stats = summarize_field(members, "technical_specs.memory_slots", numeric=True)
    assert stats["known_count"] == 1 and stats["coverage"] == 0.5
    assert stats["safe_min"] is None and stats["safe_max"] is None


def test_projection_is_materialized_offline_with_bounds():
    projection = next(p for p in family_projections(rows()) if p["key"] == "board:B550M:DDR4")
    assert projection["bounds"]["technical_specs.memory_slots"]["min"] == 2
    assert projection["bounds"]["technical_specs.max_memory_gb"]["safe_min"] == 64
    gpu_projection = next(p for p in family_projections(rows()) if p["category"] == "gpu")
    assert gpu_projection["bounds"]["compatibility.min_psu_watts"]["safe_max"] == 550


# ---- PC A / B / C / D --------------------------------------------------------------------------

def test_pc_a_is_proved_by_family_bounds_and_is_sufficient():
    trusted = context(pc())["trusted_context"]
    verdict = trusted["compatibility"]
    assert {"cpu_socket", "ram_type", "ram_slots", "ram_capacity", "gpu_power"} <= set(verdict["checked_rules"])
    assert "gpu_case" in verdict["unchecked_rules"]
    assert verdict["rule_sources"]["ram_slots"] == verdict["rule_sources"]["ram_capacity"] == "catalog_family_bound"
    assert verdict["status"] == "partial" and not verdict["issues"]
    evidence = {e["rule"]: e for e in verdict["evidence"]}
    assert evidence["ram_slots"]["evidence"]["min"] == 2 and evidence["ram_slots"]["evidence"]["candidate_count"] == 4
    assert evidence["gpu_power"]["evidence"]["bound_used"] == 550
    assert all(item["source"] != "user" for item in trusted["build"])
    assert trusted["analysis_readiness"]["status"] == "sufficient"  # Pending physical rules do not make it insufficient.
    assert trusted["upgrade_blockers"] == {"gpu": ["gpu_case"]}
    assert not any(c["component_type"] == "gpu" for c in trusted["upgrade_candidates"])


def test_pc_a_end_to_end_is_not_insufficient_and_has_an_explicit_upgrade_state():
    ctx = context(pc())
    result = service(Provider()).analyze_pc(ctx)
    assert result.metadata.analysis_source == "gemini"
    assert result.compatibility.status == "partial"
    assert result.analysis.balance.status == "balanced" and result.analysis.primary_limit is None
    assert result.upgrade_assessment.status == "no_priority"
    assert result.readiness.status == "sufficient"
    assert not any("Compatibilidade parcial" in w for w in result.analysis.warnings)


def test_model_cannot_call_a_sufficient_context_insufficient():
    provider = Provider(analysis(overall_rating="insufficient_data", balance={"status": "insufficient_data", "explanation": "x"}))
    with pytest.raises(AIInvalidResponseError):
        service(provider).analyze_pc(context(pc()))
    schema = provider.calls and provider.calls[0]["schema"]
    from ai.contract import analysis_schema
    assert "insufficient_data" not in analysis_schema(context(pc()))["properties"]["overall_rating"]["enum"]


def test_upgrade_priority_without_candidate_is_partial_when_a_physical_rule_blocks_the_product():
    priority = {"priority": 1, "component_type": "gpu", "reason": "A placa de vídeo é a próxima categoria.",
                "expected_benefit": "Mais margem gráfica.", "budget_relevance": "no_budget", "candidate_id": None}
    result = service(Provider(analysis(upgrade_priorities=[priority]))).analyze_pc(context(pc()))
    assert result.upgrade_assessment.status == "partial" and result.upgrade_assessment.blocked_types == ["gpu"]
    ram = {**priority, "component_type": "ram"}
    result = service(Provider(analysis(upgrade_priorities=[ram]))).analyze_pc(context(pc()))
    assert result.upgrade_assessment.status == "priorities_available"


def test_pc_b_does_not_claim_rules_that_some_candidate_may_fail():
    verdict = context(pc(ram="4x32GB DDR4", psu="450W"))["trusted_context"]["compatibility"]
    assert "ram_slots" not in verdict["checked_rules"] and "ram_capacity" not in verdict["checked_rules"]
    assert "ram_slots" in verdict["unchecked_rules"] and "ram_capacity" in verdict["unchecked_rules"]
    assert verdict["status"] == "incompatible" and "gpu_power" in verdict["failed_rules"]


def test_family_wide_refutation_is_incompatible_but_straddling_is_not():
    too_much = context(pc(ram="2x128GB DDR4"))["trusted_context"]["compatibility"]
    assert "ram_capacity" in too_much["failed_rules"]  # No B550M candidate holds 256GB.
    many = context(pc(ram="8x8GB DDR4"))["trusted_context"]["compatibility"]
    assert "ram_slots" in many["failed_rules"]  # No candidate has 8 slots.
    four = context(pc(ram="4x8GB DDR4"))["trusted_context"]["compatibility"]
    assert "ram_slots" in four["unchecked_rules"] and not four["failed_rules"]


def test_pc_c_ambiguous_input_stays_unresolved_and_is_insufficient():
    ctx = context({"cpu": "Ryzen", "gpu": "RTX", "motherboard": "placa", "ram": "memoria", "psu": "fonte"})
    trusted = ctx["trusted_context"]
    assert trusted["analysis_readiness"]["status"] == "insufficient" and not trusted["compatibility"]["checked_rules"]
    assert all(item["source"] == "user" for item in trusted["build"])
    assert trusted["upgrade_candidates"] == []
    result = service(Provider(analysis(overall_rating="insufficient_data", balance={"status": "insufficient_data", "explanation": "x"}))).analyze_pc(ctx)
    assert result.upgrade_assessment.status == "insufficient" and result.upgrade_assessment.readiness_reasons


def test_cpu_only_is_insufficient():
    trusted = context({"cpu": "Ryzen"})["trusted_context"]
    assert trusted["analysis_readiness"]["status"] == "insufficient"
    assert "cpu_not_recognized" in trusted["analysis_readiness"]["reasons"]


def test_pc_d_exact_sku_keeps_using_its_own_data():
    trusted = context(pc(motherboard="Gigabyte B550M K", case="ATX mATX GPU até 350mm",
                         gpu="RTX 4060 Ti comprimento 240mm"))["trusted_context"]
    verdict = trusted["compatibility"]
    assert "ram_slots" in verdict["checked_rules"] and "ram_capacity" in verdict["checked_rules"]
    assert "catalog_family_bound" not in (verdict["rule_sources"]["ram_slots"], verdict["rule_sources"]["ram_capacity"])
    board_item = next(i for i in trusted["build"] if i["category"] == "motherboard")
    assert board_item["resolution_scope"] == "sku" and not board_item.get("family_bounds")
    assert "gpu_case" in verdict["checked_rules"] and verdict["rule_sources"]["gpu_case"] == "user_text"


def test_partial_family_coverage_without_model_level_evidence_is_not_trusted():
    catalog = LocalCatalog([r for r in rows() if r["name"] != "GeForce RTX 4060 Ti"] + [gpu("GeForce RTX 4060 Ti Placeholder SKU", psu=None)])
    boards = [r for r in rows() if r["category"] == "motherboard" and r["name"] != "Placa-mãe B550M AM4 DDR4"]
    boards.append(board("Unknown Slots B550M", None, None))
    catalog = LocalCatalog([r for r in rows() if r["category"] != "motherboard"] + boards)
    verdict = context(pc(), catalog)["trusted_context"]["compatibility"]
    assert "ram_slots" not in verdict["checked_rules"]


def test_trusted_field_requires_proving_statistics():
    item = {"source": "derived", "specifications": {}, "compatibility": {}, "family_bounds": {},
            "field_sources": {"technical_specs.memory_slots": "catalog_family_bound"}}
    assert not trusted_field(item, "technical_specs", "memory_slots")
    item["family_bounds"] = {"technical_specs.memory_slots": summarize_field(rows()[2:5], "technical_specs.memory_slots", numeric=True)}
    assert trusted_field(item, "technical_specs", "memory_slots")
    item["field_sources"]["technical_specs.memory_slots"] = "catalog_family_consensus"
    assert not trusted_field(item, "technical_specs", "memory_slots")  # 2 vs 4 slots: no consensus


# ---- upgrade candidates are judged per replacement ---------------------------------------------

def test_partial_compatibility_no_longer_hides_unrelated_specific_candidates():
    extra = row("kit-ram", "Corsair Vengeance 64GB (2x32GB) DDR4 3600", specs={"capacity": "64GB", "modules": "2x32GB"}, compat={"memory_type": "DDR4"})
    trusted = context(pc(), LocalCatalog(rows([extra])))["trusted_context"]
    assert trusted["compatibility"]["status"] == "partial"
    assert [c["name"] for c in trusted["upgrade_candidates"] if c["component_type"] == "ram"] == ["Corsair Vengeance 64GB (2x32GB) DDR4 3600"] or \
        any(c["component_type"] == "ram" for c in trusted["upgrade_candidates"])
    assert not any(c["component_type"] == "gpu" for c in trusted["upgrade_candidates"])


# ---- deterministic technical assessment --------------------------------------------------------

def test_technical_assessment_describes_the_pc_with_catalog_facts():
    profile = context(pc(ram="2x32GB DDR4 3200"))["trusted_context"]["technical_assessment"]
    assert profile["cpu"]["threads"] == 16 and profile["cpu"]["socket"] == "AM4"
    assert profile["ram"]["total_gb"] == 64 and profile["psu"]["headroom"] == "comfortable"
    ids = {f["id"] for f in profile["findings"]}
    assert {"cpu_threads_strong", "ram_ample", "storage_nvme", "psu_comfortable", "cpu_gpu_balanced"} <= ids
    assert profile["upgrade_order"] == [] or profile["next_logical_category"] is None
    assert not any("compatib" in f["text"].lower() for f in profile["findings"])


def test_generational_imbalance_is_detected_from_catalog_data_only():
    old = row("cpu", "Intel Core i5 6600", specs={"cores": 4, "threads": 4, "tdp_watts": 65}, compat={"socket": "LGA1151"}, brand="Intel")
    top = gpu("GeForce RTX 4080", psu=750, scope="family")
    catalog = LocalCatalog(rows([old, top]))
    profile = context(pc(cpu="i5 6600", gpu="RTX 4080", psu="850W"), catalog)["trusted_context"]["technical_assessment"]
    assert profile["balance"]["cpu_gpu"] == "cpu_limits_gpu"
    assert profile["upgrade_order"][0]["component"] == "cpu"
    assert any(f["id"] == "cpu_gpu_imbalance" and f["kind"] == "alert" for f in profile["findings"])


def test_low_memory_and_hdd_become_improvements_not_compatibility_noise():
    profile = context(pc(ram="8GB DDR4", storage=["1TB HDD"]))["trusted_context"]["technical_assessment"]
    kinds = {f["id"]: f["kind"] for f in profile["findings"]}
    assert kinds["ram_low"] == "improvement" and kinds["storage_hdd"] == "improvement"
    assert {entry["component"] for entry in profile["upgrade_order"]} >= {"ram", "storage"}


# ---- confidence, primary limit, fallback -------------------------------------------------------

def test_unrelated_pending_rule_does_not_lower_confidence_and_unknown_becomes_null():
    limit = {"component": "cpu", "confidence": "high", "explanation": "O processador é o ponto a observar."}
    result = service(Provider(analysis(primary_limit=limit))).analyze_pc(context(pc()))
    assert result.analysis.primary_limit.confidence == "high"
    unknown = {"component": "unknown", "confidence": "low", "explanation": "Sem limitante confirmado."}
    result = service(Provider(analysis(primary_limit=unknown))).analyze_pc(context(pc()))
    assert result.analysis.primary_limit is None


@pytest.mark.parametrize("code", ["timeout", "unavailable", "overloaded"])
def test_gemini_outage_returns_a_labelled_technical_fallback(code):
    provider = Provider(error=AIError(code, "indisponível", 503))
    svc = service(provider)
    result = svc.analyze_pc(context(pc(ram="2x32GB DDR4 3200")))
    assert result.metadata.analysis_source == "deterministic_fallback" and result.metadata.fallback_reason == code
    assert result.compatibility.checked_rules and result.compatibility.status == "partial"
    assert result.analysis.strengths and not any("pendente" in text.lower() for text in result.analysis.weaknesses)
    assert result.analysis.weaknesses and result.analysis.final_recommendation
    assert result.upgrade_assessment.status in {"no_priority", "priorities_available", "partial"}
    assert not svc._cache  # Never cached: the next request retries the provider.


def test_fallback_reports_real_conflicts_first():
    result = service(Provider(error=AIError("timeout", "x", 504))).analyze_pc(context(pc(psu="450W")))
    assert result.compatibility.status == "incompatible" and result.analysis.overall_rating == "attention"
    assert result.analysis.upgrade_priorities[0].component_type == "psu" and result.analysis.upgrade_priorities[0].candidate_id is None
    assert result.upgrade_assessment.status == "priorities_available"


def test_invalid_model_output_is_still_rejected_not_masked():
    with pytest.raises(AIInvalidResponseError):
        service(Provider({"surprise": True})).analyze_pc(context(pc()))


# ---- optional upgrade-candidate lookup must not take the analysis down -------------------------

class FlakyCatalog(LocalCatalog):
    """Resolves the build normally; the OPTIONAL upgrade lookup fails like a slow/unavailable catalog."""
    def __init__(self, rows, error=None, resolve_error=None):
        super().__init__(rows)
        self.error, self.resolve_error, self.upgrade_calls = error, resolve_error, 0

    def human_candidates(self, category, name):
        if self.resolve_error:
            raise self.resolve_error
        return super().human_candidates(category, name)

    def upgrade_candidates(self, category, limit=24):
        self.upgrade_calls += 1
        raise self.error


def post_route(catalog, provider):
    from fastapi.testclient import TestClient
    import ai_routes
    from main import app
    original = ai_routes.get_ai_service
    ai_routes.get_ai_service = lambda: service(provider)
    app.dependency_overrides[ai_routes.get_ai_catalog] = lambda: catalog
    try:
        return TestClient(app).post("/ai/analyze-pc", json={"components": pc(), "usage": ["gaming"], "resolution": "1080p"})
    finally:
        ai_routes.get_ai_service = original
        app.dependency_overrides.pop(ai_routes.get_ai_catalog, None)


def unavailable():
    from fastapi import HTTPException
    return HTTPException(status_code=503, detail="Catálogo temporariamente indisponível")


@pytest.mark.parametrize("error", [None, "requests"])
def test_optional_upgrade_lookup_failure_still_returns_the_technical_analysis(error, caplog):
    import requests
    catalog = FlakyCatalog(rows(), error=unavailable() if error is None else requests.Timeout("slow"))
    with caplog.at_level("WARNING", logger="pc2you.ai"):
        response = post_route(catalog, Provider())
    assert response.status_code == 200, response.text
    body = response.json()
    assert catalog.upgrade_calls == 1  # A failing catalog costs one attempt, not one per category.
    assert body["recommended_candidates"] == []
    assert body["compatibility"]["checked_rules"] and body["upgrade_assessment"]["status"]
    assert body["analysis"]["summary"] and body["readiness"]["status"] == "sufficient"
    assert "upgrade candidate lookup failed" in caplog.text and "category" in caplog.text


def test_critical_resolution_failure_is_still_503():
    response = post_route(FlakyCatalog(rows(), error=unavailable(), resolve_error=unavailable()), Provider())
    assert response.status_code == 503


def test_gemini_outage_with_failing_upgrade_lookup_still_falls_back():
    catalog = FlakyCatalog(rows(), error=unavailable())
    response = post_route(catalog, Provider(error=AIError("timeout", "x", 504)))
    assert response.status_code == 200
    assert response.json()["metadata"]["analysis_source"] == "deterministic_fallback"
