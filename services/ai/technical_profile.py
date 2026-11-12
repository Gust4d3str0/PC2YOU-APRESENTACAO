"""Deterministic technical assessment of the CURRENT build.

The backend collects facts and derives simple, explainable indicators; the model only explains them.
Classes and release eras come from model-number tables (documented below) and are labelled as
approximate. Nothing here is a benchmark, an FPS estimate or a bottleneck percentage.
"""
import re
from datetime import date

from catalog_specs.human_input import cpu_features, gpu_features
from catalog_specs.normalization import capacity, normalize_human_text, normalize_spec

CLASS_LABELS = {1: "entrada", 2: "intermediária", 3: "intermediária forte", 4: "alta", 5: "topo"}
RYZEN_YEAR = {1: 2017, 2: 2018, 3: 2019, 4: 2020, 5: 2020, 6: 2022, 7: 2022, 8: 2024, 9: 2024}
INTEL_YEAR = {6: 2015, 7: 2017, 8: 2017, 9: 2018, 10: 2020, 11: 2021, 12: 2021, 13: 2022, 14: 2023, 15: 2024}
RTX_YEAR = {20: 2018, 30: 2020, 40: 2022, 50: 2025}
GTX_YEAR = {9: 2014, 10: 2016, 16: 2019}
RX_YEAR = {4: 2016, 5: 2019, 6: 2020, 7: 2022, 9: 2025}
SOCKET_YEAR = {"AM4": 2017, "AM5": 2022, "LGA1700": 2021, "LGA1200": 2020, "LGA1151": 2015, "LGA1155": 2011,
               "LGA1150": 2013, "AM3": 2009, "LGA1851": 2024}
MATURE_SOCKETS = {"AM4", "LGA1200", "LGA1151", "LGA1155", "LGA1150", "AM3"}
HEAVY_USAGE = {"editing", "streaming", "3d_rendering", "ai_ml", "programming"}
GRAPHIC_USAGE = {"gaming", "editing", "streaming", "3d_rendering", "ai_ml"}


def _spec(item, key):
    return (item or {}).get("specifications", {}).get(key)


def _compat(item, key):
    return (item or {}).get("compatibility", {}).get(key)


def cpu_profile(item, year):
    threads, cores = _spec(item, "threads"), _spec(item, "cores")
    features = cpu_features(normalize_human_text(item["name"]), bare=False)[0]
    number = features.get("number") or ""
    release = None
    if features.get("family") == "ryzen" and number[:1].isdigit():
        release = RYZEN_YEAR.get(int(number[0]))
    elif features.get("family") == "core" and number:
        release = INTEL_YEAR.get(int(number[:2]) if len(number) == 5 else int(number[0]))
    elif features.get("family") == "ultra":
        release = 2024
    level = None
    if isinstance(threads, int):
        level = 5 if threads >= 24 else 4 if threads >= 16 else 3 if threads >= 12 else 2 if threads >= 8 else 1
        if release and year - release > 6:
            level = max(1, level - 1)
    return {"recognized": True, "name": item["name"], "cores": cores, "threads": threads,
            "socket": _compat(item, "socket"), "tdp_watts": _spec(item, "tdp_watts"),
            "class": CLASS_LABELS.get(level), "level": level, "approx_release_year": release,
            "basis": "threads from catalog, adjusted for platform age"}


