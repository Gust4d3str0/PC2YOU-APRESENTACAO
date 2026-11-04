"""AI v2 read model: deterministic candidates, prices, promotion/catalog association."""

import re
from copy import deepcopy
from datetime import datetime, timezone

from product_matching.offers import condition_labels
from product_matching.promotions import promotion_match, enrich_promotion
from product_matching import CatalogMatcher
from product_matching.quality import (money, date_value, recent, offer_url as safe_url, catalog_offers, best_known_price, equivalence_key)

from ai.schemas import AnalyzePCRequest, technical_text
from ai_context import (COMPAT_FIELDS, SPEC_FIELDS, _fields, check_compatibility,
                        build_context)


MANDATORY = {"gpu": {"gpu_power"}, "cpu": {"cpu_socket"}, "ram": {"ram_type", "ram_slots"}, "psu": {"gpu_power"}}
AFFECTED = {"gpu": {"gpu_power", "gpu_case"}, "cpu": {"cpu_socket"},
            "ram": {"ram_type", "ram_slots", "ram_capacity"}, "psu": {"gpu_power"}}


def promotion_component(promotion, catalog):
    match = promotion_match(promotion, catalog)
    if not match.matched or match.confidence_level != 'high' or match.conflicts:
        return None
    return next((c for c in catalog if str(c['id']) == match.component_id), None)


def normalized_promotions(promotions, catalog, now):
    catalog = CatalogMatcher(catalog)
    result, seen = {}, set()
    for raw in promotions:
        if not isinstance(raw, dict) or not isinstance(raw.get("offer"), dict) or not isinstance(raw.get("product") or {}, dict):
            continue
        if raw.get("is_demo") or raw.get("status") not in {"parsed", "matched", "verified", "published"}:
            continue
        observed = recent((raw.get("telegram") or {}).get("sent_at") or raw.get("created_at"), now, 3)
        offer = raw.get("offer") or {}
        enriched = enrich_promotion(raw, catalog, now)
        # Only offers that may compete for a price: not invalid/expired/stale, matched at high confidence.
        if not enriched['offer']['verified'] or not enriched['evaluation']['eligible']:
            continue
        conditions = enriched['offer'].get('conditions') or {}
        price = money(offer.get("price"))
        component = promotion_component(raw, catalog)
        pid = str(raw.get("_id", ""))
        if not observed or not price or not component or not re.fullmatch(r"[\w-]{1,120}", pid):
            continue
        url = safe_url(offer.get("url"))
        store = str(offer["store"])[:120] if offer.get("store") else None
        coupon = str(offer["coupon"])[:80] if offer.get("coupon") else None
        identity = equivalence_key(component["id"], {"store": store, "price": price, "coupon": coupon, "url": url})
        if identity in seen:
            continue
        seen.add(identity)
        original = money(offer.get("original_price"))
        result.setdefault(component["id"], []).append({
            "promotion_id": pid, "component_id": component["id"], "title": component["name"],
            "store": store, "price": price, "original_price": original if original and original > price else None,
            "coupon": coupon, "url": url, "observed_at": observed.isoformat(), "source": "telegram",
            # Fixed vocabulary only (never free Telegram text) so the model can disclose the condition.
            "conditions": condition_labels(conditions), "is_conditional": enriched['evaluation']['is_conditional'],
            "status": enriched['evaluation']['status'],
        })
    for values in result.values():
        values.sort(key=lambda item: (item["price"], item["url"] is None, item["promotion_id"]))
    return {key: values[:3] for key, values in result.items()}


def history_stats(component, now):
    days = {}
    for snapshot in (component.get('price_history') or [])[-365:]:
        observations = snapshot.get('observations') or []
        if not isinstance(observations, list):
            continue  # Daily catalog aggregates carry a count, not verified observation rows.
        for item in observations:
            date = recent(item.get('date'), now, 90)
            price = money(item.get('price'))
            if (date and price and item.get('component_id') == component.get('id')
                    and item.get('source') in {'mercado_livre', 'telegram', 'manual'}
                    and item.get('verified') is True and item.get('match_level') == 'high'
                    and isinstance(item.get('match_confidence'), (int, float)) and item['match_confidence'] >= .85):
                key = date.date().isoformat()
                days[key] = min(days.get(key, price), price)
    if len(days) < 3:
        return None
    return {'historical_average': round(sum(days.values()) / len(days), 2),
            'historical_min': min(days.values()), 'samples': len(days), 'source': 'catalog_real'}


