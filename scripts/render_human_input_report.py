"""Render HUMAN_INPUT_RESOLUTION_REPORT.md from reports/human-input-resolution.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
d = json.loads((ROOT / 'reports/human-input-resolution.json').read_text(encoding='utf-8'))
s, b = d['summary'], d['benchmark']
L = ['# Relatório de resolução de entradas humanas', '',
     'Execução: rota real `/ai/analyze-pc` + MongoDB local (127.0.0.1, snapshot de 18.213 componentes). '
     'Provedor de prosa simulado: nenhum Gemini, nenhum Atlas, nenhum dado externo.', '',
     '## Resumo', '',
     f'- Catálogo antes/depois: {d["catalog_count_before"]} / {d["catalog_count_after"]}; alterações técnicas: {len(d["catalog_preservation"]["technical_changes"])}',
     f'- Entradas unitárias: {s["units_passed"]}/{s["unit_inputs"]}',
     f'- Ambíguas sem resolução arbitrária: {s["ambiguous_passed"]}/{s["ambiguous_inputs"]}',
     f'- PCs informais: {s["pcs_passed"]}/{s["pcs"]} (status: {s["statuses"]})',
     f'- Benchmark ({b["iterations"]} resoluções): p50 {b["p50_ms"]} ms, p95 {b["p95_ms"]} ms, máx {b["max_ms"]} ms (meta p95 < 10 ms: {"ok" if b["p95_under_10_ms"] else "FALHOU"})',
     f'- Plano: IXSCAN `{b["winning_plan"]["inputStage"]["inputStage"]["indexName"]}`, {b["documents_examined"]} doc examinado; full scans por requisição: {b["full_catalog_scans_per_request"]}; máx. candidatos {b["max_candidates"]}; chamadas Gemini no matching: {b["gemini_matching_calls"]}', '',
     '## Antes / depois dos três PCs informais anteriores', '',
     '| PC | Antes (reconhecidos / regras / pendentes) | Depois |', '|---|---|---|']
for c in d['comparisons']:
    a, n = c['before'], c['after']
    L.append(f'| {c["pc"]} | {a["recognized"]} / {a["checked"]} / {a["pending"]} | {n["recognized"]} / {n["checked"]} / {n["pending"]} |')
L += ['', '## Entradas unitárias', '',
      '| Categoria | Entrada | Normalizada | Escopo | catalog_id | Campos derivados | Tempo (ms) | Rejeições |', '|---|---|---|---|---|---|---|---|']
for u in d['units']:
    r = u['resolution']
    L.append(f'| {r["category"]} | {u["input"]} | {u["normalized"]} | {r["resolution_scope"]} | {r["catalog_id"] or "-"} | '
             f'{", ".join(f"{k}={v}" for k, v in u["derived_fields"].items()) or "-"} | {u.get("elapsed_ms", "-")} | {", ".join(u["rejections"]) or "-"} |')
L += ['', '## Entradas ambíguas', '', '| Categoria | Entrada | Motivo | Resultado |', '|---|---|---|---|']
for u in d['ambiguities']:
    L.append(f'| {u["resolution"]["category"]} | {u["input"]} | {", ".join(u["rejections"])} | {u["resolution"]["resolution_scope"]} |')
L += ['', '## PCs (30 informais, incluindo 10 incompatíveis)', '',
      '| # | Cenário | Esperado | Obtido | Reconhecidos | Catálogo/Derivado | Regras verificadas | Pendentes | Problemas | Tempo (ms) |', '|---|---|---|---|---|---|---|---|---|---|']
for p in d['pcs']:
    L.append(f'| {p["pc"]} | {p["label"]} | {p["expected"]} | {p["status"]} | {p["recognized"]}/7 | {p["catalog_matches"]}/{p["derived_matches"]} | '
             f'{", ".join(p["checked_rules"] or []) or "-"} | {", ".join(p["pending_rules"] or []) or "-"} | {len(p["issues"] or [])} | {p["elapsed_ms"]} |')
L += ['', '## Limitações deliberadas', '',
      '- Slots de RAM, RAM máxima, comprimento de GPU, espaço máximo de GPU e formato de placa só são verificados quando vêm do SKU do catálogo ou do texto do usuário; família/modelo genéricos não os inventam.',
      '- Lista positiva de formatos de gabinete (ex.: "ATX") não exclui outros formatos; só vale como prova de incompatibilidade com "apenas".',
      '- Entradas com alternativas, faixas, negação ou valores conflitantes ficam sem resolução.', '']
(ROOT / 'HUMAN_INPUT_RESOLUTION_REPORT.md').write_text('\n'.join(L), encoding='utf-8')
print('ok')
