CATEGORY_WEIGHTS = {
    "gpu": 0.50,
    "cpu": 0.30,
    "ram": 0.10,
    "storage": 0.05,
    "motherboard": 0.05,
}

BENCHMARK_WEIGHTS = {
    "gaming_score": 0.50,
    "workstation_score": 0.30,
    "ai_score": 0.20,
}

CATEGORY_LABELS = {
    "gpu": "GPU",
    "cpu": "CPU",
    "ram": "RAM",
    "storage": "armazenamento",
    "motherboard": "placa-mãe",
}


def classify_score(score: int) -> dict:
    if score >= 95:
        return {
            "tier": "Entusiasta extremo",
            "gaming": "Excelente para 4K Ultra, Ray Tracing e altas taxas de quadros",
            "workstation": "Excelente para renderização, edição pesada, IA e multitarefa avançada",
            "ai": "Excelente para IA local, aceleração por GPU e workloads computacionais pesados",
            "summary": "Build topo de linha para jogos, criação de conteúdo e cargas profissionais.",
            "recommendation": "Indicada para usuários exigentes, criadores de conteúdo e workloads pesados.",
        }

    if score >= 88:
        return {
            "tier": "Alto desempenho",
            "gaming": "Excelente para 1440p/4K com qualidade alta",
            "workstation": "Muito forte para edição, programação pesada e produtividade",
            "ai": "Muito forte para aceleração por GPU, estudos de IA e tarefas criativas",
            "summary": "Build de alto desempenho, equilibrada para jogos e trabalho.",
            "recommendation": "Indicada para jogos modernos, edição e multitarefa intensa.",
        }

    if score >= 78:
        return {
            "tier": "Performance avançada",
            "gaming": "Muito bom para 1080p/1440p",
            "workstation": "Bom para edição, multitarefa e desenvolvimento",
            "ai": "Boa para aceleração moderada e fluxos de IA leves a intermediários",
            "summary": "Build forte para uso geral avançado.",
            "recommendation": "Indicada para jogos, estudos, programação e produtividade.",
        }

    if score >= 65:
        return {
            "tier": "Intermediário",
            "gaming": "Bom para 1080p com ajustes de qualidade",
            "workstation": "Adequado para produtividade e estudos",
            "ai": "Adequado para tarefas leves e experimentos pontuais",
            "summary": "Build intermediária para uso diário e jogos moderados.",
            "recommendation": "Indicada para uso geral com bom custo-benefício.",
        }

    return {
        "tier": "Básico",
        "gaming": "Indicado para uso diário, estudos e jogos leves",
        "workstation": "Básico para tarefas simples",
        "ai": "Limitado para IA local e cargas aceleradas",
        "summary": "Build de entrada.",
        "recommendation": "Indicada para navegação, estudos e tarefas leves.",
    }


def _benchmark_score(component: dict) -> float:
    benchmark = component.get("benchmark", {})
    weighted_total = 0.0
    used_weight = 0.0

    for key, weight in BENCHMARK_WEIGHTS.items():
        value = benchmark.get(key)
        if isinstance(value, (int, float)):
            weighted_total += value * weight
            used_weight += weight

    if used_weight == 0:
        return 0

    return weighted_total / used_weight


def _category_scores(components: list[dict]) -> dict[str, float]:
    grouped_scores: dict[str, list[float]] = {}

    for component in components:
        category = component.get("category")
        if category == "kit-ram":
            category = "ram"
        if category not in CATEGORY_WEIGHTS:
            continue
        grouped_scores.setdefault(category, []).append(_benchmark_score(component))

    return {
        category: round(sum(scores) / len(scores), 1)
        for category, scores in grouped_scores.items()
        if scores
    }


def _performance_highlights(components: list[dict], scores: dict[str, float]) -> list[str]:
    by_category = {}
    for component in components:
        cat = component.get("category")
        by_category["ram" if cat == "kit-ram" else cat] = component

    highlights = []

    for category in ("gpu", "cpu", "ram", "storage", "motherboard"):
        component = by_category.get(category)
        score = scores.get(category)
        if component and score is not None:
            label = CATEGORY_LABELS.get(category, category)
            highlights.append(f"{label}: {component.get('name')} contribui com {score:.0f}/100 na nota técnica.")

    ignored = [c.get("category") for c in components if c.get("category") not in CATEGORY_WEIGHTS and c.get("category") != "kit-ram"]
    if ignored:
        highlights.append("Fonte, gabinete e cooler foram avaliados na compatibilidade, sem reduzir a nota de desempenho.")

    return highlights[:6]


def estimate_performance(components: list[dict]) -> dict:
    if not components:
        return {
            "gaming": "Não calculado",
            "workstation": "Não calculado",
            "ai": "Não calculado",
            "estimated_score": 0,
            "tier": "Não calculado",
            "summary": "Nenhuma peça foi selecionada para estimar desempenho.",
            "recommendation": "Selecione uma build completa para receber uma análise técnica.",
            "highlights": [],
        }

    scores = _category_scores(components)
    weighted_total = 0.0
    used_weight = 0.0

    for category, score in scores.items():
        weight = CATEGORY_WEIGHTS[category]
        weighted_total += score * weight
        used_weight += weight

    estimated_score = round(weighted_total / used_weight) if used_weight else 0
    classification = classify_score(estimated_score)

    return {
        "estimated_score": estimated_score,
        **classification,
        "highlights": _performance_highlights(components, scores),
        "category_scores": scores,
    }
