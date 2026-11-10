# Expansão técnica externa do PC2YOU

Validação local de 10/11/2026 (America/Sao_Paulo). Atlas de produção não foi acessado nem alterado.

Catálogo: **150 → 18213 componentes**. MongoDB local 8.0.5, banco `pc2you_external_catalog_validation_release`, porta `27219`.

## Fontes e licenças

| Fonte | Commit imutável | Licença |
|---|---|---|
| buildcores | `e4838129c57b26d4f0711871d5ae68f3a9c848a9` | CC-BY-NC-SA-4.0 |
| pc_part_dataset | `c52a04ca9465c83997ed335f7767b09a2005dd26` | MIT |

Origem, textos integrais, atribuição, mudanças e notices estão em [THIRD_PARTY_DATA_NOTICES.md](THIRD_PARTY_DATA_NOTICES.md). Os manifestos em `external-data/manifests/` preservam os checksums e as versões. O licenciamento desses dados permanece separado do código.

## Ingestão e deduplicação

| Fonte | Lidos | Elegíveis | Novos | Merges | Conflitos/revisão | Rejeitados | Campos preenchidos |
|---|---:|---:|---:|---:|---:|---:|---:|
| buildcores | 23854 | 20122 | 17942 | 815 | 1365 | 3732 | 54297 |
| pc_part_dataset | 43100 | 7286 | 121 | 314 | 6851 | 35814 | 246 |
| Total | 66954 | 27408 | 18063 | 1129 | 8216 | 39546 | 54543 |

Contagens são de registros processados. Duplicatas idênticas dentro do dataset compartilham o mesmo ID de candidato; por isso o total de documentos em staging difere do total lido. “Conflitos/revisão” inclui tanto divergências técnicas quanto possível duplicidade sem MPN. Não significa que todos esses registros tenham especificações erradas.

Status reais em `catalog_import_candidates`: `{"accepted": 18051, "merged": 1073, "conflict": 8080, "rejected": 37452}`. Falhas de promoção: **0**.

Os planos completos, com campos, provenance, confirmações e conflitos por candidato:

- [BuildCores](reports/buildcores-import-plan.json)
- [PC Part Dataset](reports/pc-part-dataset-import-plan.json)

## Cobertura antes/depois

| Categoria | Antes: total / completos | Depois: total / completos |
|---|---:|---:|
| cpu | 40 / 37 | 247 / 224 |
| motherboard | 27 / 14 | 2544 / 2528 |
| ram | 18 / 18 | 3618 / 3618 |
| gpu | 29 / 23 | 3032 / 23 |
| psu | 10 / 10 | 3049 / 3049 |
| case | 6 / 6 | 3545 / 3360 |
| storage | 11 / 11 | 2169 / 2169 |

Escopos antes: `{'sku': 62, 'family': 47, 'model': 41}`. Depois: `{'sku': 17910, 'family': 55, 'model': 248}`.

Componentes promovidos com conflito persistido: 0. Os conflitos ficam nos candidatos, fora de `components`.

**Limite material:** as fontes não informam recomendação de fonte para as novas GPUs. TDP não foi convertido em PSU recomendado; assim, a regra `gpu_power` permanece pendente nesses SKUs. Isso explica a baixa contagem de GPUs totalmente completas, mesmo com VRAM e comprimento conhecidos.

| Categoria | Campo | Antes | Depois |
|---|---|---:|---:|
| cpu | `compatibility.socket` | 40/40 | 224/247 |
| cpu | `technical_specs.cores` | 40/40 | 247/247 |
| cpu | `technical_specs.threads` | 40/40 | 224/247 |
| cpu | `technical_specs.tdp_watts` | 37/40 | 247/247 |
| motherboard | `compatibility.socket` | 27/27 | 2544/2544 |
| motherboard | `compatibility.memory_type` | 27/27 | 2544/2544 |
| motherboard | `technical_specs.memory_slots` | 17/27 | 2535/2544 |
| motherboard | `technical_specs.max_memory_gb` | 18/27 | 2532/2544 |
| motherboard | `compatibility.form_factor` | 26/27 | 2542/2544 |
| ram | `technical_specs.capacity` | 18/18 | 3618/3618 |
| ram | `compatibility.memory_type` | 18/18 | 3618/3618 |
| ram | `technical_specs.speed` | 18/18 | 3618/3618 |
| gpu | `technical_specs.memory` | 29/29 | 3032/3032 |
| gpu | `technical_specs.length_mm` | 23/29 | 3018/3032 |
| gpu | `compatibility.min_psu_watts` | 23/29 | 23/3032 |
| psu | `technical_specs.wattage` | 10/10 | 3049/3049 |
| case | `compatibility.supported_form_factors` | 6/6 | 3509/3545 |
| case | `compatibility.max_gpu_length_mm` | 6/6 | 3396/3545 |
| storage | `technical_specs.capacity` | 11/11 | 2169/2169 |
| storage | `technical_specs.interface` | 11/11 | 2169/2169 |

