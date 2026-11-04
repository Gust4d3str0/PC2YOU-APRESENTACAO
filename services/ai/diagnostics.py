"""Safe validation telemetry: no input values, prompts, credentials or thoughts."""

import json
import logging

from .contract import resolve_schema


logger = logging.getLogger("pc2you.ai")


def json_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def schema_location(loc, schema):
    node, path = schema, []
    for part in loc:
        node = resolve_schema(node, schema)
        if isinstance(part, int):
            path.append(str(part))
            node = node.get("items", {})
        elif part in node.get("properties", {}):
            path.append(part)
            node = node["properties"][part]
        else:
            path.append("<extra>")
            node = {}
    node = resolve_schema(node, schema)
    expected = node.get("type") or "|".join(p.get("type", "unknown") for p in node.get("anyOf", [])) or "defined field"
    if "enum" in node:
        expected += " enum"
    return ".".join(path) or "$", expected


def pydantic_issues(error, schema):
    result = []
    for item in error.errors(include_input=True, include_context=False, include_url=False):
        path, expected = schema_location(item["loc"], schema)
        result.append({"field": path, "expected": expected,
                       "received": "missing" if item["type"] == "missing" else json_type(item.get("input")),
                       "category": item["type"]})
    return result


def sanitized_response(value, schema):
    # Preserve structure, not prose/IDs/numbers. Even adversarial unknown keys are hidden.
    def visit(item, node, depth=0):
        if depth > 8:
            return "<depth limit>"
        node = resolve_schema(node, schema)
        if isinstance(item, dict):
            result = {}
            for key, val in list(item.items())[:20]:
                known = key in node.get("properties", {})
                result[key if known else "<extra>"] = visit(val, node["properties"].get(key, {}) if known else {}, depth + 1)
            return result
        if isinstance(item, list):
            return [visit(val, node.get("items", {}), depth + 1) for val in item[:3]]
        return f"<{json_type(item)} redacted>"
    return visit(value, schema)


def log_failure(settings, provider, stage, issues, raw=None, schema=None):
    logger.warning("[AI] Structured response validation failed provider=%s model=%s stage=%s issues=%s",
                   provider if provider in {"gemini", "mock", "demo-mock"} else "custom",
                   settings.model, stage, json.dumps(issues, ensure_ascii=True))
    if settings.debug_validation and raw is not None and schema is not None:
        logger.warning("[AI] Sanitized response=%s", json.dumps(sanitized_response(raw, schema), ensure_ascii=True))