def prices(component, promotions, now):
    known, verified = [], []
    qualified = catalog_offers(component, now)
    for item in qualified:
        price = item['price']
        if item.get('source', 'seed') == 'seed':
            continue  # Seed prices are legacy fiction: never a current or reference price.
        if item['quality']['product_match_level'] == 'high':
            if item.get('valid_until') or item.get('coupon_valid_until'):
                from product_matching.quality import offer_state
                if offer_state(item, now=now) != 'active':
                    continue
            known.append({'value': price, 'source': 'catalog_reference', 'verified': False, 'store': item.get('store')})
        if item['quality']['verified']:
            verified.append({'value': price, 'source': 'catalog_real', 'verified': True, 'store': item.get('store')})
    real_catalog = min((p["value"] for p in verified), default=None)
    verified += [{"value": p["price"], "source": "telegram", "verified": True, "store": p["store"],
                  "conditional": bool(p.get("is_conditional")), "conditions": p.get("conditions") or []} for p in promotions]
    options = [{**p, 'price': p['value'], 'quality': {'source': 'telegram' if p['source'] == 'telegram' else 'mercado_livre',
               'verified': p['verified'], 'product_match_level': 'high'}} for p in verified + known]
    # Lowest real price wins; when it is conditional the condition travels with it and is disclosed to the user.
    chosen = best_known_price(options, allow_reference=True)
    best = {k: chosen[k] for k in ('value', 'source', 'verified', 'store')} if chosen else {
        "value": None, "source": "unavailable", "verified": False, "store": None,
    }
    best['conditional'] = bool(chosen and chosen.get('conditional'))
    best['conditions'] = list(chosen.get('conditions') or []) if chosen and chosen.get('conditional') else []
    return best, min((p["value"] for p in known), default=None), real_catalog


def technical_component(raw):
    return {"catalog_id": technical_text(str(raw["id"])), "name": technical_text(str(raw["name"])[:120]),
            "category": "ram" if raw["category"] == "kit-ram" else raw["category"], "source": "catalog",
            "specifications": _fields(raw, "technical_specs", SPEC_FIELDS),
            "compatibility": _fields(raw, "compatibility", COMPAT_FIELDS), "_catalog_category": raw["category"]}


def public_component(item):
    return {k: v for k, v in item.items() if not k.startswith("_")}


def replacement_compatibility(build, replacements):
    replaced = {item["category"] for item in replacements}
    components = [deepcopy(item) for item in build if item["category"] not in replaced] + replacements
    result = check_compatibility(components)
    mandatory = set().union(*(MANDATORY[item["category"]] for item in replacements))
    if result["issues"] or not mandatory.issubset(result["checked_rules"]):
        return None
    relevant = set().union(*(AFFECTED[item["category"]] for item in replacements))
    unchecked = relevant.intersection(result["unchecked_rules"])
    return {**result, "valid": None if unchecked else True,
            "status": "partial" if unchecked else "compatible",
            "warnings": (["Confirme as regras e medidas pendentes antes de comprar."] if unchecked else [])}


def potential_improvement(current, candidate, usage):
    if not current:
        return True
    if candidate["category"] in {"ram", "kit-ram"}:
        def capacity(item):
            value = str(item.get("technical_specs", {}).get("capacity", ""))
            match = re.fullmatch(r"\s*(\d+)\s*GB\s*", value, re.I)
            return int(match[1]) if match else None
        old_capacity, new_capacity = capacity(current), capacity(candidate)
        if old_capacity is not None and new_capacity is not None:
            return new_capacity > old_capacity
    if candidate["category"] == "psu":
        old = current.get("technical_specs", {}).get("wattage")
        new = candidate.get("technical_specs", {}).get("wattage")
        return isinstance(old, (int, float)) and isinstance(new, (int, float)) and new > old
    score = "ai_score" if usage[0] == "ai_ml" else "gaming_score" if usage[0] in {"gaming", "streaming"} else "workstation_score"
    old, new = current.get("benchmark", {}).get(score), candidate.get("benchmark", {}).get(score)
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return new > old
    # No numerical improvement is claimed without evidence. The model may return no choice.
    return True


