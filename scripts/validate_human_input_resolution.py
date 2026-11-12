"""Real local catalog + analysis route, frozen catalog, no Gemini or Atlas.

This runner never imports components. Index construction is a separate local-only step.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'services'), str(ROOT / 'api-orcamentos'), str(ROOT / 'scripts')]
from catalog_specs.human_input import parse_input
from catalog_specs.human_resolver import mongo_bundle, resolve_human, candidate_query
from catalog_specs.normalization import normalize_spec
from import_external_catalog import write_json, read_jsonl
from pymongo.monitoring import CommandListener


class QueryAudit(CommandListener):
    def __init__(self):
        self.active, self.finds, self.violations = False, 0, []
        self.patterns = set()

    def started(self,event):
        if not self.active or event.command_name != 'find':
            return
        query=event.command
        if query.get('find') != 'components':
            return
        self.finds+=1
        where=query.get('filter',{})
        limit=abs(query.get('limit',0))
        self.patterns.add((tuple(sorted(where)),limit))
        if not where or not 1<=limit<=33 or 'category' not in where or '$regex' in json.dumps(where):
            self.violations.append({'filter':where,'limit':limit})

    def succeeded(self,event):
        pass

    def failed(self,event):
        pass

UNITS = json.loads((ROOT / 'services/tests/fixtures/human-input-cases.json').read_text(encoding='utf-8'))
AMBIGUOUS = [('ram','16GB ou 32GB DDR4'), ('ram','DDR4 DDR5 32GB'), ('ram','3200 3600 DDR4 16GB'),
             ('ram','32GB 2x8GB DDR4'), ('psu','650W 750W'), ('psu','500-650W'),
             ('storage','1TB 2TB NVMe'), ('storage','1TB SATA NVMe'),
             ('cpu','Ryzen 5600X ou 5600G'), ('gpu','RTX 4070 RTX 4070 Super')]


def pc(cpu='Ryzen 7 5700X', board='B550M', ram='32GB DDR4 3200', gpu='RTX 4060 Ti',
       storage='1TB NVMe', psu='650W', case='ATX'):
    return dict(cpu=cpu,motherboard=board,ram=ram,gpu=gpu,storage=[storage],psu=psu,case=case)


NORMAL = [
    ('Pedido PC 1', pc()),
    ('Pedido PC 2', pc(cpu='i5 12400F',board='B660M DDR4',ram='16GB DDR4',gpu='RTX 3060',storage='SSD NVMe 1TB',psu='650 watts',case='mATX')),
    ('Pedido PC 3', pc(cpu='Ryzen 5 7600',board='B650 DDR5',ram='32GB DDR5 6000',gpu='RX 7800 XT',storage='NVMe 2TB',psu='750W')),
    ('Pedido PC 4', pc(cpu='Ryzen5700X',board='b550m',ram='2x16gb 3200 ddr4',gpu='rtx4060ti',storage='ssd nvme 1tb',psu='fonte 650w',case='gabinete atx')),
    ('CPU sem tier', pc(cpu='5700X', ram='2x16GB DDR4 3200')),
    ('CPU X', pc(cpu='5600X',ram='16 GB 3200 DDR4')),
    ('CPU G', pc(cpu='5600G',gpu='GeForce RTX4060Ti')),
    ('PSU marca sem SKU', pc(psu='Corsair 650W',storage='500GB SATA SSD')),
    ('DDR5 48GB', pc(cpu='7800X3D',board='B650 DDR5',ram='2x24GB DDR5 6000 CL30',psu='850W')),
    ('B760 DDR4', pc(cpu='i5-13600K',board='B760M DDR4',ram='DDR4 32GB 3600',gpu='RTX 4070 Super',psu='850W')),
    ('B760 DDR5', pc(cpu='i5-13600K',board='B760M DDR5',ram='DDR5 32GB 6000',gpu='RTX 4080 Super',psu='850W')),
    ('VRAM explícita sem SKU arbitrário', pc(gpu='RTX 4060 Ti 16GB')),
    ('SSD sem interface', pc(storage='SSD 1TB',psu='650W 80 Plus Gold')),
    ('Família sem PSU recomendado', pc(gpu='RTX3060Ti')),
]

# Complete builds use existing named boards plus explicit generic facts. No physical defaults.
for index, cpu in enumerate(['Ryzen5700X','5700X','5600X','5600G','Ryzen 5 5600','Processador Ryzen 7 5700X'],1):
    NORMAL.append((f'Completo com campos explícitos {index}', pc(cpu=cpu,board='Gigabyte B550M K',
        ram='2x16GB DDR4 3200',gpu='RTX 4060 Ti comprimento 240mm',psu='650W 80 Plus Gold',
        case='ATX mATX Mini-ITX GPU até 350mm')))

INCOMPATIBLE = [
    ('Socket AM5 em AM4',pc(cpu='Ryzen 5 7600')),
    ('Socket Intel em AM5',pc(cpu='i5 12400F',board='B650 DDR5',ram='32GB DDR5 6000')),
    ('DDR5 em placa DDR4',pc(ram='32GB DDR5 6000')),
    ('DDR4 em placa DDR5',pc(cpu='Ryzen 5 7600',board='B650 DDR5')),
    ('Fonte abaixo da GPU',pc(gpu='RTX 4070 Super',psu='450W')),
    ('Outra fonte insuficiente',pc(psu='350W')),
    ('RAM acima do limite SKU',pc(board='Gigabyte B550M K',ram='2x128GB DDR4 3200')),
    ('Mais módulos que slots SKU',pc(board='Gigabyte B550M K',ram='8x8GB DDR4 3200')),
    ('Gabinete com exclusão explícita',pc(board='Gigabyte B550M K',case='apenas Mini-ITX')),
    ('GPU explicitamente maior que espaço',pc(board='Gigabyte B550M K',gpu='RTX 4060 Ti comprimento 400mm',case='ATX mATX GPU até 300mm')),
]


class Catalog:
    def __init__(self, collection):
        self.collection, self.timings, self.requests, self.max_candidates = collection, [], [], 0

    def human_candidates(self, category, text):
        parsed = parse_input(text,category)
        result = mongo_bundle(self.collection,parsed)
        self.max_candidates = max(self.max_candidates,len(result['candidates']))
        return result

    def resolve(self, category, text):
        started = perf_counter()
        result, trace = resolve_human(text,category,self)
        elapsed = (perf_counter()-started)*1000
        self.timings.append(elapsed)
        trace['elapsed_ms'] = round(elapsed,4)
        return result, trace

    def upgrade_candidates(self, category, limit=24):
        return list(self.collection.find({'category':category},{'_id':0}).limit(min(limit,24)))

    def list_components(self, category):
        raise AssertionError('Full catalog/category scan forbidden during a request')


class ProseDouble:
    name = 'local-prose-double-no-gemini'

    def generate(self, **kwargs):
        trusted = kwargs['context']['trusted_context']
        verdict = trusted['compatibility']
        insufficient = trusted['analysis_readiness']['status'] != 'sufficient'
        state = 'attention' if verdict['issues'] else 'insufficient_data' if insufficient else 'good'
        return {'summary':'Avaliação técnica produzida localmente.', 'overall_rating':state,
                'balance':{'status':'attention' if verdict['issues'] else 'insufficient_data' if insufficient else 'balanced',
                           'explanation':'Confira as verificações do sistema.'},
                'primary_limit':None,
                'strengths':[], 'weaknesses':[], 'upgrade_priorities':[], 'warnings':[], 'missing_information':[],
                'final_recommendation':'Consulte os resultados técnicos antes de decidir uma troca.'}


def route_cases(catalog, configurations):
    from fastapi.testclient import TestClient
    import ai_routes
    from main import app
    from ai import AIService
    from ai.config import AISettings
    service = AIService(AISettings(enabled=True,api_key='offline-no-real-key',cache_ttl=0,requests_per_minute=100),ProseDouble())
    original = ai_routes.get_ai_service
    ai_routes.get_ai_service = lambda:service
    app.dependency_overrides[ai_routes.get_ai_catalog] = lambda:catalog
    results = []
    try:
        client = TestClient(app)
        for index,(label,components,expected) in enumerate(configurations,1):
            traces = [catalog.resolve(cat,name)[1] for cat,value in components.items()
                      for name in (value if isinstance(value,list) else [value]) if name]
            started = perf_counter()
            response = client.post('/ai/analyze-pc',json={'components':components,'usage':['gaming'],'resolution':'1080p'})
            body = response.json()
            elapsed = (perf_counter()-started)*1000
            verdict = body.get('compatibility',{})
            recognized = body.get('metadata',{}).get('technical_matches',0)
            passed = response.status_code == 200 and verdict.get('status') == expected and recognized == sum(bool(v) for v in components.values())
            results.append({'pc':index,'label':label,'expected':expected,'passed':passed,'http_status':response.status_code,
                            'recognized':recognized,'catalog_matches':body.get('metadata',{}).get('catalog_matches'),
                            'derived_matches':body.get('metadata',{}).get('derived_matches'),
                            'status':verdict.get('status'),'checked_rules':verdict.get('checked_rules'),
                            'pending_rules':verdict.get('unchecked_rules'),'issues':verdict.get('issues'),
                            'missing_information':body.get('analysis',{}).get('missing_information'),
                            'components':body.get('components'), 'input':components,'traces':traces,'elapsed_ms':round(elapsed,3),
                            'error':body if response.status_code != 200 else None})
    finally:
        ai_routes.get_ai_service = original
        app.dependency_overrides.pop(ai_routes.get_ai_catalog,None)
    return results


def main():
    from pymongo import MongoClient
    from pymongo.uri_parser import parse_uri
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uri',default='mongodb://127.0.0.1:27219')
    parser.add_argument('--db',default='pc2you_external_catalog_validation_release')
    args = parser.parse_args()
    if any(h not in {'localhost','127.0.0.1','::1'} for h,_ in parse_uri(args.uri)['nodelist']):
        parser.error('Local validation refuses Atlas/non-loopback hosts')
    query_audit=QueryAudit()
    client = MongoClient(args.uri,serverSelectionTimeoutMS=5000,event_listeners=[query_audit])
    collection = client[args.db].components
    count = collection.count_documents({})
    assert count == 18213, f'Expected the existing 18213-component snapshot; got {count}'
    # This offline audit is outside the resolver: immutable technical content vs the prior artifact.
    reference = {r['id']:r for r in read_jsonl(ROOT/'reports/external-catalog-local.jsonl')}
    preservation = {'technical_changes':[], 'count':count}
    for row in collection.find({}, {'_id':0}):
        for field in ('name','brand','category','technical_specs','compatibility','external_ids','prices','benchmark'):
            if row.get(field) != reference[row['id']].get(field):
                preservation['technical_changes'].append(row['id']+'.'+field)
    catalog = Catalog(collection)
    query_audit.active=True
    units = []
    for unit in UNITS:
        resolved,trace = catalog.resolve(unit['category'],unit['input'])
        feature_ok = unit['feature'] is None or trace['features'].get(unit['feature']) == unit['expected']
        units.append({**trace,'passed':feature_ok and resolved['source'] != 'user'})
    ambiguous = []
    for category,text in AMBIGUOUS:
        resolved,trace = catalog.resolve(category,text)
        ambiguous.append({**trace,'passed':resolved['source']=='user' and not resolved['specifications']})
    configurations = [(label,parts,'compatible' if index>=14 else 'partial') for index,(label,parts) in enumerate(NORMAL)]
    configurations += [(label,parts,'incompatible') for label,parts in INCOMPATIBLE]
    pcs = route_cases(catalog,configurations)
    previous = json.loads((ROOT/'reports/external-pc-validation.json').read_text(encoding='utf-8'))['results'][:3]
    comparisons_input = [(f'Comparação anterior {r["pc"]}',r['request'],'partial') for r in previous]
    comparisons_new = route_cases(catalog,comparisons_input)
    comparisons = [{'pc':old['pc'],'before':{'recognized':old['recognized'],'checked':len(old['checked_rules']),'pending':len(old['pending_rules'])},
                    'after':{'recognized':new['recognized'],'checked':len(new['checked_rules'] or []),'pending':len(new['pending_rules'] or [])},
                    'input':old['request'],'result':new} for old,new in zip(previous,comparisons_new)]
    bench = [('cpu','Ryzen5700X'),('cpu','5700X'),('gpu','rtx4060ti'),('ram','2x16GB 3200 DDR4'),('motherboard','B660M DDR4'),
             ('storage','NVMe 2TB'),('psu','650W 80 Plus Gold'),('case','Gabinete ATX')]
    times=[]
    for i in range(1000):
        start=perf_counter();catalog.resolve(*bench[i%len(bench)]);times.append((perf_counter()-start)*1000)
    times.sort()
    explain = collection.database.command('explain',{'find':collection.name,'filter':{'category':'cpu','human_lookup_keys':'cpu::5700:x'},'limit':33},verbosity='executionStats')
    benchmark={'iterations':len(times),'p50_ms':round(statistics.median(times),4),'p95_ms':round(times[950],4),'max_ms':round(max(times),4),
               'winning_plan':explain['queryPlanner']['winningPlan'],'documents_examined':explain['executionStats']['totalDocsExamined'],
               'keys_examined':explain['executionStats']['totalKeysExamined'],'p95_under_10_ms':times[950]<10,
               'max_candidates':catalog.max_candidates,'full_catalog_scans_per_request':len(query_audit.violations),'gemini_matching_calls':0,
               'component_find_commands':query_audit.finds,'query_violations':query_audit.violations,
               'query_patterns':[{'filter_fields':keys,'limit':limit} for keys,limit in sorted(query_audit.patterns)]}
    query_audit.active=False
    result={'catalog_count_before':count,'catalog_count_after':collection.count_documents({}),'catalog_preservation':preservation,
            'units':units,'ambiguities':ambiguous,'pcs':pcs,'comparisons':comparisons,'benchmark':benchmark,
            'summary':{'unit_inputs':len(units),'units_passed':sum(r['passed'] for r in units),'ambiguous_inputs':len(ambiguous),
                       'ambiguous_passed':sum(r['passed'] for r in ambiguous),'pcs':len(pcs),'pcs_passed':sum(r['passed'] for r in pcs),
                       'statuses':dict(Counter(r['status'] for r in pcs)),'incompatible_inputs':len(INCOMPATIBLE)},
            'execution':'Real analysis route and local MongoDB. Prose provider explicitly simulated. No Gemini, external data or Atlas.'}
    write_json(ROOT/'reports/human-input-resolution.json',result)
    print(json.dumps({'summary':result['summary'],'benchmark':benchmark,'comparisons':[{k:v for k,v in c.items() if k not in {'input','result'}} for c in comparisons]},ensure_ascii=False))
    print('Failures:',[(r['label'],r['status'],r['recognized'],r['error']) for r in pcs if not r['passed']])
    client.close()
    return 0 if (all(r['passed'] for r in units+ambiguous+pcs) and not preservation['technical_changes'] and not query_audit.violations and benchmark['p95_under_10_ms']) else 1


if __name__=='__main__':
    raise SystemExit(main())
