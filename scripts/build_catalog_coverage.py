"""Rebuild the reviewed technical expansion using persisted official API attributes only.

No network. Does not change the snapshot or a database. Reproducible output in api-catalogo/.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from catalog_specs import plan_backfill, apply_plan
from catalog_specs.mapper import attribute_values
from catalog_audit.seed_io import load_seed


def build():
    catalog = ROOT / 'api-catalogo'
    registry = json.loads((catalog / 'catalog_spec_sources.json').read_text(encoding='utf-8'))
    rows, references = [], []
    baseline = {r['id']: r for r in load_seed(catalog / 'seed.py')}
    baseline.update({r['id']: r for r in json.loads((catalog / 'catalog_enrichment_v1.json').read_text(encoding='utf-8'))})
    for item in registry['new_components'] + registry['existing_components']:
        existing = item['id'] in baseline
        identity = baseline[item['id']] if existing else item
        row = {k: identity[k] for k in ('id', 'name', 'category', 'brand')}
        row.update(technical_specs={}, compatibility={}, identity_scope=item.get('identity_scope', 'sku'))
        docs = []
        for pid in item['product_ids']:
            doc = registry['products'][pid]
            docs.append({**doc, 'matches': {row['id']: {'status': 'matched', 'conflicts': []}}})
        plan = plan_backfill(row, docs)
        filled = apply_plan(row, plan)
        if item.get('aliases'):
            filled['aliases'] = item['aliases']
        if existing:
            for change in plan['changes']:
                references.append({'id': row['id'], 'identity': {k: row[k] for k in ('name', 'category', 'brand')},
                                   'fields': {change['field']: change['value']}, 'source': change['source'],
                                   'product_id': change.get('product_id'), 'raw': change.get('raw'),
                                   'urls': [f'https://api.mercadolibre.com/products/{change["product_id"]}']})
            continue
        first = registry['products'][item['product_ids'][0]]
        attrs = attribute_values(first)
        # Preserve explicit commercial model/part number; never derive a critical spec from the title.
        if attrs.get('MODEL'):
            filled['technical_specs']['model'] = attrs['MODEL']
        filled.update(image=f'/components/default-{row["category"]}.svg',
                      description=f'{row["name"]}. Dados estruturados da API oficial do Mercado Livre.',
                      benchmark={}, prices=[], price_history=[])
        filled['external_enrichment'] = {'mercado_livre': {
            **first, 'match_status': 'matched', 'match_basis': 'reviewed_catalog_spec_sources',
            'brand_variant': False, 'external_conflict': False,
        }}
        rows.append(filled)
    for filename, data in [('catalog_coverage_v2.json', rows), ('catalog_spec_references.json', references)]:
        (catalog / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return rows, references


if __name__ == '__main__':
    rows, refs = build()
    print(f'{len(rows)} reviewed components; {len(refs)} existing-SKU field references')
