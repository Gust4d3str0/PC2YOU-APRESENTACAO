"""Deterministic sufficiency, upgrade state and provider-free fallback analysis.

Nothing here calls a model. The model never decides whether data is sufficient:
the backend computes it from recognized components and verified rules.
"""
from catalog_specs.normalization import normalize_spec

GRAPHIC_USAGES = {"gaming", "editing", "streaming", "3d_rendering", "ai_ml"}
# Rules that must be verified before a SPECIFIC product may be offered for a category.
CANDIDATE_REQUIRED = {"gpu": {"gpu_power", "gpu_case"}, "cpu": {"cpu_socket"},
                      "ram": {"ram_type", "ram_slots", "ram_capacity"}, "psu": {"gpu_power"}, "storage": set()}
RULE_LABELS = {"cpu_socket": "socket do processador", "ram_type": "tipo de memória",
               "ram_slots": "slots de memória", "ram_capacity": "capacidade máxima de memória",
               "gpu_power": "potência da fonte para a placa de vídeo",
               "board_case": "formato da placa-mãe no gabinete",
               "gpu_case": "espaço físico da placa de vídeo no gabinete"}
RULE_COMPONENT = {"cpu_socket": "motherboard", "ram_type": "ram", "ram_slots": "ram", "ram_capacity": "ram",
                  "gpu_power": "psu", "board_case": "case", "gpu_case": "case"}
CATEGORY_LABELS = {"cpu": "processador", "gpu": "placa de vídeo", "motherboard": "placa-mãe",
                   "ram": "memória", "storage": "armazenamento", "psu": "fonte", "case": "gabinete"}


def recognized(item):
    return bool(item and item.get("source") in {"catalog", "derived"}
                and (item.get("specifications") or item.get("compatibility")))


def blockers(unchecked):
    """Categories whose specific products cannot be offered yet, with the pending rules."""
    pending = set(unchecked)
    return {category: sorted(required & pending)
            for category, required in CANDIDATE_REQUIRED.items() if required & pending}


def readiness(build, compatibility, usage):
    by_category = {item["category"]: item for item in build}
    reasons = []
    if not recognized(by_category.get("cpu")):
        reasons.append("cpu_not_recognized")
    gpu = by_category.get("gpu")
    if gpu and not recognized(gpu) and set(usage) & GRAPHIC_USAGES:
        reasons.append("gpu_not_recognized")
    if not recognized(by_category.get("ram")):
        reasons.append("ram_without_technical_info")
    psu = by_category.get("psu")
    if recognized(gpu) and not (psu and normalize_spec("wattage", (psu.get("specifications") or {}).get("wattage"))):
        reasons.append("psu_wattage_unknown")
    count = sum(recognized(item) for item in build)
    if count < 3:
        reasons.append("too_few_components_recognized")
    if not compatibility["checked_rules"] and not compatibility["issues"]:
        reasons.append("no_rule_verified")
    return {"status": "insufficient" if reasons else "sufficient", "reasons": reasons,
            "recognized_components": count, "checked_rules": len(compatibility["checked_rules"]),
            "note": "Regras físicas pendentes, como espaço no gabinete, não tornam a análise insuficiente."}


def upgrade_assessment(trusted, priorities):
    ready = trusted["analysis_readiness"]
    verdict = trusted["compatibility"]
    pending = trusted.get("upgrade_blockers", {})
    blocked = sorted({p.component_type for p in priorities if p.candidate_id is None and pending.get(p.component_type)})
    if ready["status"] != "sufficient":
        status = "insufficient"
    elif not priorities:
        status = "partial" if verdict["issues"] else "no_priority"
    else:
        status = "partial" if blocked else "priorities_available"
    return {"status": status, "blocked_types": blocked, "pending_rules": list(verdict["unchecked_rules"]),
            "readiness_reasons": ready["reasons"] if status == "insufficient" else []}


def fallback_analysis(trusted, user):
    """Technical diagnosis from verified backend facts. Never presented as a model answer."""
    verdict, ready = trusted["compatibility"], trusted["analysis_readiness"]
    profile = trusted.get("technical_assessment") or {}
    findings = profile.get("findings", [])
    issues, unchecked = verdict["issues"], verdict["unchecked_rules"]
    budget = user["upgrade_budget"]
    relevance = "no_budget" if budget is None else "price_unavailable"
    ordered = list(dict.fromkeys(
        [RULE_COMPONENT[r] for r in verdict.get("failed_rules", []) if r in RULE_COMPONENT]
        + [entry["component"] for entry in profile.get("upgrade_order", [])]))
    reasons = {entry["component"]: entry["reason_code"] for entry in profile.get("upgrade_order", [])}
    texts = {c: next((f["text"] for f in findings if f["component"] == c and f["kind"] in {"improvement", "alert"}), None)
             for c in ordered}
    priorities = [{"priority": index, "component_type": category,
                   "reason": texts.get(category) or f"A verificação técnica apontou um conflito envolvendo {CATEGORY_LABELS[category]}.",
                   "expected_benefit": "Resolver o conflito antes de qualquer outra troca." if category not in reasons
                   else "Evolução técnica coerente com o restante do conjunto.",
                   "budget_relevance": relevance, "candidate_id": None}
                  for index, category in enumerate(ordered[:7], 1)]
    strengths = [f["text"] for f in findings if f["kind"] == "strength"][:8]
    weaknesses = list(issues)[:8] + [f["text"] for f in findings if f["kind"] == "improvement"][:max(0, 8 - len(issues))]
    if not weaknesses and ready["status"] == "sufficient":
        weaknesses = ["Nenhum ponto crítico identificado no cenário informado."]
    warnings = [f["text"] for f in findings if f["kind"] == "alert"][:12]
    if issues:
        rating, balance, summary = "attention", "attention", "As verificações técnicas encontraram conflitos que devem ser resolvidos primeiro."
        final = "Resolva primeiro os conflitos apontados antes de qualquer outra troca."
    elif ready["status"] != "sufficient":
        rating, balance, summary = "insufficient_data", "insufficient_data", "Há poucas informações técnicas reconhecidas para uma análise útil."
        final = "Informe mais detalhes das peças principais para uma análise completa."
    else:
        imbalance = profile.get("balance", {}).get("cpu_gpu")
        rating = "attention" if warnings else "good"
        balance = "attention" if warnings or imbalance in {"cpu_limits_gpu", "gpu_behind_cpu"} else "balanced"
        summary = ("Diagnóstico técnico gerado pelo sistema a partir das especificações reconhecidas no catálogo: "
                   + ("o conjunto apresenta pontos de atenção." if balance == "attention" else "o conjunto parece equilibrado para o uso informado."))
        if priorities:
            final = f"O próximo passo mais lógico é evoluir {CATEGORY_LABELS[priorities[0]['component_type']]}."
        elif profile.get("next_logical_category"):
            final = (f"Nenhum upgrade urgente é necessário. Se quiser ganhar desempenho no futuro, "
                     f"a próxima categoria a considerar é {CATEGORY_LABELS[profile['next_logical_category']]}.")
        else:
            final = "Nenhum upgrade urgente é necessário no cenário informado."
    return {
        "summary": summary, "overall_rating": rating,
        "balance": {"status": balance, "explanation":
                    "Avaliação baseada em especificações técnicas reconhecidas; não mede desempenho em jogos ou programas."},
        "primary_limit": None, "strengths": strengths, "weaknesses": weaknesses,
        "upgrade_priorities": priorities, "warnings": warnings, "missing_information": [],
        "final_recommendation": final,
    }
