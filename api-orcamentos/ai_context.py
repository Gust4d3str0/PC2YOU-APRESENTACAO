"""Deterministic catalog enrichment and compatibility, before any AI call."""

import math
import re
from copy import deepcopy

import compatibility
from ai.schemas import AnalyzePCRequest, technical_text


# Only these technical fields cross the provider boundary. No descriptions, URLs or accounts.
SPEC_FIELDS = {
    "socket", "memory_type", "memory_slots", "max_memory_gb", "capacity", "modules",
    "wattage", "tdp_watts", "power_consumption_watts", "length_mm", "interface",
    "cores", "threads", "frequency", "speed", "memory", "vram", "type",
}
COMPAT_FIELDS = {"socket", "memory_type", "form_factor", "min_psu_watts",
                 "supported_form_factors", "max_gpu_length_mm"}
LABELS = {"cpu": "Processador", "gpu": "Placa de vídeo", "motherboard": "Placa-mãe",
          "ram": "Memória RAM", "storage": "Armazenamento", "psu": "Fonte", "case": "Gabinete"}
RULES = [
    ("cpu_socket", [("cpu", "compatibility", "socket"), ("motherboard", "compatibility", "socket")]),
    ("ram_type", [("motherboard", "compatibility", "memory_type"), ("ram", "compatibility", "memory_type")]),
    ("ram_slots", [("motherboard", "technical_specs", "memory_slots")]),
    ("ram_capacity", [("motherboard", "technical_specs", "max_memory_gb"), ("ram", "technical_specs", "capacity")]),
    ("gpu_power", [("gpu", "compatibility", "min_psu_watts"), ("psu", "technical_specs", "wattage")]),
    ("board_case", [("motherboard", "compatibility", "form_factor"), ("case", "compatibility", "supported_form_factors")]),
    ("gpu_case", [("gpu", "technical_specs", "length_mm"), ("case", "compatibility", "max_gpu_length_mm")]),
]


def _safe_value(value):
    if isinstance(value, str):
        return technical_text(value[:120])
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    if isinstance(value, list) and len(value) <= 16:
        return [_safe_value(item) for item in value]
    raise ValueError("Unsupported catalog value")


def _fields(item, section, allowed):
    result = {}
    for key, value in (item.get(section) or {}).items():
        if key in allowed and value is not None:
            try:
                result[key] = _safe_value(value)
            except ValueError:
                pass
    return result


def normalize(value):
    return re.sub(r"[^\w]", "", value.casefold())


def canonical_name(value):
    value = re.sub(r"^(?:AMD|Intel|NVIDIA|GeForce|Placa[- ]mãe|Placa de vídeo)\s+", "", value, flags=re.I)
    return normalize(value)


def enrich(name, category, catalog):
    # Search is category-scoped and exact after punctuation/spacing normalization.
    # Ambiguous / partial names remain user input rather than guesses.
    query = name
    memory = re.search(r"\s+(\d+)\s*GB\s*$", name, re.I) if category == "gpu" else None
    if memory:
        query = name[:memory.start()].strip()
    found = catalog.search_components(category, query)
    if category == "ram":
        found += catalog.search_components("kit-ram", query)
    found = list({str(item.get("id")): item for item in found}.values())
    matches = [item for item in found
               if item.get("category") in ({"ram", "kit-ram"} if category == "ram" else {category})
               and (canonical_name(query) == canonical_name(str(item.get("name", "")))
                    or normalize(name) == normalize(str(item.get("id", ""))))
               and (not memory or re.match(rf"\s*{memory.group(1)}\s*GB\b", str(item.get("technical_specs", {}).get("memory", "")), re.I))]
    if len(matches) != 1:
        return {"name": name, "category": category, "source": "user", "catalog_id": None,
                "specifications": {}, "compatibility": {}}
    item = matches[0]
    return {"name": technical_text(str(item["name"])[:120]), "category": category,
            "source": "catalog", "catalog_id": technical_text(str(item["id"])[:120]),
            "specifications": _fields(item, "technical_specs", SPEC_FIELDS),
            "compatibility": _fields(item, "compatibility", COMPAT_FIELDS),
            "_catalog_category": item["category"]}


def as_catalog(item):
    return {"id": item["catalog_id"], "category": item.get("_catalog_category", item["category"]),
            "technical_specs": item["specifications"], "compatibility": item["compatibility"]}


