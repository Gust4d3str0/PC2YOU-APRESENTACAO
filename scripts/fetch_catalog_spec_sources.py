"""Read official ML Product API only; save reviewable structured source documents.

Uses existing credentials/rotating-token manager. No scraping or AI.
The output is evidence, not automatic authorization to map a SKU to a family.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'api-catalogo'), str(ROOT / 'services'), str(ROOT / 'scripts')]
from enrich_mercado_livre_products import load_env
from ml_products import MercadoLivreApi, MercadoLivreTokenManager, MercadoLivreProductNormalizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queries', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--domain', help='Official ML domain, e.g. MLB-COMPUTER_PROCESSORS')
    args = parser.parse_args()
    load_env(ROOT / '.env')
    tokens = MercadoLivreTokenManager(token_file=ROOT / '.tools/ml-catalog-token.json')
    api = MercadoLivreApi(tokens)
    rows = []
    for query in args.queries:
        params = {'site_id': 'MLB', 'q': query, 'limit': args.limit}
        if args.domain:
            params['domain_id'] = args.domain
        response = api.get('/products/search', params=params)
        print(query, response.kind, flush=True)
        if not response.ok:
            rows.append({'query': query, 'outcome': response.kind})
            continue
        for result in response.data.get('results', []):
            response = api.get_product(result['id'])
            if response.ok:
                doc = MercadoLivreProductNormalizer.normalize(response.data)
                if doc:
                    rows.append({'query': query, 'product': doc})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
