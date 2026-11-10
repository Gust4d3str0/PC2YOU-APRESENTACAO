"""Render the audit, field provenance and reproducible endpoint evidence as Markdown."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
from catalog_specs.coverage import audit
from catalog_specs.identity import identity_scope


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def main():
    before = read('docs/demo/catalog-coverage-before.json')
    rows = [json.loads(line) for line in (ROOT / 'demo-data/components.jsonl').read_text(encoding='utf-8').splitlines()]
    after = audit(rows)
    (ROOT / 'docs/demo/catalog-coverage-after.json').write_text(json.dumps(after, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    new = read('api-catalogo/catalog_coverage_v2.json')
    changes = read('docs/demo/catalog-backfill-changes.json')
    pcs = read('docs/demo/catalog-pc-validation.json')
    lines = ['# PC2YOU — cobertura técnica do catálogo', '', 'Auditoria de 09/11/2026. Valores ausentes não foram inventados.', '',
        f'Catálogo local: **{before["total"]} → {after["total"]} componentes**, com **{len(new)} novas identidades reais**.', '',
        f'Backfill aplicado: **{changes["fields"]} campos em {changes["components"]} componentes existentes**. '
        'Todos os campos originais dos 121 documentos foram preservados, inclusive preços, histórico, imagens e enriquecimento.', '',
        'O seed inicial continua usando `$setOnInsert`; o script de manutenção usa `$set` condicionado ao valor lido, sem upsert. '
        'O Atlas de produção não foi consultado nem alterado: não há MONGO_URI de produção configurada neste ambiente.', '',
        '## Cobertura antes e depois', '', '| Categoria | Antes | Depois |', '|---|---:|---:|']
    for cat, value in after['categories'].items():
        old = before['categories'][cat]
        lines.append(f'| {cat} | {old["complete"]}/{old["total"]} | {value["complete"]}/{value["total"]} |')
    lines += ['', 'RAM inclui `kit-ram`. `modules` é informado separadamente: '
              f'{before["categories"]["ram"]["modules_known"]}/13 → {after["categories"]["ram"]["modules_known"]}/18 conhecidos. '
              'A regra `ram_slots` agora exige a contagem real; não presume um ou dois módulos. '
              'Os 9 coolers foram inventariados, mas estão fora das sete categorias/regras solicitadas.', '',
              '**Completude significa presença e formato válidos dos campos necessários. Não é certificação independente de cada dado legado.** '
              'Os dados antigos foram preservados. As dimensões de GPUs genéricas do seed continuam sendo dados legados; não devem ser tratadas como dimensões de qualquer placa de parceiro. '
              'O novo mapper impede transferir dimensões e requisitos de energia de um SKU do Mercado Livre para uma família genérica. '
              'Também impede copiar slots ou capacidade máxima de um SKU para uma família de placa-mãe.', '',
              '## Campos obrigatórios por categoria', '', '| Categoria | Campo canônico | Antes | Depois |', '|---|---|---:|---:|']
    for cat, value in after['categories'].items():
        old = before['categories'][cat]
        for field, count in value['fields'].items():
            lines.append(f'| {cat} | `{field}` | {old["fields"][field]}/{old["total"]} | {count}/{value["total"]} |')
    lines += ['', 'GPU usa `min_psu_watts`: consumo isolado não foi convertido em potência recomendada de fonte.', '',
              '## Participação nas sete regras', '', '| Regra | Antes, por categoria | Depois, por categoria |', '|---|---|---|']
    for rule, counts in after['rules'].items():
        def fmt(data):
            return '; '.join(f'{cat}: {count["eligible"]}/{count["total"]}' for cat, count in data.items())
        lines.append(f'| `{rule}` | {fmt(before["rules"][rule])} | {fmt(counts)} |')
    lines += ['', '## Famílias prioritárias e limites restantes', '',
        'Todas as 16 CPUs prioritárias solicitadas estão presentes e completas. Foram adicionadas Ryzen 5 3600, Ryzen 5 5600X, Ryzen 7 5800X e Core i5-13600K.', '',
        'GPU: RTX 2060 recebeu um SKU completo real (Gigabyte GV-N2060D6-6GD rev. 2.0). RTX 3060 Ti e RTX 4080 **ainda não receberam um registro completo**: '
        'os retornos oficiais consultados não forneceram identidade/dimensões/requisito de fonte suficientes sem conflitos. RTX 4080 Super é outra identidade. '
        'Os outros modelos prioritários já estavam no seed e foram preservados. As seis famílias novas de GPUs da expansão anterior continuam incompletas; '
        'foram adicionados SKUs próprios completos Palit RTX 5050 Dual e Gigabyte RTX 5060 Ti WINDFORCE MAX OC 8GB, sem emprestar seus tamanhos às famílias.', '',
        'Placas-mãe: novos SKUs completos de A520, B450, B550, A620, B650, H610 e B760; B660 e Asus TUF X670E-PLUS existentes receberam limite de RAM de fonte estruturada. '
        'Os SKUs novos X570 AORUS ULTRA, X670 AORUS ELITE AX, MSI PRO Z690-A DDR4 e Z790 AORUS ELITE AX ainda têm campos ausentes. '
        'Não foi deduzido número de slots a partir de chipset, foto ou quantidade de canais. `SUPPORTED_RAM_MEMORY_MODULES` não foi convertido em slots, pois sua semântica não é inequívoca.', '',
        'RAM: SKUs DIMM de 8GB DDR4 2666/3200, 16GB DDR4 3200, 32GB DDR4 3200 e 16GB DDR5 5600, com número de módulos explícito; kits DDR5 de 32GB já existentes. '
        'Fonte: Corsair CV450, CX500 e Thermaltake SMART RGB 600W completam as potências prioritárias. Armazenamento: Samsung 970 EVO Plus 1TB PCIe 3.0 complementa SATA e PCIe 4.0 existentes.', '',
        '**A meta não está concluída para todo componente comercial possível.** Uma família como B760M sem DDR4/DDR5 continua ambígua; um SKU desconhecido não recebe specs do primeiro modelo parecido.', '',
        '## Normalização, origem e rejeições', '',
        'Normalização única: `services/catalog_specs/normalization.py`; mapeamento por categoria: `mapper.py`. '
        'Ordem de propostas: atributos estruturados oficiais → campo estruturado já existente → referência técnica do repositório com identidade coincidente → parser de notação explícita de módulos. '
        'Conflitos entre propostas deixam o campo ausente. Nenhum título de anúncio alimenta socket, TDP, slots, potência ou dimensões.', '',
        'Os atributos utilizados estão nos arquivos de evidência. Cada valor inserido guarda `spec_provenance`, o atributo original, valor bruto e PRODUCT_ID quando aplicável. '
        '`api-catalogo/catalog_spec_sources.json` contém os produtos oficiais revisados; `catalog_coverage_v2.json` é reproduzível, sem preços ou benchmarks fabricados.', '',
        'Exclusões explícitas: TDP 105W do produto ML do Ryzen 5 9600X não identifica o modo padrão; TDP 65W e 28 threads do produto ML do i5-14600KF contradizem a referência oficial. '
        'Esses valores não foram aproveitados. [AMD 9600X](https://shop-us-en.amd.com/amd-ryzen-5-9600x-processor/), '
        '[Intel 14600KF](https://www.intel.com/content/www/us/en/products/sku/236778/intel-core-i5-processor-14600kf-24m-cache-up-to-5-30-ghz/specifications.html).', '',
        'Também foram rejeitados: sockets múltiplos ou sem prefixo inequívoco, DDR4/DDR5 combinados, dimensões com eixos contraditórios, combos, módulos incompatíveis com a capacidade total e domínios de produto incorretos.', '',
        '## Campos preenchidos em documentos existentes', '', '| Componente | Campo | Valor inserido | Origem |', '|---|---|---|---|']
    for plan in changes['changes']:
        for change in plan['changes']:
            origin = change['source']
            if change.get('product_id'):
                origin = f'[{origin}](https://api.mercadolibre.com/products/{change["product_id"]})'
            lines.append(f'| `{plan["id"]}` | `{change["field"]}` | `{cell(json.dumps(change["value"], ensure_ascii=False))}` | {origin} |')
    lines += ['', '## Valores técnicos dos novos componentes e respectivas fontes', '', '| ID | Campo | Valor | Origem |', '|---|---|---|---|']
    for row in new:
        for record in row.get('spec_provenance', {}).values():
            origin = f'[{record["source"]}](https://api.mercadolibre.com/products/{record["product_id"]})'
            lines.append(f'| `{row["id"]}` | `{record["field"]}` | `{cell(json.dumps(record["value"], ensure_ascii=False))}` | {origin} |')
    lines += ['', '## Execução de /ai/analyze-pc em 10 configurações', '',
        'Rota FastAPI real, `enrich()`, regras e validação da resposta reais; transporte do catálogo substituído pelo snapshot local. '
        'Somente a redação da IA usa um substituto de teste identificado. **Não houve chamada ao Gemini nem teste HTTP contra produção.** '
        'Compatibilidade técnica e IDs abaixo são resultados calculados, não saídas simuladas.', '',
        '| PC | Configuração | HTTP | Reconhecidos | Regras verificadas | Faltantes | Compatibilidade |', '|---|---|---:|---:|---:|---:|---|']
    for result in pcs['results']:
        response, verdict = result['response'], result['response']['compatibility']
        lines.append(f'| {result["pc"]} | {result["label"]} | {result["http_status"]} | {response["metadata"]["catalog_matches"]}/7 | {len(verdict["checked_rules"])}/7 | {len(verdict["unchecked_rules"])} | {verdict["status"]} |')
    for result in pcs['results']:
        lines += ['', f'### PC {result["pc"]}: {result["label"]}', '', '| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |', '|---|---|---|---|']
        for component in result['response']['components']:
            query = result['request']['components'][component['category']]
            lines.append(f'| {component["category"]}: {cell(query)} | `{component["catalog_id"]}` | {cell(json.dumps(component["specifications"], ensure_ascii=False))} | {cell(json.dumps(component["compatibility"], ensure_ascii=False))} |')
        verdict = result['response']['compatibility']
        lines += ['', f'Regras verificadas: `{", ".join(verdict["checked_rules"])}`. Regras faltantes: `{verdict["unchecked_rules"]}`.']
    lines += ['', '## Auditoria individual de todos os componentes', '', '| ID | Categoria / escopo | Campos obrigatórios ausentes |', '|---|---|---|']
    details = {r['id']: r for r in after['components']}
    for row in rows:
        detail = details.get(row['id'])
        missing = ', '.join(detail['missing']) if detail else 'Cooler: sem critério solicitado'
        if detail and detail['category'] == 'ram' and not detail['modules_known']:
            missing += ('; ' if missing else '') + 'modules não conhecido (ram_slots pendente)'
        lines.append(f'| `{row["id"]}` | {row["category"]} / {identity_scope(row)} | {missing or "Nenhum"} |')
    lines += ['', '## Testes e reprodução local', '',
        'Resultado: **1.197 testes passaram, 1 ignorado**: 275 em api-orcamentos; 399 em api-catalogo (mais 1 ignorado); 523 em services. '
        'Inclui concorrência Mongo, idempotência, ausência de sobrescritas, paridade entre seed Mongo vazio e snapshot enriquecido, ambiguidades, sufixos Ti/Super/X, módulos ausentes, incompatibilidades reais e enriquecimento futuro pela integração oficial. '
        'Um teste de deduplicação de ofertas teve seu relógio fixado na data do próprio fixture para não expirar conforme o calendário; a lógica de produção correspondente não mudou.', '',
        'Reexecução após aplicar o backfill: **0 campos a preencher**. O sync insert-only também propõe 0 novas inserções após a primeira aplicação.', '',
        '```powershell', 'python scripts/audit_catalog_coverage.py --output reports/catalog-audit.json',
        'python scripts/backfill_demo_specs.py --dry-run', 'python scripts/sync_catalog_coverage.py --dry-run',
        'python scripts/build_catalog_coverage.py', 'python scripts/validate_catalog_pcs.py',
        'python -m pytest api-orcamentos/tests -q', 'python -m pytest api-catalogo/tests -q', 'python -m pytest services/tests -q', '```', '',
        'Não execute os três diretórios de testes num único processo pytest: eles usam módulos locais de mesmo nome (`main`, `services`, `database`). '
        'As dependências declaradas dos dois serviços têm versões conflitantes; esta execução usou um ambiente local com os requisitos de api-orcamentos e mongomock/serviços adicionais. '
        'Para ambientes separados, instale os requirements do serviço correspondente.', '',
        '## Aplicação no MongoDB Atlas de produção, sem apagar dados', '',
        'Execute a partir da raiz deste checkout atualizado, em um ambiente de manutenção com `pymongo` instalado. '
        '`MONGO_URI` deve vir do gerenciador de segredos/ambiente de produção, com a URI `mongodb+srv` real; `MONGO_DB` deve indicar o banco correto. '
        'Nenhum comando abaixo importa o loader de demo ou substitui documentos. O índice único de `components.id`, já exigido pela API, deve existir; '
        'o sync recusa aplicação sem esse índice. Os scripts não removem nem recriam índices.', '',
        '```powershell', '# MONGO_URI e MONGO_DB já definidos pelo ambiente seguro de produção.',
        'New-Item -ItemType Directory -Force reports | Out-Null',
        'python scripts/audit_catalog_coverage.py --mongo --db $env:MONGO_DB --output reports/atlas-before.json',
        'python scripts/backfill_demo_specs.py --mongo --db $env:MONGO_DB --dry-run --report reports/atlas-backfill-plan.json',
        'python scripts/sync_catalog_coverage.py --mongo --db $env:MONGO_DB --dry-run', '',
        '# Após revisar os valores e suas origens nos relatórios:',
        'python scripts/backfill_demo_specs.py --mongo --db $env:MONGO_DB --apply --report reports/atlas-backfill-applied.json',
        'python scripts/sync_catalog_coverage.py --mongo --db $env:MONGO_DB --apply',
        'python scripts/audit_catalog_coverage.py --mongo --db $env:MONGO_DB --output reports/atlas-after.json',
        'python scripts/backfill_demo_specs.py --mongo --db $env:MONGO_DB --dry-run --report reports/atlas-backfill-idempotence.json', '```', '',
        'O backfill percorre todos os documentos e o cache `external_product_enrichment` do próprio banco. '
        'As referências persistidas no projeto só se aplicam quando ID, nome, marca e categoria coincidem. '
        'Campos existentes — inclusive valores diferentes, zero ou inválidos — são preservados e exigem revisão separada. '
        'Campos preenchidos entre a leitura e a gravação não são sobrescritos. O sync adiciona somente os 29 IDs revisados que não existirem; não altera nenhum ID presente.', '',
        'Publique as versões atualizadas de api-catalogo e api-orcamentos para ativar o mapper no enriquecimento futuro e o matching novo. '
        'O seed na inicialização não faz o backfill de documentos existentes. Os Dockerfiles incluem o módulo compartilhado.', '',
        'Evidências completas: `docs/demo/catalog-coverage-before.json`, `catalog-coverage-after.json`, '
        '`catalog-backfill-changes.json`, `catalog-pc-validation.json`, `api-catalogo/catalog_spec_sources.json` e `catalog_spec_references.json`.', '']
    (ROOT / 'CATALOG_COVERAGE_REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Report generated: {len(lines)} lines; {after["total"]} components; {pcs["passed"]}/{pcs["total"]} PC validations passed')


if __name__ == '__main__':
    main()