## Participação nas sete regras

| Regra | Antes: elegíveis/total por categoria | Depois: elegíveis/total por categoria |
|---|---|---|
| `cpu_socket` | cpu: 40/40; motherboard: 27/27 | cpu: 224/247; motherboard: 2544/2544 |
| `ram_type` | motherboard: 27/27; ram: 18/18 | motherboard: 2544/2544; ram: 3618/3618 |
| `ram_slots` | motherboard: 17/27; ram: 11/18 | motherboard: 2535/2544; ram: 3611/3618 |
| `ram_capacity` | motherboard: 18/27; ram: 18/18 | motherboard: 2532/2544; ram: 3618/3618 |
| `gpu_power` | gpu: 23/29; psu: 10/10 | gpu: 23/3032; psu: 3049/3049 |
| `board_case` | motherboard: 26/27; case: 6/6 | motherboard: 2542/2544; case: 3509/3545 |
| `gpu_case` | gpu: 23/29; case: 6/6 | gpu: 3018/3032; case: 3396/3545 |

Auditorias: [antes](reports/external-coverage-before.json), [depois](reports/external-coverage-after.json) e [execução independente de audit_catalog_coverage.py](reports/external-coverage-audited.json).

## Vinte PCs na rota real

real FastAPI route, real local MongoDB catalog, simulated prose only; no Gemini.

**20/20 testes passaram.** Passar significa respeitar o resultado esperado, incluindo respostas parciais e incompatíveis. Os PCs 4–11 exigem sete componentes reconhecidos e compatibilidade completa; 12–14 exigem incompatibilidade. Os três SKUs importados devem resolver para suas identidades específicas.

| PC | Cenário | Reconhecidos | SKU / família / modelo | Regras feitas / pendentes | Resultado | Tempo da rota (ms) |
|---:|---|---:|---|---|---|---:|
| 1 | A: AM4 / 4060 Ti, informal | 5 | 2 / 2 / 1 | 4 / 3 | partial | 51.868 |
| 2 | B: Intel / 3060, informal | 4 | 1 / 2 / 1 | 1 / 6 | partial | 19.498 |
| 3 | C: AM5 / RX 7800, informal | 4 | 0 / 3 / 1 | 2 / 5 | partial | 15.807 |
| 4 | AM4 complete | 7 | 4 / 2 / 1 | 7 / 0 | compatible | 33.567 |
| 5 | Intel complete | 7 | 4 / 2 / 1 | 7 / 0 | compatible | 40.788 |
| 6 | AM5 complete | 7 | 4 / 2 / 1 | 7 / 0 | compatible | 42.257 |
| 7 | CPU suffix X | 7 | 4 / 2 / 1 | 7 / 0 | compatible | 33.55 |
| 8 | CPU suffix base | 7 | 4 / 2 / 1 | 7 / 0 | compatible | 31.883 |
| 9 | CPU suffix G | 7 | 4 / 2 / 1 | 7 / 0 | compatible | 29.375 |
| 10 | Intel K / DDR4 | 7 | 4 / 2 / 1 | 7 / 0 | compatible | 31.952 |
| 11 | Intel DDR5 | 7 | 4 / 2 / 1 | 7 / 0 | compatible | 37.49 |
| 12 | Socket incompatible | 7 | 4 / 2 / 1 | 7 / 0 | incompatible | 12.434 |
| 13 | DDR incompatible | 7 | 4 / 2 / 1 | 7 / 0 | incompatible | 11.661 |
| 14 | Power insufficient | 7 | 5 / 1 / 1 | 7 / 0 | incompatible | 12.116 |
| 15 | GPU expanded family Ti | 6 | 4 / 1 / 1 | 5 / 2 | partial | 13.084 |
| 16 | Unknown CPU stays unknown | 2 | 0 / 2 / 0 | 0 / 7 | partial | 12.726 |
| 17 | Missing SKU remains unknown | 3 | 1 / 1 / 1 | 0 / 7 | partial | 12.411 |
| 18 | Imported gpu SKU: gpu-ext-4f659a2bfb4baec8db846708 | 7 | 5 / 1 / 1 | 6 / 1 | partial | 14.136 |
| 19 | Imported ram SKU: ram-ext-61cd02b80c8d901ad870508d | 7 | 4 / 2 / 1 | 7 / 0 | incompatible | 13.246 |
| 20 | Imported storage SKU: storage-ext-a3f6a5487b0ca9beaabe0270 | 7 | 4 / 2 / 1 | 7 / 0 | compatible | 29.733 |

