"""Read-only smoke checks against the independently running demo."""
import json
from pathlib import Path
import requests

root = Path(__file__).resolve().parents[1]
checks = []

def check(base, path, expected=200, method='GET', **kwargs):
    response = requests.request(method, base+path, timeout=25, **kwargs)
    checks.append({'method':method, 'path':path, 'status':response.status_code, 'expected':expected})
    assert response.status_code == expected, (path, response.status_code)
    return response

catalog = 'http://localhost:8012'
ai = 'http://localhost:8013'
for path in ['/health/ready','/commerce/catalog','/promotions','/components/ryzen-5-5600','/components/ryzen-5-5600/offers','/components/ryzen-5-5600/price-history','/demo/status','/demo/metrics','/demo/database','/demo/database/components','/demo/telegram-latest','/demo/ml-components','/demo/ml-example']:
    check(catalog, path)
check(catalog, '/demo/matcher', params={'text':'Processador AMD Ryzen 7 7800X3D 4.2GHz AM5'})
check(catalog, '/demo/telegram-parse', params={'text':'Processador AMD Ryzen 7 7800X3D por R$ 2399,00 https://kabum.com.br/produto/12345'})
for name in ['components','telegram_promotions','product_price_history','external_product_enrichment','ml_integration_state','telegram_service_status']:
    check(catalog, '/demo/database/'+name)
check(catalog, '/demo/database/users', 404)
check(catalog, '/demo/database/components?page_size=100', 422)
check(ai, '/demo/ai-status')
check(ai, '/demo/ai-context', params={'configuration':(root/'docs/demo/preset.json').read_text()})
for base,path in [(catalog,'/demo/matcher'),(catalog,'/demo/database/components'),(ai,'/demo/ai-context')]:
    for method in ['POST','PUT','PATCH','DELETE']:
        check(base,path,403,method,json={})
for path in ['/','/apresentacao','/analyze-pc','/components/ryzen-5-5600']:
    check('http://localhost:5174',path)
(root/'docs/demo/smoke-validation.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
print(f'{len(checks)} smoke checks passed.')
