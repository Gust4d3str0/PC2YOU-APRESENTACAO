"""One Pydantic contract, enriched by the same contextual rules used for validation."""

from .schemas import PCAnalysis


def budget_relevance_values(candidate, budget):
    expected = ("no_budget" if budget is None else "price_unavailable"
                if not candidate or candidate["price"] is None else "within_budget")
    return (expected, "save_budget")


def analysis_schema(context):
    schema = PCAnalysis.model_json_schema()
    candidates = context["trusted_context"]["upgrade_candidates"]
    budget = context["user_context"]["upgrade_budget"]
    props = schema["$defs"]["UpgradePriority"]["properties"]
    ids = list(dict.fromkeys(item["component_id"] for item in candidates))
    props["candidate_id"] = {
        "anyOf": [{"type": "string", "enum": ids}, {"type": "null"}],
    } if ids else {"type": "null"}
    allowed = set(budget_relevance_values(None, budget))
    for candidate in candidates:
        allowed.update(budget_relevance_values(candidate, budget))
    props["budget_relevance"]["enum"] = [v for v in props["budget_relevance"]["enum"] if v in allowed]
    props["budget_relevance"]["description"] = (
        "Use no_budget when upgrade_budget is null. With a budget, within_budget requires "
        "a selected candidate_id with a real catalog price. A type-level priority with "
        "candidate_id=null has no verified price: use price_unavailable or save_budget."
    )
    return schema


def resolve_schema(node, root):
    while "$ref" in node:
        node = root["$defs"][node["$ref"].split("/")[-1]]
    return node


def normalize_enums(value, schema):
    """Only case variations of known enum values; never translations or number coercion."""
    def visit(item, node):
        node = resolve_schema(node, schema)
        if isinstance(item, dict):
            return {key: visit(val, node["properties"][key]) if key not in {"candidate_id", "promotion_id"} and key in node.get("properties", {}) else val
                    for key, val in item.items()}
        if isinstance(item, list):
            return [visit(val, node.get("items", {})) for val in item]
        if isinstance(item, str) and "enum" in node:
            return next((v for v in node["enum"] if isinstance(v, str) and v.casefold() == item.casefold()), item)
        return item
    return visit(value, schema)
