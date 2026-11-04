"""Diagnostic only: can the official API read these listings (ITEM_IDs)?

    python scripts/check_mercado_livre_price_capability.py --item-id MLB7833387058
    python scripts/check_mercado_livre_price_capability.py --from-promotions --limit 20

Prints how many were tested and how many are available / forbidden / not_found / error. A 403 is reported as a capability
(`forbidden`), never as a problem with the offer. Promotions, prices and offers are never modified; with --record only the integration status (item_api / price_validation) is stored.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / 'api-catalogo', ROOT / 'services'):
    sys.path.insert(0, str(path))


def load_env(path):
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            key, sep, value = line.partition('=')
            if sep and key.strip().startswith(('MERCADO_LIVRE_', 'ML_')) and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip().strip('"\'')


def check(item_ids, capability):
    results = [capability.probe(item_id) for item_id in item_ids]
    counts = Counter(r['status'] for r in results)
    return {'tested': len(results), 'available': counts['available'], 'forbidden': counts['forbidden'], 'not_found': counts['not_found'],
            'error': counts['error'], 'items': [{'item_id': r['item_id'], 'status': r['status']} for r in results]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--item-id', action='append', default=[])
    parser.add_argument('--from-promotions', action='store_true', help='ITEM_IDs found in stored Telegram promotions')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--record', action='store_true', help='store the capability result (item_api / price_validation) in ml_integration_state')
    parser.add_argument('--mongo-uri', default='mongodb://localhost:27017')
    parser.add_argument('--db', default='orcapc_catalog')
    args = parser.parse_args()
    load_env(ROOT / '.env')
    import ml_products
    from product_matching.ml_ids import ml_ids_from_offer
    item_ids = list(args.item_id)
    if args.from_promotions:
        from pymongo import MongoClient
        promotions = MongoClient(args.mongo_uri)[args.db].telegram_promotions
        found = {ml_ids_from_offer(d.get('offer'))[1] for d in promotions.find({'$or': [{'offer.url': {'$regex': 'mercadoli|meli[.]la'}}, {'offer.resolved_url': {'$regex': 'mercadoli'}}]})}
        item_ids += sorted(i for i in found if i)
    if not item_ids:
        print('Nenhum ITEM_ID para testar (use --item-id MLB… ou --from-promotions).')
        return
    database = None
    if args.record:
        from pymongo import MongoClient
        database = MongoClient(args.mongo_uri)[args.db]
    report = check(list(dict.fromkeys(item_ids))[:args.limit], ml_products.MercadoLivrePriceCapability(ml_products.api, database))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