def gpu_profile(item, year):
    features = gpu_features(normalize_human_text(item["name"]))[0]
    series, number, suffix = features.get("series"), features.get("number") or "", (features.get("suffix") or "").lower()
    level = release = None
    if number.isdigit():
        n = int(number)
        if series in {"rtx", "gtx"}:
            level = {5: 1, 6: 2, 7: 3, 8: 4, 9: 5}.get((n % 100) // 10)
            release = (RTX_YEAR if series == "rtx" else GTX_YEAR).get(n // 100)
        elif series == "rx":
            level = {5: 1, 6: 2, 7: 3, 8: 4, 9: 5}.get((n % 1000) // 100)
            release = RX_YEAR.get(n // 1000 if n >= 1000 else n // 100)
        if level and suffix in {"ti", "super", "ti super", "xt", "xtx", "gre"} and level in {2, 3}:
            level += 1
        if level and release and year - release > 6:
            level = max(1, level - 1)
    memory = (_spec(item, "memory") or "")
    return {"recognized": True, "name": item["name"], "family": item.get("_family_label") or item["name"],
            "scope": item.get("resolution_scope"), "memory_hint": memory or None, "class": CLASS_LABELS.get(level),
            "level": level, "approx_release_year": release,
            "recommended_psu_watts": _compat(item, "min_psu_watts") or
            ((item.get("family_bounds") or {}).get("compatibility.min_psu_watts") or {}).get("safe_max"),
            "basis": "model-number table (approximate class, not a benchmark)"}


def ram_profile(item):
    total = capacity(_spec(item, "capacity"), gb=True) if _spec(item, "capacity") else None
    speed = normalize_spec("speed", _spec(item, "speed"))
    return {"recognized": True, "total_gb": total, "type": _compat(item, "memory_type") or _spec(item, "memory_type"),
            "speed": speed, "modules": _spec(item, "modules")}


def storage_profile(items):
    drives = []
    for item in items:
        interface = _spec(item, "interface")
        gb = capacity(_spec(item, "capacity"), gb=True) if _spec(item, "capacity") else None
        drives.append({"name": item["name"], "capacity_gb": gb, "interface": interface,
                       "type": _spec(item, "type"), "nvme": bool(interface and "nvme" in str(interface).lower()),
                       "hdd": str(_spec(item, "type") or "").upper() == "HDD"})
    return drives


def _finding(finding_id, kind, component, text):
    return {"id": finding_id, "kind": kind, "component": component, "text": text}


def technical_assessment(build, usage, today_year=None):
    year = today_year or date.today().year
    usage = list(usage)
    by = {}
    for item in build:
        if item.get("source") in {"catalog", "derived"} and (item.get("specifications") or item.get("compatibility")):
            by.setdefault(item["category"], []).append(item)
    cpu = cpu_profile(by["cpu"][0], year) if "cpu" in by else {"recognized": False}
    gpu = gpu_profile(by["gpu"][0], year) if "gpu" in by else {"recognized": False}
    ram = ram_profile(by["ram"][0]) if "ram" in by else {"recognized": False}
    storage = storage_profile(by.get("storage", []))
    board = by.get("motherboard", [None])[0]
    psu = by.get("psu", [None])[0]
    socket = (_compat(board, "socket") or (cpu.get("socket") if cpu["recognized"] else None))
    platform = {"socket": socket, "memory_type": _compat(board, "memory_type") or ram.get("type"),
                "form_factor": _compat(board, "form_factor"), "approx_socket_year": SOCKET_YEAR.get(socket),
                "mature": socket in MATURE_SOCKETS}
    wattage = normalize_spec("wattage", _spec(psu, "wattage")) if psu else None
    needed = gpu.get("recommended_psu_watts") if gpu["recognized"] else None
    headroom_class = None
    if wattage and needed:
        headroom_class = "below_recommended" if wattage < needed else "tight" if wattage - needed < 100 else "comfortable"
    findings, ranking = [], []
    cpu_name = cpu.get("name")
    graphics = bool(set(usage) & GRAPHIC_USAGE)
    heavy = bool(set(usage) & HEAVY_USAGE)

    if cpu["recognized"] and cpu.get("threads") and cpu.get("cores"):
        if cpu["level"] and cpu["level"] >= 3:
            findings.append(_finding("cpu_threads_strong", "strength", "cpu",
                            f"{cpu_name} tem {cpu['cores']} núcleos e {cpu['threads']} threads, o que dá boa folga para multitarefa e para o uso informado."))
        elif cpu["level"] == 1:
            findings.append(_finding("cpu_threads_low", "improvement", "cpu",
                            f"{cpu_name} tem poucos núcleos e threads para cargas mais pesadas; é um ponto de evolução."))
            ranking.append(("cpu", 2, "cpu_low_thread_count"))
    if gpu["recognized"] and gpu.get("level"):
        if gpu["level"] >= 3 and graphics:
            findings.append(_finding("gpu_class_good", "strength", "gpu",
                            f"{gpu['name']} está na classe {gpu['class']} de placas de vídeo, adequada para o tipo de uso e a resolução informados."))
        elif gpu["level"] <= 1 and graphics:
            findings.append(_finding("gpu_class_entry", "improvement", "gpu",
                            f"{gpu['name']} é de classe de entrada; cargas gráficas mais exigentes tendem a pedir uma placa mais forte."))
            ranking.append(("gpu", 3, "gpu_entry_class"))
    imbalance = None
    if cpu.get("level") and gpu.get("level"):
        gap = gpu["level"] - cpu["level"]
        years = None
        if cpu.get("approx_release_year") and gpu.get("approx_release_year"):
            years = gpu["approx_release_year"] - cpu["approx_release_year"]
        if gap >= 2 or (years is not None and years >= 5 and gpu["level"] >= 3):
            imbalance = "cpu_limits_gpu"
            findings.append(_finding("cpu_gpu_imbalance", "alert", "cpu",
                            f"Há um desequilíbrio geracional entre {cpu_name} e {gpu['name']}: o processador tende a ser a principal limitação do conjunto."))
            ranking.append(("cpu", 5, "cpu_behind_gpu"))
        elif -gap >= 2 and graphics:
            imbalance = "gpu_behind_cpu"
            findings.append(_finding("gpu_behind_cpu", "improvement", "gpu",
                            f"{gpu['name']} está uma classe técnica abaixo de {cpu_name}; a placa de vídeo é o primeiro candidato a evolução para cargas gráficas."))
            ranking.append(("gpu", 4, "gpu_behind_cpu"))
        else:
            imbalance = "balanced"
            findings.append(_finding("cpu_gpu_balanced", "strength", "gpu",
                            f"{cpu_name} e {gpu['name']} estão em classes técnicas próximas, formando um conjunto coerente."))
    total = ram.get("total_gb")
    if ram["recognized"] and total:
        if total >= 32:
            findings.append(_finding("ram_ample", "strength", "ram", f"{total}GB de memória {ram.get('type') or ''} é uma quantidade alta para o uso informado.".replace("  ", " ")))
        elif total < 8:
            findings.append(_finding("ram_very_low", "alert", "ram", f"{total}GB de memória é pouco e tende a limitar multitarefa."))
            ranking.append(("ram", 5, "ram_very_low"))
        elif total < 16:
            findings.append(_finding("ram_low", "improvement", "ram", f"{total}GB de memória atende o básico, mas é o primeiro ponto a ampliar para jogos e multitarefa."))
            ranking.append(("ram", 3, "ram_low"))
        elif heavy and total < 32:
            findings.append(_finding("ram_below_heavy_target", "improvement", "ram", f"{total}GB de memória funciona, mas cargas de edição, renderização ou desenvolvimento costumam se beneficiar de mais."))
            ranking.append(("ram", 2, "ram_below_heavy_target"))
        else:
            findings.append(_finding("ram_adequate", "strength", "ram", f"{total}GB de memória é uma quantidade adequada para o uso informado."))
        speed = ram.get("speed")
        mhz = int(re.match(r"\d+", speed)[0]) if speed else None
        if mhz and ((ram.get("type") == "DDR4" and mhz < 2666) or (ram.get("type") == "DDR5" and mhz < 4800)):
            findings.append(_finding("ram_slow", "improvement", "ram", f"A memória informada ({speed}) é lenta para a plataforma {ram.get('type')}."))
    for drive in storage[:1]:
        if drive["nvme"]:
            findings.append(_finding("storage_nvme", "strength", "storage", f"O armazenamento NVMe ({drive['name']}) favorece carregamentos rápidos e boa responsividade."))
        elif drive["hdd"]:
            findings.append(_finding("storage_hdd", "improvement", "storage", "O armazenamento principal é um disco mecânico; um SSD melhora muito a responsividade e os carregamentos."))
            ranking.append(("storage", 3, "storage_hdd"))
        if drive["capacity_gb"] and drive["capacity_gb"] < 480:
            findings.append(_finding("storage_small", "improvement", "storage", "A capacidade de armazenamento é pequena para jogos e projetos atuais."))
            ranking.append(("storage", 2, "storage_small"))
    if headroom_class == "comfortable":
        findings.append(_finding("psu_comfortable", "strength", "psu", f"A fonte de {wattage}W tem folga sobre o mínimo recomendado para a placa de vídeo informada."))
    elif headroom_class == "tight":
        findings.append(_finding("psu_tight", "improvement", "psu", f"A fonte de {wattage}W atende a placa de vídeo atual, mas com pouca folga; uma placa mais forte no futuro pode exigir uma fonte maior."))
        ranking.append(("psu", 1, "psu_tight_for_future_gpu"))
    elif headroom_class == "below_recommended":
        findings.append(_finding("psu_below", "alert", "psu", f"A fonte de {wattage}W está abaixo do mínimo recomendado para a placa de vídeo informada."))
        ranking.append(("psu", 6, "psu_below_recommended"))
    if platform["mature"]:
        findings.append(_finding("platform_mature", "improvement", "motherboard",
                        f"A plataforma ({socket}) é de geração anterior: atende bem hoje, mas uma evolução futura de processador tende a exigir nova placa-mãe e possivelmente nova memória."))
    ranked = sorted({(c, s, r) for c, s, r in ranking}, key=lambda x: -x[1])
    order, seen = [], set()
    for component, _, reason in ranked:
        if component not in seen:
            seen.add(component)
            order.append({"component": component, "reason_code": reason})
    next_logical = None
    if not order:
        levels = {c: p.get("level") for c, p in (("gpu", gpu), ("cpu", cpu)) if p.get("level")}
        if levels:
            lowest = min(levels.values())
            tied = [c for c, v in levels.items() if v == lowest]
            next_logical = "gpu" if "gpu" in tied and graphics else tied[0]
    return {
        "basis": "backend-derived from catalog specifications; approximate classes, not benchmarks",
        "usage": usage, "cpu": cpu, "gpu": gpu, "ram": ram, "storage": storage, "platform": platform,
        "psu": {"recognized": bool(psu), "wattage": wattage, "headroom": headroom_class},
        "balance": {"cpu_gpu": imbalance},
        "findings": findings,
        "upgrade_order": order,
        "no_urgent_upgrade": not order and bool(findings),
        "next_logical_category": next_logical,
    }
