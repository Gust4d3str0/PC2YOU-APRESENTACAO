"""Backfill `offer.resolved_url` & co. for stored Telegram promotions (HTTP redirects only, additive).

    python scripts/resolve_promotion_links.py                 # promotions never checked
    python scripts/resolve_promotion_links.py --force         # re-check everything
    python scripts/resolve_promotion_links.py --limit 50 --workers 4

Each distinct URL is resolved once. `offer.url` and every other field are left untouched.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import MongoClient  # noqa: E402

from services.product_matching.destinations import link_fields, resolve_redirects  # noqa: E402
from services.product_matching.quality import offer_url  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mongo-uri', default='mongodb://localhost:27017')
    parser.add_argument('--db', default='orcapc_catalog')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    promotions = MongoClient(args.mongo_uri)[args.db].telegram_promotions
    query = {'offer.url': {'$type': 'string'}}
    if not args.force:
        query['offer.link_checked_at'] = {'$exists': False}
    rows = [(r['_id'], r['offer']['url']) for r in promotions.find(query, {'offer.url': 1}) if offer_url(r['offer']['url'])]
    if args.limit:
        rows = rows[:args.limit]
    urls = sorted({url for _, url in rows})
    print(f'{len(rows)} promoções, {len(urls)} URLs distintas')
    with ThreadPoolExecutor(args.workers) as pool:
        resolutions = dict(zip(urls, pool.map(lambda u: resolve_redirects(u, use_cache=False), urls)))
    now = datetime.now(timezone.utc).isoformat()
    stats = Counter()
    for _id, url in rows:
        fields = link_fields(url, resolutions[url], now)
        promotions.update_one({'_id': _id, 'offer.url': url}, {'$set': {f'offer.{k}': v for k, v in fields.items()}})
        stats[fields['link_status']] += 1
    print(dict(stats))


if __name__ == '__main__':
    main()
