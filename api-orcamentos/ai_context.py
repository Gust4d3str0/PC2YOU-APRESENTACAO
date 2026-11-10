"""Deterministic catalog enrichment and compatibility, before any AI call."""

import math
import re
from copy import deepcopy

import compatibility
from ai.schemas import AnalyzePCRequest, technical_text
from product_matching.normalization import named_brands, normalize_brand, normalize_text
from product_matching.matcher import features
from catalog_specs.coverage import RULES
from catalog_specs.normalization import normalize_spec


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
    return re.sub(r"[^a-z0-9]", "", normalize_text(value))


def canonical_name(value, brands):
    words = re.sub(r"[.,]", " ", normalize_text(value)).split()
    # Only remove brands belonging to this catalog identity (including existing
    # aliases such as WD). A different manufacturer remains a mismatch.
    for size in (2, 1):
        index = 0
        while index < len(words):
            if normalize_brand(" ".join(words[index:index + size])) in brands:
                del words[index:index + size]
            else:
                index += 1
    value = " ".join(words)
    value = re.sub(r"\bgeforce\b", " ", value)
    value = re.sub(r"\b(?:placa mae|placa de video|processador|gamer|lacrado|novo|box|oem)\b", " ", value)
    return ' '.join(value.split())


def _identity_match(name, category, item):
    """Explicit identities only; commercial words cannot erase variant tokens."""
    p = features({'title': name, 'category': category})
    c = features(item)
    if p['multiple'] or (p['inferred'] in {'cpu', 'gpu'} and p['inferred'] != category):
        return False
    brands = named_brands(item.get('name')) | {normalize_brand(item.get('brand'))}
    if category == 'cpu' and named_brands(name) - brands:
        return False
    if category == 'cpu':
        if not p['model'] or p['model'] != c['model']:
            return False
        cleaned = canonical_name(name, brands)
        cleaned = re.sub(r'\b(?:ryzen\s*[3579]\s*\d{4}[a-z0-9]*|(?:core\s*)?i[3579]\s*\d{4,5}[a-z]*)\b', '', cleaned)
        return not normalize(cleaned)
    if category == 'motherboard':
        # A chipset alone can identify an explicitly generic family, never a named SKU.
        candidate = normalize_text(item.get('name'))
        generic = bool(re.fullmatch(r'placa mae [abhxz]\d{3}[a-z]* (?:am\d|lga\d+) ddr\d(?: classe)?', candidate))
        candidate_models = set(re.findall(r'\b[abhxz]\d{3}[a-z]*\b', candidate))
        if not generic or not p['model'] or p['model'] != candidate_models or p['brands'] - c['brands']:
            return False
        for key in ('socket', 'memory_type'):
            if p[key] and p[key] != c[key]:
                return False
        cleaned = canonical_name(name, brands)
        cleaned = re.sub(r'\b(?:[abhxz]\d{3}[a-z]*|am[345]|lga\d+|ddr[345]|classe)\b', '', cleaned)
        return not normalize(cleaned)
    if category == 'psu' and normalize_text(item.get('name')).startswith('fonte '):
        if p['brands'] - c['brands'] or not p['power'] or p['power'] != c['power']:
            return False
        query = normalize(canonical_name(name, brands)).removeprefix('fonte')
        candidate = normalize(canonical_name(item['name'], brands)).removeprefix('fonte')
        return query == next(iter(p['power'])) + 'w' or query == candidate
    return False


def _matches_name(name, category, item):
    if normalize(name) == normalize(str(item.get("id", ""))):
        return True
    brands = named_brands(item.get("name")) | {normalize_brand(item.get("brand"))}
    brands.discard("")
    if category == "gpu" and re.search(r"\b(?:GeForce|RTX|GTX)\b", item.get("name", ""), re.I):
        brands.add("nvidia")
    query = canonical_name(name, brands)
    candidate = canonical_name(item.get("name", ""), brands)
    if normalize(query) == normalize(candidate):
        return True
    if any(normalize(query) == normalize(canonical_name(alias, brands))
           for alias in item.get('aliases', [])):
        return True
    if _identity_match(name, category, item):
        return True
    memory = re.search(r"\b(\d+)gb\s*$", query) if category == "gpu" else None
    return bool(memory and normalize(query[:memory.start()]) == normalize(candidate)
                and re.match(rf"\s*{memory.group(1)}\s*GB\b",
                             str((item.get("technical_specs") or {}).get("memory", "")), re.I))


def enrich(name, category, catalog):
    # Keep direct IDs fast. Names also need the category snapshot: the catalog's
    # literal search can miss accents, punctuation, units or a relocated brand.
    query = name
    memory = re.search(r"\s+(\d+)\s*GB\s*$", name, re.I) if category == "gpu" else None
    if memory:
        query = name[:memory.start()].strip()
    found = catalog.search_components(category, query)
    if category == "ram":
        found += catalog.search_components("kit-ram", query)
    if not any(normalize(name) == normalize(str(item.get("id", ""))) for item in found):
        found += catalog.list_components(category)
        if category == "ram":
            found += catalog.list_components("kit-ram")
    found = list({str(item.get("id")): item for item in found}.values())
    matches = [item for item in found
               if item.get("category") in ({"ram", "kit-ram"} if category == "ram" else {category})
               and _matches_name(name, category, item)]
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
        available = all(normalize_spec(key, known.get(cat, {}).get(section, {}).get(key)) is not None
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
                                      "technical_specs": {}, "compatibility": {}})[section][key] = normalize_spec(key, known[cat][section][key])
        if name == "ram_slots":
            selected['ram']['technical_specs']['modules'] = normalize_spec('modules', known['ram']['technical_specs']['modules'])
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
