import json
import logging
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from google import genai
from google.genai import types

from ai.config import AISettings
from ai.contract import analysis_schema, budget_relevance_values, normalize_enums
from ai.diagnostics import sanitized_response
from ai.errors import AIInvalidResponseError
from ai.provider import GeminiProvider
from ai.schemas import AnalyzePCRequest, PCAnalysis
from ai_context import build_context
from test_ai import setup, post, request, analysis, transport_response


@pytest.mark.parametrize("change,status", [
    ({"primary_limit": {**analysis()["primary_limit"], "confidence": "alta"}}, 502),
    ({"primary_limit": {**analysis()["primary_limit"], "confidence": "HIGH"}}, 200),
    ({"upgrade_priorities": [{**analysis()["upgrade_priorities"][0], "priority": "1"}]}, 502),
    ({"upgrade_priorities": [{**analysis()["upgrade_priorities"][0], "priority": 1}]}, 200),
    ({"primary_limit": None}, 502),
    ({"warnings": None}, 502),
    ({"warnings": []}, 200),
    ({"unknown_field": "extra"}, 502),
    ({"overall_rating": "excelente"}, 502),
    ({"overall_rating": "bom"}, 502),
    ({"overall_rating": "GOOD"}, 200),
    ({"upgrade_priorities": []}, 200),
    ({"primary_limit": {"component": "unknown", "confidence": "low", "explanation": "Faltam evidências para escolher um componente."}}, 200),
])
def test_realistic_model_contract_variations(setup, change, status):
    setup.provider.output.update(change)
    response = post(setup)
    assert response.status_code == status, response.text
    if status == 200:
        data = response.json()["analysis"]
        assert data["primary_limit"]["confidence"] in {"low", "medium", "high"}
        assert data["overall_rating"] in {"good", "attention", "insufficient_data"}


@pytest.mark.parametrize("field", ["strengths", "weaknesses", "upgrade_priorities", "warnings", "missing_information"])
def test_omitted_optional_arrays_default_to_empty_lists(setup, field):
    del setup.provider.output[field]
    response = post(setup)
    assert response.status_code == 200, response.text
    assert response.json()["analysis"][field] == []


def test_actual_failure_regression_no_candidate_cannot_claim_within_budget(setup, caplog):
    # Exact category observed in the real pre-fix response. No fabricated price fallback.
    setup.provider.output["upgrade_priorities"][0]["budget_relevance"] = "within_budget"
    with caplog.at_level(logging.WARNING, logger="pc2you.ai"):
        response = post(setup, request(upgrade_budget=2000))
    assert response.status_code == 502
    assert 'stage=semantic' in caplog.text
    assert 'upgrade_priorities.0.budget_relevance' in caplog.text
    assert 'unsupported_budget_claim' in caplog.text
    assert 'price_unavailable|save_budget' in caplog.text
    assert not setup.service._cache
    sent = setup.provider.calls[0]["schema"]
    assert sent["$defs"]["UpgradePriority"]["properties"]["budget_relevance"]["enum"] == ["price_unavailable", "save_budget"]


@pytest.mark.parametrize("budget,price,expected", [
    (None, None, {"no_budget", "save_budget"}),
    (2000, None, {"price_unavailable", "save_budget"}),
    (2000, 1500, {"within_budget", "price_unavailable", "save_budget"}),
    (None, 1500, {"no_budget", "save_budget"}),
])
def test_contextual_generation_enums_use_same_budget_rule_as_backend(setup, budget, price, expected):
    context = build_context(AnalyzePCRequest.model_validate(request(upgrade_budget=budget)), setup.catalog)
    if price is not None:
        context["trusted_context"]["upgrade_candidates"] = [{"component_id": "gpu-option", "component_type": "gpu", "name": "Catalog option", "price": price}]
    schema = analysis_schema(context)
    actual = set(schema["$defs"]["UpgradePriority"]["properties"]["budget_relevance"]["enum"])
    shared = set(budget_relevance_values(None, budget))
    for candidate in context["trusted_context"]["upgrade_candidates"]:
        shared.update(budget_relevance_values(candidate, budget))
    assert actual == shared == expected


