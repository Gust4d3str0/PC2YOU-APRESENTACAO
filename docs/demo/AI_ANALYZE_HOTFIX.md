# Hotfix /ai/analyze-pc — 05/11/2026

O preset principal retornou HTTP 200 com sete componentes do catálogo, `compatibility.valid=true`, `status=compatible`, sete regras verificadas e nenhuma regra pendente. A interface apresenta esse status como “Compatível (verificado pelas regras do sistema)”.

## Alteração

A busca anterior usava `q` literal no catálogo, seguida de igualdade quase exata. A consulta podia excluir a peça antes da comparação; a normalização não removia acentos e só retirava alguns prefixos. Agora nomes também consultam a categoria e comparam uma identidade normalizada única. Reutilizam-se apenas funções puras de normalização e aliases de marca do Product Matcher. Não há matching por IA, fuzzy score ou novo contrato.

Minúsculas, acentos, pontuação, espaços, unidades com espaços e posição da marca são normalizados. Fabricantes diferentes, sufixos de variante, capacidades diferentes, nomes parciais e múltiplas identidades continuam sem specs atribuídas. IDs diretos e RAM/kit-ram continuam suportados.

Os textos repetidos são removidos depois da validação, preservando a primeira redação. A interface não repete em “Alertas” uma mensagem já exibida em compatibilidade. As regras, a redução de confiança por dados ausentes e a rejeição de respostas inventadas permanecem ativas.

## Dados do cenário principal

| Componente existente | Dados usados |
| --- | --- |
| `ryzen-5-5600` | CPU: AM4, 6 cores, 12 threads, TDP 65 W |
| `b550m-am4-ddr4` | Placa-mãe: AM4, DDR4, 4 slots, Micro-ATX; capacidade máxima 128 GB completada |
| `ram-16gb-ddr4` | RAM: 16 GB DDR4, 3200 MHz |
| `rtx-3060` | GPU: 12 GB GDDR6, comprimento 200 mm, fonte mínima 550 W |
| `ssd-nvme-1tb` | Armazenamento: Kingston NV3, 1 TB, NVMe PCIe 4.0 |
| `fonte-650w` | Fonte: potência 650 W |
| `gabinete-atx` | Gabinete: ATX/Micro-ATX/Mini-ITX, GPU até 380 mm |

O único campo acrescentado foi `b550m-am4-ddr4.technical_specs.max_memory_gb=128`. A origem é o mesmo ID em `scripts/ai_upgrade_demo.py`, linha 35. É uma referência técnica de demonstração já existente no repositório, não uma nova confirmação externa de SKU comercial. Nenhum outro campo foi copiado desse fixture (ele possui diferenças de formato em relação ao catálogo).

O backfill foi aplicado ao JSONL e o seed recebeu o mesmo campo. `scripts/backfill_demo_specs.py` é dry-run por padrão, idempotente e não insere componentes nem sobrescreve valores preenchidos. A segunda execução sobre o snapshot retornou `changes: []`. Bancos persistidos precisam executar o script após o rebuild, conforme `README-DEMO.md`; o boot preserva documentos existentes.

## Antes e depois reais

[Requisições e respostas completas](ai-analyze-hotfix-evidence.json). Mesma requisição antes/depois, com variações cosméticas nas peças do preset:

```json
{
  "cpu": "Ryzen 5 5600 AMD",
  "motherboard": "GIGABYTE Placa mae B550M AM4 DDR4",
  "ram": "Fury Beast 16 GB DDR4 3200 MHz Kingston"
}
```

| POST /ai/analyze-pc | HTTP | Peças identificadas | Status | valid | Regras verificadas |
| --- | --- | --- | --- | --- | --- |
| Antes | 200 | 4/7 | partial | null | 2/7 |
| Depois | 200 | 7/7 | compatible | true | 7/7 |
| Preset principal original depois | 200 | 7/7 | compatible | true | 7/7 |

As três chamadas usaram a rota FastAPI real via TestClient e Gemini real (`gemini-3.5-flash-lite`, `cached=false`). O transporte HTTP do catálogo foi substituído pela leitura do snapshot JSONL local, reproduzindo a busca literal. O Docker estava desligado; a pilha com MongoDB/PostgreSQL persistidos não foi iniciada nem migrada nesta execução. Nenhuma fonte externa de componentes foi consultada. O fallback salvo de 04/11 continua sendo um registro histórico, explicitamente datado.

## Verificação

- `python -m pytest -q api-orcamentos/tests`: 256 passaram, incluindo 24 regressões do hotfix.
- `python -m pytest -q services/tests/test_product_matching.py services/tests/test_matcher.py services/tests/test_demo_explain.py`: 142 passaram.
- Com `PYTHONPATH` apontando para `services`, `python -m pytest -q api-catalogo/tests/test_final_seed.py api-catalogo/tests/test_seed_identity.py api-catalogo/tests/test_pricing_refactor.py`: 183 passaram.
- Frontend: 61 testes passaram; lint e build passaram.
- `python scripts/verify-snippets.py`: os 29 trechos coincidem com os arquivos e linhas reais. Os guias foram sincronizados; o gerador preserva os trechos já publicados.

Os testes Python usaram ambiente local isolado em `.tools/hotfix-venv`, com os requirements de `api-orcamentos` e dependências adicionais de testes dos serviços. Houve avisos de depreciação existentes nas dependências.

## Arquivos alterados

- `api-orcamentos/ai_context.py`: identificação determinística.
- `services/ai/service.py` e `services/ai/presentation.py`: deduplicação na resposta.
- `api-catalogo/seed.py`, `demo-data/components.jsonl` e `scripts/backfill_demo_specs.py`: complemento técnico conhecido.
- `api-orcamentos/tests/test_ai_hotfix.py`: regressões de matching, verificação, backfill e alertas.
- `frontend/src/components/PCAnalysisResult.jsx`: evita repetir avisos entre seções.
- `frontend/src/presentation/AiSections.jsx`, `snippets.json`, `snippetGuides.json` e `scripts/build_snippets.py`: apresentação e código exibido atualizados.
- `README-DEMO.md`, este relatório e `ai-analyze-hotfix-evidence.json`: instruções e evidência.

Endpoints públicos, schemas e o motor de compatibilidade não foram alterados.