def check_compatibility(components):
    known = {item["category"]: as_catalog(item) for item in components if item["source"] == "catalog"}
    issues, checked, unchecked = [], [], []
    for name, fields in RULES:
        available = all(known.get(cat, {}).get(section, {}).get(key) not in (None, "", [], 0)
                        for cat, section, key in fields)
        if name == "ram_slots":
            available = available and "ram" in known
        if not available:
            unchecked.append(name)
            continue
        # Call the existing engine per rule. Exclude unavailable properties so its defaults
        # cannot turn a missing spec into a false incompatibility or a false pass.
        selected = {}
        for cat, section, key in fields:
            selected.setdefault(cat, {"id": known[cat]["id"], "category": known[cat]["category"],
                                      "technical_specs": {}, "compatibility": {}})[section][key] = known[cat][section][key]
        if name == "ram_slots":
            selected["ram"] = {"id": known["ram"]["id"], "category": known["ram"]["category"],
                               "technical_specs": {k: v for k, v in known["ram"]["technical_specs"].items() if k == "modules"},
                               "compatibility": {}}
        try:
            result = compatibility.check_components(list(selected.values()))
        except (TypeError, ValueError):
            unchecked.append(name)
            continue
        checked.append(name)
        issues.extend(result["errors"])
    warnings = []
    if unchecked:
        warnings.append("Compatibilidade parcial: faltam dados do catálogo para uma ou mais regras.")
    if "psu" not in known or not known["psu"]["technical_specs"].get("wattage"):
        warnings.append("Fonte desconhecida ou sem potência verificada. Confirme modelo e potência antes de upgrades.")
    ram = known.get("ram")
    if ram:
        capacity = compatibility._capacity_gb(ram)
        if capacity and capacity < 8:
            warnings.append("O catálogo informa menos de 8 GB de RAM; a memória pode limitar multitarefa.")
    return {"valid": False if issues else (None if unchecked else True),
            "status": "incompatible" if issues else ("partial" if unchecked else "compatible"),
            "issues": list(dict.fromkeys(issues)), "warnings": warnings,
            "checked_rules": checked, "unchecked_rules": unchecked}


def price_of(item):
    values, conditional = [], []
    for offer in item.get("prices", []):
        target = conditional if offer.get("conditional") or offer.get("coupon") else values
        try:
            price = float(offer.get("price"))
            if math.isfinite(price) and price > 0:
                target.append(price)
        except (TypeError, ValueError):
            continue
    values = values or conditional  # unconditional first; a conditional price only when nothing else exists
    return round(min(values), 2) if values else None


def build_context(payload: AnalyzePCRequest, catalog):
    components, missing = [], []
    for category, value in payload.components.model_dump().items():
        for name in (value if isinstance(value, list) else [value]):
            if name:
                item = enrich(name, category, catalog)
                components.append(item)
                if item["source"] == "user":
                    missing.append(f"{LABELS[category]}: especificações não verificadas no catálogo")
        if not value and category != "case":
            missing.append(f"{LABELS[category]}: não informado")
    verdict = check_compatibility(components)
    candidates = []
    # Only supply specific replacements when all existing rule checks are possible.
    # This deliberately favors type-level advice for incomplete builds.
    if verdict["valid"] is True:
        current_ids = {item["catalog_id"] for item in components}
        for category in ("gpu", "ram", "cpu", "storage", "psu"):
            options = catalog.list_components(category)
            if category == "ram":
                options += catalog.list_components("kit-ram")
            for raw in options:
                allowed_categories = {"ram", "kit-ram"} if category == "ram" else {category}
                if raw.get("id") in current_ids or raw.get("category") not in allowed_categories:
                    continue
                price = price_of(raw)
                if payload.upgrade_budget is not None and price is not None and price > payload.upgrade_budget:
                    continue
                try:
                    candidate = {"name": technical_text(str(raw["name"])[:120]), "category": category,
                                 "source": "catalog", "catalog_id": technical_text(str(raw["id"])[:120]),
                                 "_catalog_category": raw["category"],
                                 "specifications": _fields(raw, "technical_specs", SPEC_FIELDS),
                                 "compatibility": _fields(raw, "compatibility", COMPAT_FIELDS)}
                    replaced = [deepcopy(item) for item in components if item["category"] != category] + [candidate]
                    if check_compatibility(replaced)["valid"] is not True:
                        continue
                except (ValueError, KeyError):
                    continue
                candidates.append({"component_id": candidate["catalog_id"], "name": candidate["name"],
                                   "component_type": category, "price": price})
                if sum(c["component_type"] == category for c in candidates) >= 3:
                    break
    public_components = [{key: value for key, value in item.items() if not key.startswith("_")} for item in components]
    return {
        "trusted_context": {"build": public_components, "compatibility": verdict,
                            "missing_information": missing, "upgrade_candidates": candidates,
                            "benchmarks": [], "currency": "BRL"},
        "user_context": {"usage": payload.usage, "games": payload.games,
                         "display": {"resolution": {"1080p": "1920x1080", "1440p": "2560x1440", "4K": "3840x2160"}[payload.resolution],
                                     "refresh_rate": payload.refresh_rate, "monitor": payload.monitor},
                         "upgrade_budget": payload.upgrade_budget},
    }