def test_generation_contract_derives_from_pydantic_without_forked_shape(setup):
    context = build_context(AnalyzePCRequest.model_validate(request()), setup.catalog)
    schema = analysis_schema(context)
    base = PCAnalysis.model_json_schema()
    modified = deepcopy(schema)
    modified["$defs"]["UpgradePriority"]["properties"]["candidate_id"] = base["$defs"]["UpgradePriority"]["properties"]["candidate_id"]
    modified["$defs"]["UpgradePriority"]["properties"]["budget_relevance"] = base["$defs"]["UpgradePriority"]["properties"]["budget_relevance"]
    assert modified == base
    assert set(schema["properties"]) == set(PCAnalysis.model_fields)


def test_case_normalization_does_not_translate_or_modify_prose_and_ids():
    raw = analysis()
    raw["primary_limit"]["confidence"] = "MEDIUM"
    raw["primary_limit"]["component"] = "GPU"
    raw["summary"] = "Texto em Português do Brasil."
    raw["upgrade_priorities"][0]["candidate_id"] = "MiXeD-Catalog-ID"
    normalized = normalize_enums(raw, PCAnalysis.model_json_schema())
    assert normalized["primary_limit"]["confidence"] == "medium"
    assert normalized["primary_limit"]["component"] == "gpu"
    assert normalized["summary"] == raw["summary"]
    assert normalized["upgrade_priorities"][0]["candidate_id"] == "MiXeD-Catalog-ID"
    assert raw["primary_limit"]["confidence"] == "MEDIUM"
    raw["primary_limit"]["confidence"] = "alta"
    assert normalize_enums(raw, PCAnalysis.model_json_schema())["primary_limit"]["confidence"] == "alta"


def test_pydantic_diagnostic_records_types_and_path_without_values(setup, caplog):
    setup.provider.output["upgrade_priorities"][0]["priority"] = "1"
    with caplog.at_level(logging.WARNING, logger="pc2you.ai"):
        assert post(setup).status_code == 502
    assert 'stage=pydantic' in caplog.text
    assert 'upgrade_priorities.0.priority' in caplog.text
    assert '"expected": "integer"' in caplog.text
    assert '"received": "string"' in caplog.text
    assert 'int_type' in caplog.text
    assert 'Sanitized response=' not in caplog.text


def test_optional_debug_redacts_all_prose_extra_keys_secrets_and_numbers(setup, caplog):
    setup.service.settings = replace(setup.service.settings, debug_validation=True)
    raw = setup.provider.output
    raw["summary"] = "PRIVATE_NAME private@example.com SECRET_API_KEY SECRET_JWT"
    raw["PRIVATE_KEY_CONTAINING_TOKEN"] = {"thought": "CHAIN_OF_THOUGHT_SECRET"}
    with caplog.at_level(logging.WARNING, logger="pc2you.ai"):
        assert post(setup).status_code == 502
    assert 'Sanitized response=' in caplog.text
    assert '<extra>' in caplog.text and '<string redacted>' in caplog.text
    for sensitive in ("PRIVATE_NAME", "private@example.com", "SECRET_API_KEY", "SECRET_JWT", "PRIVATE_KEY_CONTAINING_TOKEN", "CHAIN_OF_THOUGHT_SECRET", setup.service.settings.api_key):
        assert sensitive not in caplog.text


def test_debug_is_off_by_default_and_environment_can_enable_it(monkeypatch):
    monkeypatch.delenv("AI_DEBUG_VALIDATION", raising=False)
    assert AISettings.from_env().debug_validation is False
    monkeypatch.setenv("AI_DEBUG_VALIDATION", "true")
    assert AISettings.from_env().debug_validation is True


def test_sdk_client_configuration_uses_env_model_timeout_and_one_attempt(monkeypatch):
    import ai.provider as provider_module
    client = Mock()
    client.models.generate_content.return_value = transport_response()
    factory = Mock(return_value=client)
    monkeypatch.setattr(provider_module.genai, "Client", factory)
    settings = AISettings(enabled=True, api_key="secret", model="configured-model", timeout=12)
    provider = GeminiProvider(settings)
    for _ in range(2):
        provider.generate(system="instructions", context={}, schema={"type": "object"})
    factory.assert_called_once()
    options = factory.call_args.kwargs["http_options"]
    assert options.timeout == 12000 and options.retry_options.attempts == 1
    assert factory.call_args.kwargs["vertexai"] is False
    assert client.models.generate_content.call_args.kwargs["model"] == "configured-model"


