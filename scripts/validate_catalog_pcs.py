"""Exercise the real /ai/analyze-pc route, catalog enrichment and AI response validation.

Only catalog transport (local snapshot) and prose provider (explicit test double) are replaced.
No Gemini, external HTTP or production database. Technical specs and verdicts are real.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'api-orcamentos'), str(ROOT / 'services')]

PCS = [
    ('AM4 B550 / RTX 3060', 'Processador AMD Ryzen 5 5600', 'Gigabyte B550M K', 'kingston-kf432c16bb-16', 'RTX 3060', '650W'),
    ('AM4 B550 / RTX 4070 Super', 'Ryzen 7 5700X AMD', 'ASRock B550 PG VELOCITA', 'kit-ram-32gb-ddr4-3600', 'RTX 4070 Super', '750W'),
    ('Intel B660 / RTX 4060', 'i5-12400F', 'Gigabyte B660M AORUS PRO', 'kingston-kf432c16bb-16', 'RTX 4060', '650W'),
    ('AM5 B650 / RX 7800 XT', 'AMD Ryzen 5 7600', 'Gigabyte B650 Gaming X AX V2', 'kit-ram-32gb-ddr5-6000', 'RX 7800 XT', '750W'),
    ('AM4 B450 / RX 6600', 'AMD Ryzen 5 3600', 'Revenger G-B450', 'kingston-kvr26n19s8-8', 'RX 6600', 'Corsair CX500'),
    ('AM4 A520 / RX 6650 XT', 'AMD Ryzen 5 5500', 'ASRock A520M-HDV', 'kingston-kf432c16bb-8', 'RX 6650 XT', '550W'),
    ('AM4 B550 / RTX 4060 Ti', 'AMD Ryzen 5 5600X', 'ASRock B550 PG VELOCITA', 'kingston-kf432c16bb-32', 'RTX 4060 Ti', '650W'),
    ('AM5 A620 / RX 7700 XT', 'AMD Ryzen 7 7800X3D', 'ASRock A620M-C', 'kit-ram-32gb-ddr5-6000', 'RX 7700 XT', '750W'),
    ('Intel B760 DDR4 / RTX 4070', 'Intel Core i5-13600K', 'Gigabyte B760M K DDR4', 'kit-ram-16gb-ddr4-3200', 'RTX 4070', '750W'),
    ('Intel B760 DDR5 / RTX 4080 Super', 'Intel Core i7-14700K', 'Gigabyte B760M DS3H DDR5', 'kit-ram-64gb-ddr5-6000', 'RTX 4080 Super', '850W'),
]


class SnapshotCatalog:
    def __init__(self, path=ROOT / 'demo-data/components.jsonl'):
        self.items = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

    def list_components(self, category):
        return [r for r in self.items if r['category'] == category]

    def search_components(self, category, query):
        return [r for r in self.list_components(category) if r['id'] == query or query.casefold() in r['name'].casefold()]


class ValidationProseProvider:
    name = 'offline-validation-double'

    def generate(self, **kwargs):
        return {'summary': 'Execução local de validação técnica do catálogo.', 'overall_rating': 'good',
                'balance': {'status': 'balanced', 'explanation': 'Não foram feitas medições de desempenho.'},
                'primary_limit': None,
                'strengths': [], 'weaknesses': [], 'upgrade_priorities': [], 'warnings': [], 'missing_information': [],
                'final_recommendation': 'Consulte os resultados determinísticos de compatibilidade.'}


def run():
    from fastapi.testclient import TestClient
    import ai_routes
    from main import app
    from ai import AIService
    from ai.config import AISettings
    service = AIService(AISettings(enabled=True, api_key='offline-no-real-key', cache_ttl=0), ValidationProseProvider())
    catalog = SnapshotCatalog()
    original = ai_routes.get_ai_service
    ai_routes.get_ai_service = lambda: service
    app.dependency_overrides[ai_routes.get_ai_catalog] = lambda: catalog
    results = []
    try:
        client = TestClient(app)
        for index, (label, cpu, board, ram, gpu, psu) in enumerate(PCS, 1):
            components = dict(cpu=cpu, motherboard=board, ram=ram, gpu=gpu, psu=psu,
                              storage=['Samsung 970 EVO Plus MZ-V7S1T0 1TB NVMe PCIe 3.0' if index == 5 else 'Kingston NV3 1TB NVMe M.2'],
                              case='Lian Li LANCOOL 216')
            payload = {'components': components, 'usage': ['gaming'], 'resolution': '1080p'}
            response = client.post('/ai/analyze-pc', json=payload)
            body = response.json()
            verdict = body.get('compatibility', {})
            success = (response.status_code == 200 and body['metadata']['catalog_matches'] == 7
                       and len(verdict['checked_rules']) == 7 and not verdict['unchecked_rules'] and verdict['valid'] is True)
            results.append({'pc': index, 'label': label, 'request': payload, 'http_status': response.status_code,
                            'passed': success, 'response': body})
    finally:
        ai_routes.get_ai_service = original
        app.dependency_overrides.pop(ai_routes.get_ai_catalog, None)
    return {'execution': 'real FastAPI route, local catalog transport, simulated prose only; no Gemini',
            'total': len(results), 'passed': sum(r['passed'] for r in results), 'results': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/demo/catalog-pc-validation.json')
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for item in result['results']:
        print(item['pc'], item['label'], item['http_status'], 'PASS' if item['passed'] else 'FAIL',
              item['response'].get('metadata', {}).get('catalog_matches'), item['response'].get('compatibility'))
    raise SystemExit(0 if result['passed'] == result['total'] else 1)
