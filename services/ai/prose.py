"""Reject invented numerical/model claims while allowing supplied technical references."""

import re

from .errors import ContractViolation
from .schemas import technical_text


_QUANTITY = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:GB|TB|MHz|GHz|W|Hz)\b", re.I)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def validate_prose(value, path, context, selected):
    try:
        technical_text(value)
    except ValueError as exc:
        raise ContractViolation(path, "unsafe_text", "technical prose without secrets or instructions", "string") from exc
    # These claims are forbidden even if a number also occurs elsewhere in the input.
    if re.search(r"R\$|\$|€|%|\b\d+(?:[.,]\d+)?\s*(?:FPS|frames\b|quadros\b|por cento)", value, re.I):
        raise ContractViolation(path, "unsupported_performance_or_price", "qualitative prose without invented prices/FPS", "string")
    cleaned = value
    build = context["trusted_context"]["build"]
    # References to current components (not invented recommendations) are legitimate.
    for item in build + selected:
        name = item["name"]
        aliases = [name, re.sub(r"^(?:AMD|Intel|NVIDIA|GeForce)\s+", "", name, flags=re.I)]
        aliases.extend(re.findall(r"\b[A-Za-z]{1,8}[- ]?\d{1,5}[A-Za-z]{0,3}\b", name))
        for alias in aliases:
            cleaned = re.sub(r"(?<!\w)" + re.escape(alias).replace(r"\ ", r"\s*") + r"(?!\w)", "", cleaned, flags=re.I)
    quantities, memory_types = set(), set()
    for text in _strings(build):
        quantities.update(match.group() for match in _QUANTITY.finditer(text))
        memory_types.update(re.findall(r"\bG?DDR[3-7]X?\b", text, re.I))
    numeric_units = {
        "cores": ("núcleos", "nucleos", "cores"), "threads": ("threads",),
        "wattage": ("W", "watts"), "tdp_watts": ("W", "watts"),
        "power_consumption_watts": ("W", "watts"), "min_psu_watts": ("W", "watts"),
        "memory_slots": ("slots",), "max_memory_gb": ("GB",),
        "length_mm": ("mm",), "max_gpu_length_mm": ("mm",),
    }
    for component in build:
        for section in ("specifications", "compatibility"):
            specs = component[section]
            for key, units in numeric_units.items():
                number = specs.get(key)
                if isinstance(number, (int, float)) and not isinstance(number, bool):
                    for unit in units:
                        cleaned = re.sub(r"(?<!\w)" + re.escape(str(number)) + r"\s*" + unit + r"\b", "", cleaned, flags=re.I)
            for key in ("socket", "memory_type", "interface", "form_factor"):
                item = specs.get(key)
                if isinstance(item, str):
                    cleaned = re.sub(r"(?<!\w)" + re.escape(item) + r"(?!\w)", "", cleaned, flags=re.I)
    rate = context["user_context"]["display"].get("refresh_rate")
    if rate:
        quantities.add(f"{rate} Hz")
    for quantity in quantities:
        pattern = re.escape(re.sub(r"\s+", "", quantity))
        pattern = re.sub(r"(?<=\d)(?=[A-Za-z])", r"\\s*", pattern)
        cleaned = re.sub(r"(?<!\w)" + pattern + r"(?!\w)", "", cleaned, flags=re.I)
    for memory in memory_types:
        cleaned = re.sub(r"\b" + re.escape(memory) + r"\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(?:1080p|1440p|4k|3d)\b", "", cleaned, flags=re.I)
    resolution = context["user_context"]["display"].get("resolution")
    if resolution:
        cleaned = cleaned.replace(resolution, "")
    if re.search(r"\d|\b(?:RTX|GTX|Ryzen|GeForce|Radeon|Xeon|Threadripper)\b|\bCore\s+i", cleaned, re.I):
        raise ContractViolation(path, "unverified_technical_reference", "references supplied in the technical context", "string")
    if re.search(r"\bcompat[ií]ve(?:l|is)\b", cleaned, re.I):
        raise ContractViolation(path, "compatibility_verdict_in_prose", "backend compatibility verdict only", "string")