def test_official_sdk_serializes_exact_schema_without_network(setup):
    context = build_context(AnalyzePCRequest.model_validate(request(upgrade_budget=2000)), setup.catalog)
    schema = analysis_schema(context)
    output = analysis()
    output["upgrade_priorities"][0]["budget_relevance"] = "price_unavailable"
    seen = []

    def handler(http_request):
        body = json.loads(http_request.content)
        seen.append(body)
        assert body["generationConfig"]["responseJsonSchema"] == schema
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [{"text": json.dumps(output)}]}}]})

    client = genai.Client(api_key="test-only", vertexai=False, http_options=types.HttpOptions(
        client_args={"transport": httpx.MockTransport(handler)}, retry_options=types.HttpRetryOptions(attempts=1)))
    setup.service.provider = GeminiProvider(setup.service.settings, client)
    response = post(setup, request(upgrade_budget=2000))
    assert response.status_code == 200, response.text
    assert len(seen) == 1


def test_thought_parts_never_enter_analysis_or_logs(caplog):
    client = Mock()
    response = transport_response()
    response.candidates[0].content.parts.insert(0, SimpleNamespace(text="CHAIN_OF_THOUGHT_SECRET", thought=True))
    client.models.generate_content.return_value = response
    provider = GeminiProvider(AISettings(enabled=True, api_key="test-only"), client)
    assert provider.generate(system="s", context={}, schema={}) == analysis()
    assert 'CHAIN_OF_THOUGHT_SECRET' not in caplog.text


def test_invalid_response_has_structured_safe_diagnostics_and_no_retry():
    client = Mock()
    client.models.generate_content.return_value = transport_response({"candidates": []})
    with pytest.raises(AIInvalidResponseError) as exc:
        GeminiProvider(AISettings(enabled=True, api_key="test-only"), client).generate(system="s", context={}, schema={})
    assert exc.value.issues[0]["category"] == "empty_candidates"
    client.models.generate_content.assert_called_once()


def test_sanitized_snapshot_is_bounded_and_does_not_retain_scalar_values():
    raw = {"warnings": ["private@example.com"] * 100, "summary": "SECRET", "primary_limit": {"confidence": "HIGH"}}
    safe = sanitized_response(raw, PCAnalysis.model_json_schema())
    assert len(safe["warnings"]) == 3
    assert 'SECRET' not in json.dumps(safe) and 'private@example.com' not in json.dumps(safe)


@pytest.mark.parametrize("text,accepted", [
    ("Seu cenário é 1080p a 144 Hz.", True),
    ("Seu cenário é 1080p a 240 Hz.", False),
    ("Sua memória informada é de 16GB.", True),
    ("Sua memória informada é de 64GB.", False),
    ("Seu processador é AMD Ryzen 5 5600.", True),
    ("Seu processador é Ryzen 5 5600.", True),
    ("Compre Ryzen 9 9999X.", False),
    ("Você terá 144 FPS.", False),
    ("Você terá um ganho de 144%.", False),
    ("Isso custa R$ 144.", False),
])
def test_prose_allows_only_grounded_technical_references(setup, text, accepted):
    setup.provider.output["summary"] = text
    body = request()
    body["components"].update(cpu="AMD Ryzen 5 5600", ram="16GB DDR4")
    response = post(setup, body)
    assert response.status_code == (200 if accepted else 502), response.text


@pytest.mark.parametrize("text,accepted", [
    ("Seu processador possui 6 núcleos e 12 threads.", True),
    ("Seu processador possui 8 núcleos e 24 threads.", False),
    ("Seu processador usa o socket AM5.", True),
    ("Seu processador usa o socket AM4.", False),
    ("Seu processador terá 12 FPS.", False),
])
def test_catalog_numeric_specs_are_allowed_only_with_corresponding_units(setup, text, accepted):
    setup.catalog.items[0]["technical_specs"].update(cores=6, threads=12)
    setup.provider.output["summary"] = text
    assert post(setup).status_code == (200 if accepted else 502)


@pytest.mark.parametrize("board,accepted", [("B550M", True), ("B650M", False)])
def test_partial_board_model_reference_must_exist_in_supplied_name(setup, board, accepted):
    motherboard = next(c for c in setup.catalog.items if c["category"] == "motherboard")
    motherboard["name"] = "Placa-mãe B550M AM5 DDR5"
    setup.provider.output["summary"] = f"A placa-mãe {board} tem informações no catálogo."
    body = request()
    body["components"]["motherboard"] = motherboard["name"]
    assert post(setup, body).status_code == (200 if accepted else 502)
