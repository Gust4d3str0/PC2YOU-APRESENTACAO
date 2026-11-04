"""Enrich components with official Mercado Livre PRODUCT data (images, specs) — never prices, coupons or Telegram data.

    python scripts/enrich_mercado_livre_products.py                    # dry-run (default): reads, calls the Product API, writes nothing
    python scripts/enrich_mercado_livre_products.py --dry-run --no-fetch   # statistics only, no ML call at all
    python scripts/enrich_mercado_livre_products.py --apply            # persist enrichment (each PRODUCT_ID fetched once, 24h cache)
    python scripts/enrich_mercado_livre_products.py --suggest          # report-only: candidate PRODUCT_IDs per component, for human review

PRODUCT_IDs come from (1) Telegram promotions whose stored/resolved URL contains `/p/MLB…` and whose component the PC2YOU matcher
linked with High confidence, and (2) `api-catalogo/ml_product_map.json`, a manually verified list. The PC2YOU matcher must accept
each (product, component) pair without conflicts. ITEM_IDs (`wid=`) are only counted and probed; the price API is currently
restricted for third-party listings (403) and that is reported as a capability, not as an offer problem.

Credentials are read from the environment / `.env` and are never printed or written to the report. Rotating refresh requires
MERCADO_LIVRE_CLIENT_ID/SECRET and MERCADO_LIVRE_TOKEN_FILE; without them the access token in `.env` is used until it expires.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / 'api-catalogo', ROOT / 'services'):
    sys.path.insert(0, str(path))


def load_env(path):
    """Put MERCADO_LIVRE_*/ML_*/PC2YOU_* from a .env file into os.environ (existing variables win). Values are never printed."""
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        key, sep, value = line.partition('=')
        key = key.strip()
        if sep and key.startswith(('MERCADO_LIVRE_', 'ML_', 'PC2YOU_')) and key not in os.environ:
            os.environ[key] = value.strip().strip('"\'')


if __name__ == '__main__':      # importing this module (tests) must not touch the real environment
    load_env(ROOT / '.env')

from pymongo import MongoClient  # noqa: E402

import ml_products  # noqa: E402
from product_matching.ml_ids import ml_ids_from_offer  # noqa: E402
from product_matching.promotions import enrich_promotion  # noqa: E402

ML_FILTER = {'$or': [{'offer.url': {'$regex': 'mercadoli|meli\\.la'}}, {'offer.resolved_url': {'$regex': 'mercadoli|meli\\.la'}}]}
FALLBACK_IMAGE_MARKERS = ('default-', 'placehold.co')


def has_real_image(component):
    for value in [component.get('real_image'), *(component.get('images') or []), component.get('image')]:
        if isinstance(value, str) and value and not any(m in value for m in FALLBACK_IMAGE_MARKERS):
            return True
    return False


def collect(database, map_file, now=None):
    """(candidates, stats). candidates: {product_id: {'components': Counter, 'bases': set}}."""
    components = list(database.components.find({}, {'_id': 0}))
    by_id = {c['id']: c for c in components}
    candidates = defaultdict(lambda: {'components': Counter(), 'bases': set()})
    products, promo_products, items, promotions, high = set(), set(), set(), 0, 0
    for document in database.telegram_promotions.find(ML_FILTER):
        promotions += 1
        product_id, item_id = ml_ids_from_offer(document.get('offer'))
        if item_id:
            items.add(item_id)
        if not product_id:
            continue
        products.add(product_id)
        promo_products.add(product_id)
        enriched = enrich_promotion(document, components, now)
        component_id = enriched['product'].get('component_id')
        if enriched['product'].get('match_level') == 'high' and component_id in by_id:
            high += 1
            candidates[product_id]['components'][component_id] += 1
            candidates[product_id]['bases'].add('promotion_high_match')
    mapped = 0
    if map_file.is_file():
        for component_id, product_ids in (json.loads(map_file.read_text(encoding='utf-8')).get('components') or {}).items():
            for product_id in product_ids:
                if component_id in by_id and ml_products.PRODUCT_ID_RE.match(product_id):
                    mapped += 1
                    products.add(product_id)
                    candidates[product_id]['components'][component_id] += 1
                    candidates[product_id]['bases'].add('manual_mapping')
    stats = {'ml_promotions_found': promotions, 'product_ids_found_in_promotions': len(promo_products),
             'unique_product_ids': len(products), 'item_ids_found': len(items), 'unique_item_ids': len(items),
             'promotions_with_product_id_and_high_component': high, 'manual_mapping_pairs': mapped}
    return candidates, by_id, sorted(items), stats


def run(database, map_file, apply=False, fetch=True, force=False, probe_limit=20):
    candidates, by_id, items, stats = collect(database, map_file)
    api = ml_products.api
    report = {'mode': 'apply' if apply else 'dry-run', 'stats': stats, 'pairs': []}
    service = ml_products.MercadoLivreProductEnrichment(database, api) if apply else None
    api_outcomes, images_possible, with_real, would_fallback = Counter(), 0, 0, 0
    seen_components = set()
    for product_id, info in sorted(candidates.items()):
        component_id = info['components'].most_common(1)[0][0]
        component = by_id[component_id]
        basis = 'manual_mapping' if 'manual_mapping' in info['bases'] else 'promotion_high_match'
        entry = {'product_id': product_id, 'component_id': component_id, 'basis': basis}
        if apply:
            result = service.enrich(product_id, component, basis=basis, force=force)
            entry.update(outcome=result['outcome'], applied=result['applied'], images=result.get('images'), specs=result.get('specs'),
                         match=(result.get('match') or {}).get('status'))
            api_outcomes[result['outcome']] += 1
        elif fetch:
            fetched = api.get_product(product_id)
            api_outcomes['ok' if fetched.ok else fetched.kind] += 1
            normalized = ml_products.MercadoLivreProductNormalizer.normalize(fetched.data) if fetched.ok else None
            entry.update(outcome='ok' if fetched.ok else fetched.kind)
            if normalized:
                match = ml_products.evaluate_match(normalized, component, basis)
                entry.update(name=normalized['name'], images=len(normalized['images']), specs=len(normalized['specs']), match=match['status'],
                             conflicts=match['conflicts'])
        if entry.get('match') == 'matched' and entry.get('images'):
            if component_id not in seen_components:
                seen_components.add(component_id)
                images_possible += 1
                with_real += has_real_image(component)
                would_fallback += not has_real_image(component)
        report['pairs'].append(entry)
    forbidden = available = other = 0
    probes = []
    capability = ml_products.MercadoLivrePriceCapability(api, database if apply else None)
    if fetch or apply:
        for item_id in items[:probe_limit]:
            probe = capability.probe(item_id)
            probes.append({'item_id': item_id, 'status': probe['status']})
            forbidden += probe['status'] == 'forbidden'
            available += probe['status'] == 'available'
            other += probe['status'] not in {'forbidden', 'available'}
    report['stats'].update({
        'products_api_outcomes': dict(api_outcomes), 'components_that_can_receive_official_image': images_possible,
        'of_those_already_with_real_image': with_real, 'of_those_currently_on_fallback': would_fallback,
        'item_ids_probed': len(probes), 'item_api_forbidden': forbidden, 'item_api_available': available, 'item_api_other': other,
        'could_validate_price_in_future': available})
    if apply:
        ml_products.record_state(database, {'ml_products_detected': len(candidates)})
    return report


# Search filters per category (domains confirmed against the API); other categories are searched unfiltered.
SEARCH_DOMAINS = {'cpu': 'MLB-COMPUTER_PROCESSORS', 'gpu': 'MLB-GRAPHICS_CARDS', 'motherboard': 'MLB-COMPUTER_MOTHERBOARDS',
                  'storage': 'MLB-HARD_DRIVES_AND_SSDS', 'ram': 'MLB-RAM_MEMORY_MODULES', 'kit-ram': 'MLB-RAM_MEMORY_MODULES'}


def suggest(database, limit, only=None, candidates=6):
    """Report-only candidate PRODUCT_IDs from the official search; a human decides what goes into ml_product_map.json."""
    components = [c for c in database.components.find({}, {'_id': 0}) if not (c.get('external_enrichment') or {}).get('mercado_livre')
                  and (not only or c['id'] in only)]
    out = []
    for component in components[:limit]:
        query = {'site_id': 'MLB', 'status': 'active', 'q': component['name'], 'limit': 10}
        if component.get('category') in SEARCH_DOMAINS:
            query['domain_id'] = SEARCH_DOMAINS[component['category']]
        found = ml_products.api.get('/products/search', query)
        row = {'component_id': component['id'], 'name': component['name'], 'candidates': []}
        for hit in ((found.data or {}).get('results') or [])[:candidates] if found.ok else []:
            fetched = ml_products.api.get_product(hit.get('id'))
            normalized = ml_products.MercadoLivreProductNormalizer.normalize(fetched.data) if fetched.ok else None
            if normalized:
                match = ml_products.evaluate_match(normalized, component, 'suggestion')
                row['candidates'].append({'product_id': normalized['product_id'], 'name': normalized['name'], 'match': match['status'],
                                          'conflicts': match['conflicts'], 'images': len(normalized['images']),
                                          'model': normalized.get('model'), 'brand': normalized.get('brand')})
        out.append(row)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mongo-uri', default='mongodb://localhost:27017')
    parser.add_argument('--db', default='orcapc_catalog')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='report only (default)')
    mode.add_argument('--apply', action='store_true', help='persist enrichment')
    mode.add_argument('--suggest', action='store_true', help='report-only candidate discovery')
    parser.add_argument('--no-fetch', action='store_true', help='dry-run without calling Mercado Livre')
    parser.add_argument('--force', action='store_true', help='ignore the 24h cache / replace an earlier product')
    parser.add_argument('--map-file', type=Path, default=ROOT / 'api-catalogo/ml_product_map.json')
    parser.add_argument('--suggest-limit', type=int, default=10)
    parser.add_argument('--candidates', type=int, default=6, help='products fetched per component for --suggest')
    parser.add_argument('--only', default='', help='comma-separated component ids for --suggest')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/ml-product-enrichment.json')
    args = parser.parse_args()
    database = MongoClient(args.mongo_uri)[args.db]
    if args.suggest:
        report = {'mode': 'suggest', 'suggestions': suggest(database, args.suggest_limit, {i for i in args.only.split(',') if i}, args.candidates)}
    else:
        report = run(database, args.map_file, apply=args.apply, fetch=not args.no_fetch, force=args.force)
    report['generated_at'] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report.get('stats') or report, ensure_ascii=False, indent=2))
    print(f'Relatório: {args.output}')


if __name__ == '__main__':
    main()