def build_upgrade_bundle(payload, catalog, source, now=None):
    now = now or datetime.now(timezone.utc)
    v1 = build_context(AnalyzePCRequest.model_validate(payload.model_dump(exclude={"include_promotions"})), catalog)
    build = deepcopy(v1["trusted_context"]["build"])
    warnings = list(v1["trusted_context"]["compatibility"]["warnings"])
    # Small bounded window per category; catalog itself is unchanged.
    rows = []
    for category in ("gpu", "cpu", "ram", "kit-ram", "psu"):
        rows.extend(catalog.list_components(category))
    rows = deepcopy(list({str(item["id"]): item for item in rows}.values()))
    categories = {item["id"]: item["category"] for item in rows}
    for component in build:
        if component["catalog_id"] in categories:
            component["_catalog_category"] = categories[component["catalog_id"]]
    raw_promos, available = source.recent(now) if payload.include_promotions else ([], True)
    history_rows = source.history([row['id'] for row in rows], now) if payload.include_promotions and hasattr(source, 'history') else []
    for raw in rows:
        extra = [h for h in history_rows if h.get('component_id') == raw['id']]
        if extra:
            raw['price_history'] = list(raw.get('price_history') or []) + [{'observations': extra}]
    linked = normalized_promotions(raw_promos, rows, now)
    if not available:
        warnings.append("Promoções temporariamente indisponíveis; foram usados apenas dados do catálogo.")
    current = {item["category"]: item for item in build}
    by_id = {str(item["id"]): item for item in rows}
    details, internal, projection = {}, {}, []
    for raw in rows:
        try:
            item = technical_component(raw)
            category = item["category"]
            old = current.get(category)
            if old and old["catalog_id"] == item["catalog_id"]:
                continue
            if not potential_improvement(by_id.get(old["catalog_id"]) if old else None, raw, payload.usage):
                continue
            checked = replacement_compatibility(build, [item])
            if checked is None:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        offers = linked.get(item["catalog_id"], [])
        if payload.upgrade_budget is not None:
            offers = [o for o in offers if o["price"] <= payload.upgrade_budget]
        best, catalog_price, real_catalog = prices(raw, offers, now)
        if payload.upgrade_budget is not None and best["value"] is not None and best["value"] > payload.upgrade_budget:
            continue
        history = history_stats(raw, now)
        promotion = offers[0] if offers and best["source"] == "telegram" else None
        evidence = "insufficient_data"
        eligible_promotions = []
        for offer in offers:
            evidence_for_offer = ("below_verified_catalog" if real_catalog and offer["price"] < real_catalog else
                                  "below_historical_average" if history and offer["price"] < history["historical_average"] else "insufficient_data")
            if offer is promotion:
                evidence = evidence_for_offer
            if offer["url"] and checked["valid"] is True and evidence_for_offer != "insufficient_data":
                eligible_promotions.append(offer["promotion_id"])
        cid = item["catalog_id"]
        details[cid] = {"candidate_id": cid, "component": public_component(item), "price": best,
                        "catalog_price": catalog_price, "promotion": promotion, "promotions": offers,
                        "history": history, "compatibility": checked, "opportunity_evidence": evidence}
        internal[cid] = item
        projection.append({"component_id": cid, "candidate_id": cid, "name": item["name"], "component_type": category,
                           "current_component_id": old["catalog_id"] if old else None,
                           "specifications": item["specifications"], "compatibility": checked,
                           "price": best["value"] if best["verified"] else None, "price_source": best["source"],
                           "price_is_conditional": best["conditional"], "price_conditions": best["conditions"],
                           "price_history": history,
                           "promotions": [{"promotion_id": o["promotion_id"], "price": o["price"],
                                           "is_conditional": o["is_conditional"], "conditions": o["conditions"],
                                           "buy_now_eligible": o["promotion_id"] in eligible_promotions,
                                           "evidence": "below_verified_catalog" if real_catalog and o["price"] < real_catalog else
                                           "below_historical_average" if history and o["price"] < history["historical_average"] else "insufficient_data"} for o in offers]})
    projection.sort(key=lambda c: (c["component_type"], c["price"] is None, c["price"] or 0, c["candidate_id"]))
    # Bound prompt size without excluding all candidates without promotions or prices.
    projection = [item for kind in MANDATORY for item in [c for c in projection if c["component_type"] == kind][:5]]
    ids = {c["candidate_id"] for c in projection}
    details = {key: value for key, value in details.items() if key in ids}
    if not projection:
        warnings.append("Não há candidatos com dados suficientes para as regras obrigatórias. Informe nomes completos ou IDs do catálogo, especialmente placa-mãe e fonte.")
    context = {"trusted_context": {**v1["trusted_context"], "upgrade_candidates": projection},
               "user_context": {**v1["user_context"], "include_promotions": payload.include_promotions}}
    return {"context": context, "build_internal": build, "details": details, "internal": {k: v for k, v in internal.items() if k in ids},
            "warnings": warnings, "promotions_available": available,
            "matched_promotions": sum(len(d["promotions"]) for d in details.values())}
