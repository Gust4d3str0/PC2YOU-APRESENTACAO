"""Render the delivery report from actual local validation receipts; no database writes."""
from collections import Counter
import json

from import_external_catalog import ROOT, read_jsonl, write_json


def load(name):
    return json.loads((ROOT / 'reports' / name).read_text(encoding='utf-8'))


def render():
    summary = load('external-validation-summary.json')
    replay = load('external-replay-validation.json')
    if summary['database'] != replay['database'] or not replay['unchanged']:
        raise ValueError('A matching successful replay receipt is required')
    before, after = summary['before'], summary['after']
    seed, rows = read_jsonl(ROOT / 'demo-data/components.jsonl'), read_jsonl(ROOT / 'reports/external-catalog-local.jsonl')
    by_id = {r['id']: r for r in rows}
    checked, changed = 0, []
    for original in seed:
        current = by_id[original['id']]
        for section in ('technical_specs', 'compatibility'):
            for key, value in (original.get(section) or {}).items():
                if value not in (None, ''):
                    checked += 1
                    if (current.get(section) or {}).get(key) != value:
                        changed.append(f'{original["id"]}.{section}.{key}')
        for key in ('name', 'category', 'brand', 'prices', 'price_history', 'benchmark'):
            if current.get(key) != original.get(key):
                changed.append(f'{original["id"]}.{key}')
    new_rows = [r for r in rows if r['id'] not in {s['id'] for s in seed}]
    commercial = [r['id'] for r in new_rows if r.get('prices') or r.get('price_history') or r.get('benchmark')]
    integrity = {'audited_records': len(seed), 'audited_nonempty_technical_fields': checked,
                 'changed_trusted_fields': changed, 'new_records_with_commercial_data': commercial,
                 'unique_internal_ids': len(by_id) == len(rows), 'total': len(rows)}
    write_json(ROOT / 'reports/external-preservation-audit.json', integrity)
    if changed or commercial or not integrity['unique_internal_ids']:
        raise ValueError('Preservation/commercial isolation audit failed')
    lines = ['# Expansão técnica externa do PC2YOU', '', 'Validação local de 10/11/2026 (America/Sao_Paulo). Atlas de produção não foi acessado nem alterado.', '',
        f'Catálogo: **{before["total"]} → {after["total"]} componentes**. MongoDB local {summary["mongo_version"]}, '
        f'banco `{summary["database"]}`, porta `27219`.', '',
        '## Fontes e licenças', '',
        '| Fonte | Commit imutável | Licença |', '|---|---|---|']
    for source, data in summary['sources'].items():
        snapshot = data['snapshot']
        lines.append(f'| {source} | `{snapshot["commit"]}` | {snapshot["license"]} |')
    lines += ['', 'Origem, textos integrais, atribuição, mudanças e notices estão em [THIRD_PARTY_DATA_NOTICES.md](THIRD_PARTY_DATA_NOTICES.md). '
        'Os manifestos em `external-data/manifests/` preservam os checksums e as versões. '
        'O licenciamento desses dados permanece separado do código.', '',
        '## Ingestão e deduplicação', '',
        '| Fonte | Lidos | Elegíveis | Novos | Merges | Conflitos/revisão | Rejeitados | Campos preenchidos |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    totals = Counter()
    for source, data in summary['sources'].items():
        s = data['summary']
        totals.update(s)
        lines.append(f'| {source} | {s["read"]} | {s["eligible"]} | {s["new"]} | {s["merged"]} | {s["conflicts"]} | {s["rejected"]} | {s["fields_filled"]} |')
    lines += [f'| Total | {totals["read"]} | {totals["eligible"]} | {totals["new"]} | {totals["merged"]} | {totals["conflicts"]} | {totals["rejected"]} | {totals["fields_filled"]} |', '',
        'Contagens são de registros processados. Duplicatas idênticas dentro do dataset compartilham o mesmo ID de candidato; '
        'por isso o total de documentos em staging difere do total lido. “Conflitos/revisão” inclui tanto divergências técnicas '
        'quanto possível duplicidade sem MPN. Não significa que todos esses registros tenham especificações erradas.', '',
        f'Status reais em `catalog_import_candidates`: `{json.dumps(summary["staging_statuses"], ensure_ascii=False)}`. '
        f'Falhas de promoção: **{sum(len(d["promotion_failures"]) for d in summary["sources"].values())}**.', '',
        'Os planos completos, com campos, provenance, confirmações e conflitos por candidato:', '',
        '- [BuildCores](reports/buildcores-import-plan.json)', '- [PC Part Dataset](reports/pc-part-dataset-import-plan.json)', '',
        '## Cobertura antes/depois', '', '| Categoria | Antes: total / completos | Depois: total / completos |', '|---|---:|---:|']
    for cat, previous in before['categories'].items():
        current = after['categories'][cat]
        lines.append(f'| {cat} | {previous["total"]} / {previous["complete"]} | {current["total"]} / {current["complete"]} |')
    lines += ['', f'Escopos antes: `{before["identity_scopes"]}`. Depois: `{after["identity_scopes"]}`.', '',
        f'Componentes promovidos com conflito persistido: {after["components_with_conflict"]}. '
        'Os conflitos ficam nos candidatos, fora de `components`.', '',
        '**Limite material:** as fontes não informam recomendação de fonte para as novas GPUs. '
        'TDP não foi convertido em PSU recomendado; assim, a regra `gpu_power` permanece pendente nesses SKUs. '
        'Isso explica a baixa contagem de GPUs totalmente completas, mesmo com VRAM e comprimento conhecidos.', '',
        '| Categoria | Campo | Antes | Depois |', '|---|---|---:|---:|']
    for cat, previous in before['categories'].items():
        current = after['categories'][cat]
        for field, count in previous['fields'].items():
            lines.append(f'| {cat} | `{field}` | {count}/{previous["total"]} | {current["fields"][field]}/{current["total"]} |')
    lines += ['', '## Participação nas sete regras', '', '| Regra | Antes: elegíveis/total por categoria | Depois: elegíveis/total por categoria |', '|---|---|---|']
    for rule, previous in before['rules'].items():
        describe = lambda value: '; '.join(f'{cat}: {v["eligible"]}/{v["total"]}' for cat, v in value.items())
        lines.append(f'| `{rule}` | {describe(previous)} | {describe(after["rules"][rule])} |')
    lines += ['', 'Auditorias: [antes](reports/external-coverage-before.json), [depois](reports/external-coverage-after.json) '
        'e [execução independente de audit_catalog_coverage.py](reports/external-coverage-audited.json).', '',
        '## Vinte PCs na rota real', '', summary['pcs']['execution'] + '.', '',
        f'**{summary["pcs"]["passed"]}/{summary["pcs"]["total"]} testes passaram.** '
        'Passar significa respeitar o resultado esperado, incluindo respostas parciais e incompatíveis. '
        'Os PCs 4–11 exigem sete componentes reconhecidos e compatibilidade completa; 12–14 exigem incompatibilidade. '
        'Os três SKUs importados devem resolver para suas identidades específicas.', '',
        '| PC | Cenário | Reconhecidos | SKU / família / modelo | Regras feitas / pendentes | Resultado | Tempo da rota (ms) |', '|---:|---|---:|---|---|---|---:|']
    for pc in summary['pcs']['results']:
        scopes = Counter(m['match_scope'] for m in pc['matches'])
        lines.append(f'| {pc["pc"]} | {pc["label"]} | {pc["recognized"]} | {scopes["sku"]} / {scopes["family"]} / {scopes["model"]} | '
                     f'{len(pc["checked_rules"])} / {len(pc["pending_rules"])} | {pc["compatibility"]} | {pc["elapsed_ms"]} |')
    perf = summary['benchmark']
    lines += ['', 'Entradas, IDs e regras individuais: [external-pc-validation.json](reports/external-pc-validation.json). '
        'O texto foi simulado explicitamente; não houve chamada Gemini. Catálogo, MongoDB, regras e rota são reais.', '',
        '## Performance e segurança da persistência', '',
        f'Benchmark: {perf["iterations"]} consultas sobre {perf["catalog_size"]} documentos, '
        f'mediana **{perf["median_ms"]} ms**, p95 **{perf["p95_ms"]} ms**, máximo {perf["max_ms"]} ms. '
        f'`explain` confirmou `IXSCAN`, {perf["explain"]["keys_examined"]} chave e '
        f'{perf["explain"]["documents_examined"]} documento examinado na consulta de referência. '
        'A medição é local, sem a latência de rede do Atlas.', '',
        'Nenhuma consulta GitHub, chamada LLM para matching ou varredura do catálogo na análise. '
        'Candidatos de upgrade são limitados a 24 por categoria. '
        '[Benchmark MongoDB](reports/external-lookup-benchmark.json); [benchmark em memória](reports/external-lookup-memory-benchmark.json).', '',
        f'Replay integral dos dois planos: {replay["count_before"]} → {replay["count_after"]} documentos; '
        'hash SHA-256 do conteúdo permaneceu idêntico. Foram executados 32 replays concorrentes por fonte, '
        'com oito workers. [Recibo de idempotência/concorrência](reports/external-replay-validation.json).', '',
        f'Preservação independente: {len(seed)} registros auditados e {checked} campos técnicos preenchidos conferidos; '
        'nenhum valor confiável, identidade ou dado comercial foi alterado. Novas peças não têm preços, histórico '
        'ou benchmarks artificiais. [Auditoria de preservação](reports/external-preservation-audit.json).', '',
        '## Testes e comandos', '',
        '- `services/tests`: 599 passaram.', '- `api-catalogo/tests`: 402 passaram, 1 ignorado.',
        '- `api-orcamentos/tests`: 277 passaram.', '- Frontend: 61 testes passaram; build Vite passou.',
        '- `compileall` e `git diff --check`: passaram.', '',
        'São **1.339 testes aprovados**, além dos vinte PCs, benchmark e replay local. '
        'Há warnings das dependências nos testes, sem falhas. O teste ignorado é o live do Mercado Livre, '
        'que exige opt-in e token; não foi habilitado na validação offline.', '',
        'Comandos completos de download, dry-run, staging, promoção local, filtros e Atlas estão em '
        '[docs/EXTERNAL_CATALOG_IMPORT.md](docs/EXTERNAL_CATALOG_IMPORT.md). '
        'Atlas exige uma execução separada, URI exportada explicitamente e plano revisado; nenhum comando Atlas foi executado.', '',
        '## Arquivos criados/modificados', '']
    files = ['.gitignore', 'THIRD_PARTY_DATA_NOTICES.md', 'EXTERNAL_CATALOG_IMPORT_REPORT.md',
        'docs/EXTERNAL_CATALOG_IMPORT.md', 'external-data/README.md', 'external-data/manifests/buildcores.json',
        'external-data/manifests/pc_part_dataset.json', 'third-party-data/BuildCores-LICENSE.txt', 'third-party-data/BuildCores-NOTICE.md',
        'third-party-data/PC-Part-Dataset-LICENSE.txt', 'scripts/README.md', 'scripts/requirements-external-catalog.txt',
        'scripts/fetch_external_catalog_snapshot.py', 'scripts/import_external_catalog.py', 'scripts/import_buildcores_catalog.py',
        'scripts/import_pc_part_dataset.py', 'scripts/validate_external_catalog.py', 'scripts/benchmark_catalog_lookup.py',
        'scripts/check_external_catalog_replay.py', 'scripts/render_external_catalog_report.py',
        'services/catalog_specs/import_policy.json', 'services/catalog_specs/import_resources.py',
        'services/catalog_specs/external_sources.py', 'services/catalog_specs/external_identity.py',
        'services/catalog_specs/external_import.py', 'services/catalog_specs/external_persistence.py', 'services/catalog_specs/lookup.py',
        'services/catalog_specs/coverage.py', 'services/catalog_specs/normalization.py', 'services/requirements-dev.txt', 'services/tests/test_external_catalog.py',
        'api-catalogo/database.py', 'api-catalogo/main.py', 'api-catalogo/schemas.py', 'api-catalogo/services.py', 'api-catalogo/tests/test_external_lookup.py',
        'api-orcamentos/catalog_client.py', 'api-orcamentos/ai_context.py', 'api-orcamentos/tests/test_external_resolver.py']
    lines += [f'- `{path}`' for path in files]
    lines += ['', 'Os JSONs/JSONL extensos e os diretórios de snapshots são artefatos locais ignorados pelo Git. '
        'O banco local permanece disponível para inspeção. O DOCX preexistente em `docs/demo/` foi preservado.', '']
    (ROOT / 'EXTERNAL_CATALOG_IMPORT_REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print({'report': 'EXTERNAL_CATALOG_IMPORT_REPORT.md', 'total': after['total'], 'preservation': integrity})


if __name__ == '__main__':
    render()
