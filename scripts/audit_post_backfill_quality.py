"""Read-only post-backfill diagnosis. Never imports a database repository or startup."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'services'))
from product_matching import CatalogMatcher
from product_matching.matcher import features
from product_matching.normalization import normalize_text, capacity_values, normalize_store
from product_matching.promotions import enrich_promotion
from product_matching.quality import date_value, money, offer_url, equivalence_key
from telegram_collector.parser import extract_prices, _domain_store
from catalog_audit import audit_components

ASSESSMENTS = ('confirmed_match', 'probable_match', 'suspected_false_positive', 'unverifiable')


def source_fingerprints():
    result = {}
    for directory in ('api-catalogo', 'api-orcamentos', 'api-usuarios', 'services'):
        for path in (ROOT / directory).rglob('*.py'):
            if any(p.startswith('.') or p in {'tests', '__pycache__'} for p in path.relative_to(ROOT).parts):
                continue
            result[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def inspect_deployed_seed():
    code = ("import ast,json; from pathlib import Path; "
            "t=ast.parse(Path('/app/seed.py').read_text()); "
            "m=ast.parse(Path('/app/main.py').read_text()); "
            "pairs=[(n.args[0].value,n.args[1].value) for n in ast.walk(t) "
            "if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='component' "
            "and n.args and isinstance(n.args[0],ast.Constant) and n.args[0].value "
            "in ['ryzen-5-7600','ryzen-7-7800x3d','ryzen-9-7950x']]; "
            "calls=any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='seed_components' "
            "for f in m.body if isinstance(f,ast.FunctionDef) and f.name=='startup' for n in ast.walk(f)); "
            "print(json.dumps({'seed_id_name_pairs':pairs,'startup_invokes_seed':calls}))")
    try:
        result = subprocess.run(['docker', 'exec', 'orcapc_api_catalogo', 'python', '-c', code],
                                capture_output=True, text=True, timeout=15, check=True)
        return {'container': 'orcapc_api_catalogo', **json.loads(result.stdout),
                'method': 'read/AST only; no container imports, application startup or database calls',
                'causal_limit': 'Old deployed seed and startup reseeding explain the observed pattern; no pre-start snapshot or write-event log proves when it was overwritten.'}
    except (subprocess.SubprocessError, OSError, ValueError):
        return {'available': False, 'details': 'Container source inspection unavailable; no raw error logged.'}


def internal_id(row):
    value = str(row.get('_id', ''))
    return value if re.fullmatch(r'[0-9a-f]{24}', value) else 'audit-' + hashlib.sha256(value.encode()).hexdigest()[:20]


def identity_tokens(text):
    """Independent literal checks; no fuzzy scores and no raw text in the report."""
    plain = normalize_text(text)
    gpu = {''.join(m).replace(' ', '') for m in re.findall(
        r'\b(rtx|gtx|rx)\s*(\d{4})\s*(ti\s*super|super|ti|xtx|xt|gre)?\b', plain)}
    cpu = {''.join(m) for m in re.findall(r'\b(?:ryzen\s*([3579])\s*(\d{4}[a-z0-9]*)|(?:core\s*)?(i[3579])\s*(\d{4,5}[a-z]*))\b', plain)}
    boards = set(re.findall(r'\b[abhxz]\d{3}[a-z]*\b', plain))
    storage = set(re.findall(r'\b(?:wds[a-z0-9]+|sn\d+[a-z]*|nv[23]|nm\d+|sdss[a-z0-9]+)\b', plain))
    return {'gpu': gpu, 'cpu': cpu, 'motherboard': boards, 'storage': storage}


def scope_of(component):
    scope = component.get('identity_scope')
    if scope:
        return scope
    if component.get('category') == 'gpu' and normalize_text(component.get('brand')) in {'amd', 'nvidia', 'intel'}:
        return 'gpu-model-and-vram-class'
    return 'catalog-model'


def review_identity(row, component, recalculated):
    product = row.get('product') or {}
    text = product.get('name') or row.get('raw_text') or ''
    plain = normalize_text(text)
    tokens = identity_tokens(text)
    category = component.get('category') if component else product.get('component_type')
    category = 'ram' if category == 'kit-ram' else category
    models = tokens.get(category, set())
    evidence, conflicts, missing = [], [], []
    if not component:
        conflicts.append('referenced_component_missing')
    else:
        target_models = identity_tokens(component.get('name', '')).get(category, set())
        if models and target_models:
            if models != target_models:
                conflicts.append('literal_model_or_suffix_mismatch')
            else:
                evidence.append('literal_model_and_suffix_equal')
        elif category in {'gpu', 'cpu', 'motherboard', 'storage'}:
            missing.append('explicit_comparable_model')
        if product.get('component_type') and product['component_type'].replace('kit-ram', 'ram') != category:
            conflicts.append('declared_category_mismatch')
        if re.search(r'\b(?:notebook|laptop|smartphone|celular|computador|pc gamer)\b', plain):
            conflicts.append('complete_device_instead_of_component')
        if sum(bool(tokens[k]) for k in ('gpu', 'cpu', 'motherboard')) > 1 or re.search(r'\b(?:kit upgrade|combo|bundle)\b', plain):
            conflicts.append('multiple_product_families_in_advert')
        specs = {**(component.get('compatibility') or {}), **(component.get('technical_specs') or {})}
        if product.get('match_level') == 'medium' and category == 'cpu' and 'brand' not in (product.get('matched_by') or []):
            missing.append('explicit_manufacturer_signal_required_by_current_matcher')
        if category in {'gpu', 'storage', 'ram'}:
            caps = capacity_values(text)
            target = capacity_values(component.get('name')) | set().union(*(capacity_values(specs.get(k)) for k in ('memory', 'capacity', 'memory_size')))
            if caps and target and caps != target:
                conflicts.append('literal_capacity_mismatch')
            elif caps and target:
                evidence.append('capacity_explicit_and_equal')
            else:
                missing.append('capacity_or_vram')
        if category == 'ram':
            def modules(value):
                return set(re.findall(r'\b(\d+)\s*x\s*(\d+)gb\b', normalize_text(value)))
            a, b = modules(text), modules(component.get('name', '') + ' ' + str(specs.get('modules', '')))
            if a and b and a != b:
                conflicts.append('single_module_vs_kit')
            if 'rgb rs' in plain and 'lpx' in normalize_text(component.get('name')):
                conflicts.append('ram_commercial_family_mismatch')
        if category == 'motherboard':
            ddr = set(re.findall(r'\bddr[345]\b', plain))
            expected_ddr = normalize_text(specs.get('memory_type'))
            if ddr and expected_ddr and ddr != {expected_ddr}:
                conflicts.append('literal_ddr_mismatch')
            elif ddr:
                evidence.append('ddr_explicit_and_equal')
            else:
                missing.append('explicit_ddr')
            socket = normalize_text(specs.get('socket')).replace(' ', '')
            actual_socket = {s.replace(' ', '') for s in re.findall(r'\b(?:am[345]|lga\s*\d{3,4})\b', plain)}
            if actual_socket and socket not in actual_socket:
                conflicts.append('literal_socket_mismatch')
            elif actual_socket:
                evidence.append('socket_explicit_and_equal')
            else:
                missing.append('explicit_socket')
            if re.search(r'\b(?:matx|microatx)\b', plain):
                evidence.append('micro_atx_explicit')
            else:
                missing.append('explicit_form_factor')
            evidence.append('association_is_class_only_not_commercial_sku')
    if recalculated['component_id'] != product.get('component_id'):
        missing.append('persisted_identity_not_reproduced_by_current_catalog')
    if conflicts:
        assessment = 'suspected_false_positive'
        reason = 'Evidência literal incompatível com o componente atual; não corrigido.'
    elif not models and category not in {'ram'}:
        assessment = 'unverifiable'
        reason = 'Não há modelo comparável suficiente para sustentar a identidade.'
    elif missing:
        assessment = 'probable_match'
        reason = 'Modelo plausível, mas faltam evidências explícitas ou há ambiguidade no catálogo atual.'
    else:
        assessment = 'confirmed_match'
        reason = 'Identidade literal sustentada no escopo declarado; não confirma SKU parceiro, anúncio autêntico ou compra.'
    return {'promotion_id': internal_id(row), 'component_id': product.get('component_id'),
            'catalog_name': component.get('name') if component else None,
            'scope': scope_of(component) if component else None,
            'advertised_models': sorted(models), 'current_score': product.get('match_confidence'),
            'stored_level': product.get('match_level'), 'assessment': assessment,
            'evidence': evidence, 'conflicts': conflicts, 'missing_evidence': missing,
            'justification': reason, 'is_demo': bool(row.get('is_demo')),
            'review_method': 'literal evidence checklist plus assisted review; never score alone'}


def price_review(row, identity, recalculated, matcher, now):
    offer = row.get('offer') or {}
    text = (row.get('product') or {}).get('name') or row.get('raw_text') or ''
    captured = date_value((row.get('telegram') or {}).get('sent_at') or row.get('created_at'))
    advertised, _ = extract_prices(text)
    numeric = money(offer.get('price'))
    currency = offer.get('currency')
    text_brl = bool(re.search(r'R\$', text, re.I))
    parsed_currency = 'BRL' if currency == 'BRL' or not currency and text_brl else None
    url = offer_url(offer.get('url'))
    merchant = _domain_store(url) if url else None
    store_key = normalize_store(offer.get('store'))
    recognized_store = store_key if store_key in {'kabum', 'pichau', 'terabyte', 'amazon', 'mercado_livre'} else None
    mismatch = bool(merchant and recognized_store and normalize_store(merchant) != recognized_store)
    historical = enrich_promotion(row, matcher, captured + timedelta(milliseconds=1)) if captured else None
    issues = []
    if numeric is None:
        issues.append('invalid_price')
    if parsed_currency is None:
        issues.append('currency_not_proven')
    if numeric is None or money(advertised) != numeric:
        issues.append('raw_advert_price_not_unambiguously_reproduced')
    if identity['assessment'] != 'confirmed_match':
        issues.append('product_identity_not_confirmed')
    if 'class' in str(identity.get('scope')):
        issues.append('class_price_not_exact_commercial_sku')
    if not url:
        issues.append('offer_url_missing_or_invalid')
    if not recognized_store:
        issues.append('store_missing_or_unrecognized')
    if not merchant:
        issues.append('url_destination_not_proven_offline')
    if mismatch:
        issues.append('store_url_mismatch')
    if not recalculated['offer']['verified']:
        issues.append('implementation_not_verified_at_audit_time')
    return {'promotion_id': internal_id(row), 'component_id': identity['component_id'],
            'price': numeric, 'price_type': type(offer.get('price')).__name__,
            'currency_field': currency if currency in {'BRL', 'USD', 'EUR'} else None,
            'currency_evidence': 'structured' if currency == 'BRL' else 'inferred_from_R$_text' if text_brl else 'unproven',
            'raw_advert_price_equal': numeric is not None and money(advertised) == numeric,
            'offer_url_usable_syntax': bool(url), 'url_source': offer.get('url_source') if offer.get('url_source') in {'button', 'entity', 'text'} else 'unknown',
            'url_present_in_collected_links': bool(url and url in (row.get('links') or [])),
            'store_key': recognized_store, 'url_merchant': normalize_store(merchant), 'store_url_mismatch': mismatch,
            'captured_at': captured.isoformat() if captured else None,
            'expires_at_by_code': (captured + timedelta(days=3)).isoformat() if captured else None,
            'implementation_rules_pass_now': recalculated['offer']['verified'],
            'implementation_rules_pass_if_evaluated_at_capture': historical['offer']['verified'] if historical else None,
            'historical_evaluation_caveat': 'Hypothetical capture-time check using current catalog; actual backfill evaluation timestamp is not stored.',
            'advertised_price_evidence': 'passed' if not issues else 'inconclusive',
            'archived_advert_evidence_ignoring_expiry': 'passed' if not [i for i in issues if i != 'implementation_not_verified_at_audit_time'] else 'inconclusive',
            'transactional_price_confirmation': 'inconclusive_no_store_validation',
            'issues': issues}


def low_review(row, recalculated, matcher):
    p = row.get('product') or {}
    text = p.get('name') or row.get('raw_text') or ''
    plain = normalize_text(text)
    tokens = identity_tokens(text)
    f = features({'title': text, 'category': p.get('component_type'), 'brand': p.get('brand')})
    conflicts = recalculated['product']['conflicts']
    explicit = tokens.get(f['category'], set())
    catalog_models = set().union(*(identity_tokens(c.get('name', '')).get(f['category'], set())
                                  for c in matcher.rows if c.get('category') == f['category']))
    absent = sorted(explicit - catalog_models)
    if re.search(r'\b(?:notebook|laptop|smartphone|celular|monitor|headset|mouse|teclado|televisor|tv|impressora|cadeira|tablet|mini pc|computador|pc gamer)\b', plain):
        reason = 'out_of_scope_or_complete_device'
    elif f['multiple'] or len(set().union(*(tokens[k] for k in ('gpu', 'cpu', 'motherboard')))) > 1:
        reason = 'multiple_products_or_bundle'
    elif absent:
        reason = 'explicit_model_missing_from_catalog'
    elif 'variant_ambiguous' in conflicts:
        reason = 'ambiguous_catalog_variants'
    elif conflicts:
        reason = 'closest_candidate_conflict_not_proof_of_advert_error'
    else:
        reason = 'insufficient_identity_or_score_evidence'
    return {'promotion_id': internal_id(row), 'primary_reason': reason,
            'product_category': f['category'] if f['category'] in {'gpu', 'cpu', 'motherboard', 'ram', 'storage', 'psu', 'case', 'cooler'} else None,
            'advertised_models': sorted(explicit), 'absent_models': absent,
            'closest_candidate_diagnostics': conflicts,
            'diagnostic_caveat': 'Matcher low conflicts describe the selected closest candidate, not necessarily the true product.'}


def audit_snapshot(promotions, catalog, history=(), now=None):
    now = now or datetime.now(timezone.utc)
    matcher = CatalogMatcher(catalog)
    by_id = {r['id']: r for r in catalog}
    high, medium, low, prices, divergences, offer_differences, key_differences = [], [], [], [], [], [], []
    originals, recomputed, integrity, offer_integrity = Counter(), Counter(), Counter(), Counter()
    ids = Counter(c.get('id') for c in catalog)
    mismatched_observations = []
    for row in promotions:
        p, o = row.get('product') or {}, row.get('offer') or {}
        n = enrich_promotion(row, matcher, now)
        np = n['product']
        originals[p.get('match_level', 'unassessed')] += 1
        recomputed[np['match_level']] += 1
        cid = p.get('component_id')
        integrity['with_component_id'] += bool(cid)
        integrity['dangling_component_ids'] += bool(cid and cid not in by_id)
        integrity['low_with_component_id'] += bool(cid and p.get('match_level') == 'low')
        integrity['high_medium_without_id'] += bool(not cid and p.get('match_level') in {'high', 'medium'})
        offer_integrity['positive_money'] += money(o.get('price')) is not None
        offer_integrity['structured_currency_present'] += bool(o.get('currency'))
        offer_integrity['usable_offer_url'] += bool(offer_url(o.get('url')))
        offer_integrity['store_present'] += bool(o.get('store'))
        offer_integrity['url_valid_flag_disagrees_with_syntax'] += o.get('url_valid') != bool(offer_url(o.get('url')))
        offer_integrity['offer_product_score_disagreement'] += o.get('product_match_confidence') != p.get('match_confidence')
        offer_integrity['offer_product_level_disagreement'] += o.get('product_match_level') != p.get('match_level')
        offer_integrity['equivalence_key_mismatch'] += row.get('equivalence_key') != equivalence_key(cid, o)
        matched_fields = ['component_id', 'match_level', 'match_confidence', 'normalized_key', 'matched_by', 'conflicts', 'matcher_version']
        changed = [k for k in matched_fields if p.get(k) != np.get(k)]
        if changed:
            divergences.append({'promotion_id': internal_id(row), 'fields': changed,
                                'stored_component_id': cid, 'recalculated_component_id': np.get('component_id'),
                                'stored_level': p.get('match_level'), 'recalculated_level': np['match_level'],
                                'recalculated_conflicts': np.get('conflicts')})
        changed_offer = [k for k in ('source', 'verified', 'product_match_confidence', 'product_match_level',
                                      'captured_at', 'url_valid', 'url_source', 'store_key', 'matcher_version')
                         if o.get(k) != n['offer'].get(k)]
        if changed_offer:
            offer_differences.append({'promotion_id': internal_id(row), 'fields': changed_offer,
                                      'stored_verified': o.get('verified'), 'recalculated_verified': n['offer'].get('verified')})
        if row.get('equivalence_key') != n.get('equivalence_key'):
            key_differences.append(internal_id(row))
        review = review_identity(row, by_id.get(cid), {'component_id': np.get('component_id')})
        if p.get('match_level') == 'high':
            high.append(review)
        elif p.get('match_level') == 'medium':
            medium.append(review)
        else:
            low.append(low_review(row, n, matcher))
        if o.get('verified') is True:
            prices.append(price_review(row, review, n, matcher, now))
        if row.get('price_observation') != n.get('price_observation'):
            mismatched_observations.append(internal_id(row))
    refs = {}
    for filename in ('seed_identity_reference.json', 'catalog_enrichment_sources.json'):
        refs.update(json.loads((ROOT / 'api-catalogo' / filename).read_text(encoding='utf-8')))
    catalog_audit = audit_components(catalog, refs)
    counts = Counter(r['assessment'] for r in high)
    promotion_by_telegram = {(r.get('telegram', {}).get('chat_id'), r.get('telegram', {}).get('message_id')): r for r in promotions}
    history_checks = Counter()
    for item in history:
        parent = promotion_by_telegram.get((item.get('telegram', {}).get('chat_id'), item.get('telegram', {}).get('message_id')))
        history_checks['without_parent_promotion'] += parent is None
        if parent:
            history_checks['component_disagrees_with_parent'] += item.get('component_id') != (parent.get('product') or {}).get('component_id')
            history_checks['price_disagrees_with_parent'] += money(item.get('price')) != money((parent.get('offer') or {}).get('price'))
            history_checks['equivalence_key_disagrees_with_parent'] += item.get('equivalence_key') != parent.get('equivalence_key')
    critical_models = ['rtx5060', 'rtx5060ti', 'rtx5070', 'rtx5070ti', 'rx9060xt', 'rx9070xt',
                       '55600', '55600g', '55600x', '75700x', '75700x3d', '75800x3d', '79700x', '79800x3d',
                       'b450m', 'b550m', 'b650m', 'b760m', 'b840m', 'b850m']
    variant_counts = {model: Counter() for model in critical_models}
    for row in promotions:
        p = row.get('product') or {}
        tokens = set().union(*identity_tokens(p.get('name') or row.get('raw_text') or '').values())
        for model in tokens.intersection(variant_counts):
            variant_counts[model][p.get('match_level', 'unassessed')] += 1
    return {'mode': 'strictly_read_only', 'audited_at': now.isoformat(), 'total_audited': len(promotions),
            'catalog_components': len(catalog), 'original_distribution': dict(originals), 'recalculated_distribution': dict(recomputed),
            'id_integrity': {**dict(integrity), 'duplicate_catalog_ids': [cid for cid, count in ids.items() if count > 1]},
            'offer_integrity_all_promotions': dict(offer_integrity),
            'critical_variant_coverage': {k: dict(v) for k, v in variant_counts.items()},
            'high_review': {'counts': {k: counts[k] for k in ASSESSMENTS}, 'cases': high},
            'medium_review': {'total': len(medium), 'counts': dict(Counter(r['assessment'] for r in medium)), 'cases': medium},
            'low_review': {'total': len(low), 'primary_reasons': dict(Counter(r['primary_reason'] for r in low)),
                           'nonexclusive_closest_conflicts': dict(Counter(c for r in low for c in r['closest_candidate_diagnostics'])),
                           'missing_models_in_single_component_candidates': dict(Counter(m for r in low if r['primary_reason'] == 'explicit_model_missing_from_catalog' for m in r['absent_models'])), 'cases': low},
            'verified_price_audit': {'total': len(prices),
                'positive_numeric_prices': sum(r['price'] is not None for r in prices),
                'raw_advert_price_equal': sum(r['raw_advert_price_equal'] for r in prices),
                'currency_structured': sum(r['currency_field'] is not None for r in prices),
                'currency_inferred_from_text': sum(r['currency_evidence'] == 'inferred_from_R$_text' for r in prices),
                'implementation_pass_now': sum(r['implementation_rules_pass_now'] for r in prices),
                'implementation_pass_at_capture_hypothetically': sum(r['implementation_rules_pass_if_evaluated_at_capture'] is True for r in prices),
                'advertised_evidence_counts': dict(Counter(r['advertised_price_evidence'] for r in prices)),
                'archived_advert_evidence_counts_ignoring_expiry': dict(Counter(r['archived_advert_evidence_ignoring_expiry'] for r in prices)),
                'issues': dict(Counter(i for r in prices for i in r['issues'])), 'cases': prices},
            'persisted_vs_recalculated': {'identity_differences': divergences,
                'offer_metadata_differences': offer_differences, 'equivalence_key_differences': key_differences,
                'embedded_observation_differences_at_current_time': mismatched_observations},
            'catalog_identity_audit': catalog_audit,
            'history_integrity': {'total': len(history), 'verified': sum(h.get('verified') is True for h in history),
                **dict(history_checks),
                'dangling_components': sum(h.get('component_id') not in by_id for h in history),
                'verified_not_high': sum(h.get('verified') is True and h.get('match_level') != 'high' for h in history)},
            'limitations': ['Confirmation is restricted to the catalog model/class, never authenticity or checkout price.',
                'No redirects, store availability, external specifications, Gemini or Telegram calls were performed.',
                'Capture-time checks use the current catalog; the actual verification evaluation timestamp is absent.',
                'Low nearest-candidate conflicts do not prove that the advertisement itself is wrong.',
                'Currency is not required/stored by the Telegram parser. URL/store are not requirements of price_quality.',
                'AI v2 recomputes high matching and time, but does not check availability/currency/offer.verified in normalized_promotions.'],
            'production_writes_performed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/post-backfill-quality-audit.json')
    parser.add_argument('--inspect-api-container', action='store_true', help='Read deployed seed AST using docker exec; no application imports')
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    from bson.json_util import dumps
    load_dotenv(ROOT / '.env')
    source_hashes = source_fingerprints()
    try:
        with MongoClient(os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017'), tz_aware=True,
                         serverSelectionTimeoutMS=3000, connectTimeoutMS=3000, socketTimeoutMS=5000) as client:
            db = client[os.getenv('MONGO_DB', 'orcapc_catalog')]
            names = ('components', 'telegram_promotions', 'product_price_history', 'notification_history')
            def snapshot():
                return {name: list(db[name].find({}).sort('_id', 1)) for name in names}
            def fingerprints(snap):
                return {name: hashlib.sha256(dumps(rows, sort_keys=True).encode()).hexdigest() for name, rows in snap.items()}
            before = snapshot()
            report = audit_snapshot(before['telegram_promotions'], before['components'], before['product_price_history'])
            sys.path.insert(0, str(ROOT / 'api-orcamentos'))
            from promotion_source import PromotionSource
            from ai_upgrade_context import normalized_promotions
            audit_time = date_value(report['audited_at'])
            recent_promos, available = PromotionSource(collection=db.telegram_promotions).recent(audit_time)
            ai_catalog = [c for c in before['components'] if c.get('category') in {'gpu', 'cpu', 'ram', 'kit-ram', 'psu'}]
            normalized = normalized_promotions(recent_promos, ai_catalog, audit_time)
            report['ai_v2_actual_read_model_at_audit'] = {'source_read_succeeded': available, 'source_recent_rows': len(recent_promos),
                'normalized_eligible_offers': sum(map(len, normalized.values())), 'external_model_calls': 0}
            report['collection_fingerprints_before'] = fingerprints(before)
            report['collection_fingerprints_after'] = fingerprints(snapshot())
            report['collections_unchanged_during_audit'] = report['collection_fingerprints_before'] == report['collection_fingerprints_after']
    except PyMongoError:
        print('MongoDB unavailable; no writes were attempted.', file=sys.stderr)
        return 1
    report['production_source_fingerprints_before'] = source_hashes
    report['production_source_fingerprints_after'] = source_fingerprints()
    report['production_sources_unchanged_during_audit'] = source_hashes == report['production_source_fingerprints_after']
    if args.inspect_api_container:
        report['deployed_seed_evidence'] = inspect_deployed_seed()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'total': report['total_audited'], 'high': report['high_review']['counts'],
                      'verified_prices': {k: v for k, v in report['verified_price_audit'].items() if k != 'cases'},
                      'unchanged': report['collections_unchanged_during_audit']}, ensure_ascii=True))
    return 0 if report['collections_unchanged_during_audit'] and report['production_sources_unchanged_during_audit'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