Entradas, IDs e regras individuais: [external-pc-validation.json](reports/external-pc-validation.json). O texto foi simulado explicitamente; não houve chamada Gemini. Catálogo, MongoDB, regras e rota são reais.

## Performance e segurança da persistência

Benchmark: 1000 consultas sobre 18213 documentos, mediana **0.4496 ms**, p95 **0.6639 ms**, máximo 1.281 ms. `explain` confirmou `IXSCAN`, 1 chave e 1 documento examinado na consulta de referência. A medição é local, sem a latência de rede do Atlas.

Nenhuma consulta GitHub, chamada LLM para matching ou varredura do catálogo na análise. Candidatos de upgrade são limitados a 24 por categoria. [Benchmark MongoDB](reports/external-lookup-benchmark.json); [benchmark em memória](reports/external-lookup-memory-benchmark.json).

Replay integral dos dois planos: 18213 → 18213 documentos; hash SHA-256 do conteúdo permaneceu idêntico. Foram executados 32 replays concorrentes por fonte, com oito workers. [Recibo de idempotência/concorrência](reports/external-replay-validation.json).

Preservação independente: 150 registros auditados e 1066 campos técnicos preenchidos conferidos; nenhum valor confiável, identidade ou dado comercial foi alterado. Novas peças não têm preços, histórico ou benchmarks artificiais. [Auditoria de preservação](reports/external-preservation-audit.json).

## Testes e comandos

- `services/tests`: 599 passaram.
- `api-catalogo/tests`: 402 passaram, 1 ignorado.
- `api-orcamentos/tests`: 277 passaram.
- Frontend: 61 testes passaram; build Vite passou.
- `compileall` e `git diff --check`: passaram.

São **1.339 testes aprovados**, além dos vinte PCs, benchmark e replay local. Há warnings das dependências nos testes, sem falhas. O teste ignorado é o live do Mercado Livre, que exige opt-in e token; não foi habilitado na validação offline.

Comandos completos de download, dry-run, staging, promoção local, filtros e Atlas estão em [docs/EXTERNAL_CATALOG_IMPORT.md](docs/EXTERNAL_CATALOG_IMPORT.md). Atlas exige uma execução separada, URI exportada explicitamente e plano revisado; nenhum comando Atlas foi executado.

## Arquivos criados/modificados

- `.gitignore`
- `THIRD_PARTY_DATA_NOTICES.md`
- `EXTERNAL_CATALOG_IMPORT_REPORT.md`
- `docs/EXTERNAL_CATALOG_IMPORT.md`
- `external-data/README.md`
- `external-data/manifests/buildcores.json`
- `external-data/manifests/pc_part_dataset.json`
- `third-party-data/BuildCores-LICENSE.txt`
- `third-party-data/BuildCores-NOTICE.md`
- `third-party-data/PC-Part-Dataset-LICENSE.txt`
- `scripts/README.md`
- `scripts/requirements-external-catalog.txt`
- `scripts/fetch_external_catalog_snapshot.py`
- `scripts/import_external_catalog.py`
- `scripts/import_buildcores_catalog.py`
- `scripts/import_pc_part_dataset.py`
- `scripts/validate_external_catalog.py`
- `scripts/benchmark_catalog_lookup.py`
- `scripts/check_external_catalog_replay.py`
- `scripts/render_external_catalog_report.py`
- `services/catalog_specs/import_policy.json`
- `services/catalog_specs/import_resources.py`
- `services/catalog_specs/external_sources.py`
- `services/catalog_specs/external_identity.py`
- `services/catalog_specs/external_import.py`
- `services/catalog_specs/external_persistence.py`
- `services/catalog_specs/lookup.py`
- `services/catalog_specs/coverage.py`
- `services/catalog_specs/normalization.py`
- `services/requirements-dev.txt`
- `services/tests/test_external_catalog.py`
- `api-catalogo/database.py`
- `api-catalogo/main.py`
- `api-catalogo/schemas.py`
- `api-catalogo/services.py`
- `api-catalogo/tests/test_external_lookup.py`
- `api-orcamentos/catalog_client.py`
- `api-orcamentos/ai_context.py`
- `api-orcamentos/tests/test_external_resolver.py`

Os JSONs/JSONL extensos e os diretórios de snapshots são artefatos locais ignorados pelo Git. O banco local permanece disponível para inspeção. O DOCX preexistente em `docs/demo/` foi preservado.
