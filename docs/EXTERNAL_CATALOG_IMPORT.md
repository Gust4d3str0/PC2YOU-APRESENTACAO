# Importação técnica externa

O fluxo é snapshot → dry-run → revisão do relatório → staging → promoção explícita.
As APIs só consultam MongoDB; não importam snapshots, acessam GitHub ou usam Gemini
para resolver identidade. Os scripts nunca carregam `.env` implicitamente.

## Instalação e versões

PowerShell na raiz do projeto:

```powershell
.venv/Scripts/python.exe -m pip install -r scripts/requirements-external-catalog.txt
.venv/Scripts/python.exe scripts/fetch_external_catalog_snapshot.py --source buildcores --commit e4838129c57b26d4f0711871d5ae68f3a9c848a9 --output external-data/buildcores
.venv/Scripts/python.exe scripts/fetch_external_catalog_snapshot.py --source pc_part_dataset --commit c52a04ca9465c83997ed335f7767b09a2005dd26 --output external-data/pc_part_dataset
```

O destino do download deve estar ausente: snapshots são imutáveis. Para uma versão nova,
use outro diretório e informe `--snapshot`. Downloads são limitados a 128 MiB compactados,
256 MiB de arquivos selecionados e 24 MiB por arquivo. Nunca são extraídos scripts,
executáveis ou symlinks. Registros têm limite de 512 KiB; a leitura é limitada a 60.000
registros por importação. Schemas com referências remotas são rejeitados.
O planner verifica o uso de memória a cada 100 registros e interrompe ao ultrapassar
1 GiB de RSS; reduza `--category`/`--limit` nesse caso. Os relatórios são escritos em
stream para evitar uma segunda cópia completa do JSON em memória.

## Política de identidade e confiança

`services/catalog_specs/import_policy.json` contém categorias, limites e prioridade:
catálogo auditado → BuildCores → Mercado Livre validado → PC Part Dataset → parser
determinístico. `--policy arquivo.json` registra uma configuração de prioridade alternativa.
A execução combinada segue essa ordem para os campos ainda ausentes. Importadores
individuais processam uma fonte por vez; a sequência deve seguir a mesma prioridade.
Reordenar fontes não autoriza sobrescrever valores preenchidos. O catálogo existente
sempre prevalece, inclusive se uma fonte posterior for prioritária. Divergências
quarentenam o candidato inteiro; nenhuma fonte resolve conflitos por votação.

As identidades usam categoria, marca, escopo, modelo exato, IDs externos, MPN e
discriminadores como capacidade, VRAM, DDR, velocidade, quantidade de módulos e CL.
Sufixos de CPU/GPU permanecem na identidade. MPN conflitante e identidade ambígua
impedem a promoção. UUID externo nunca se torna o ID interno: novos IDs são hashes da
identidade canônica. CPUs usam escopo de modelo; famílias genéricas e SKUs físicos
permanecem separados. Dimensões de GPU só entram em SKU.

Um SKU novo do PC Part Dataset, sem MPN, é mantido em conflito se já há peças da
mesma marca e classe de hardware (GPU/chip/VRAM, PSU/potência, SSD/capacidade ou
placa-mãe/chipset/DDR). Isso evita que diferenças de grafia criem uma segunda cópia
de um SKU do BuildCores. O candidato continua disponível para revisão; nomes exatos
podem confirmar/enriquecer identidades existentes. A contagem de conflitos inclui
essas ambiguidades preventivas, além de divergências reais de especificações.

Limitações deliberadas: PC Part Dataset não tem ID estável por registro; usamos hash
dos fatos originais, excluindo preço. Não contém socket de CPU nem confirmação DIMM;
esses campos não são inferidos. Placas sem DDR explícito são rejeitadas. Não se deduz
fonte recomendada a partir de TDP de GPU. Datas inexistentes são rejeitadas quando
`--newer-than` é informado; ano isolado é comparado conservadoramente a 1º de janeiro.

## Validação local

Sem flags de gravação, os importadores apenas leem dados locais e escrevem relatórios.
`--apply` grava candidatos, com status seguro ainda `pending`; `--promote` exige o
relatório revisado. O digest vincula revisão a commit, filtros, política, identidades,
campos e conflitos, ignorando apenas horários. Alterações exigem novo dry-run.

```powershell
.venv/Scripts/python.exe scripts/import_buildcores_catalog.py --dry-run
.venv/Scripts/python.exe scripts/import_buildcores_catalog.py --apply
.venv/Scripts/python.exe scripts/import_buildcores_catalog.py --apply --promote --review-plan reports/buildcores-import-plan.json
.venv/Scripts/python.exe scripts/import_pc_part_dataset.py --jsonl reports/external-catalog-local.jsonl --category cpu --category gpu --limit 3000 --dry-run
.venv/Scripts/python.exe scripts/import_pc_part_dataset.py --category cpu --newer-than 2024-01-01 --dry-run --output reports/pc-recent-plan.json
```

A promoção JSONL produz outro arquivo (`reports/external-catalog-local.jsonl`), sem
modificar `demo-data/components.jsonl`. Não use o mesmo destino como entrada. Para
promover a segunda fonte, forneça outra saída com `--local-output`.

Com um MongoDB local já disponível, a validação completa reproduz planejamento,
staging, promoção, cobertura, 20 requisições reais da API e 1.000 consultas de benchmark:

```powershell
.venv/Scripts/python.exe scripts/validate_external_catalog.py --mongo-uri mongodb://127.0.0.1:27219 --db pc2you_external_catalog_validation_release
.venv/Scripts/python.exe scripts/audit_catalog_coverage.py --jsonl reports/external-catalog-local.jsonl --output reports/external-coverage-audited.json
.venv/Scripts/python.exe scripts/benchmark_catalog_lookup.py --jsonl reports/external-catalog-local.jsonl --iterations 1000 --output reports/external-lookup-memory-benchmark.json
```

O validador recusa hosts não locais e nomes de banco fora de `pc2you_external_catalog_*`.
O provedor de texto é um double explícito; catálogo, MongoDB, engine e rota FastAPI
são reais. PCs incompletos devem continuar parciais, e PCs incompatíveis devem acusar
incompatibilidade. Aprovação de teste não significa sete regras completas em todos os PCs.

## MongoDB Atlas — comandos para execução separada pelo responsável

Nenhum destes comandos de Atlas foi executado durante o desenvolvimento.
Configure a URI no ambiente de forma privada. O banco é sempre explícito.
Use a mesma seleção de categorias e filtros nas três etapas.

```powershell
$env:MONGO_URI = '<URI Atlas fornecida pelo responsável>'
$atlasDb = 'orcapc_catalog'

# Leitura de Atlas; sem índices, migração, staging ou promoção.
.venv/Scripts/python.exe scripts/import_buildcores_catalog.py --mongo --db $atlasDb --dry-run --output reports/buildcores-atlas-reviewed.json

# Revise candidates, conflitos, identidade, origem/licença e campos no JSON acima.
# Grava staging; components ainda não recebe as peças importadas.
.venv/Scripts/python.exe scripts/import_buildcores_catalog.py --mongo --db $atlasDb --apply --output reports/buildcores-atlas-staged.json

# Promoção explicitamente autorizada, vinculada ao dry-run revisado.
.venv/Scripts/python.exe scripts/import_buildcores_catalog.py --mongo --db $atlasDb --apply --promote --review-plan reports/buildcores-atlas-reviewed.json --output reports/buildcores-atlas-applied.json

# Só depois da primeira fonte: repetir revisão e staging para a segunda.
.venv/Scripts/python.exe scripts/import_pc_part_dataset.py --mongo --db $atlasDb --dry-run --output reports/pc-part-atlas-reviewed.json
.venv/Scripts/python.exe scripts/import_pc_part_dataset.py --mongo --db $atlasDb --apply --output reports/pc-part-atlas-staged.json
.venv/Scripts/python.exe scripts/import_pc_part_dataset.py --mongo --db $atlasDb --apply --promote --review-plan reports/pc-part-atlas-reviewed.json --output reports/pc-part-atlas-applied.json

.venv/Scripts/python.exe scripts/audit_catalog_coverage.py --mongo --db $atlasDb --output reports/atlas-coverage-after.json
```

`--apply` cria índices de importação. A promoção faz uma migração aditiva de chaves
de busca nos registros existentes e usa `$setOnInsert` para novos documentos.
Atualizações de specs usam compare-and-set: identidade e seções originais entram
no filtro; somente folhas ausentes são preenchidas. Alterações concorrentes bloqueiam
a atualização e ficam em `promotion_result`, exigindo novo planejamento. Não existem
deletes nem `replaceOne`. Índices únicos protegem IDs internos, identidade normalizada,
IDs externos e IDs de candidatos/jobs. Candidatos rejeitados manualmente não são
promovidos por uma repetição do job.

`pending`, `accepted`, `merged`, `rejected` e `conflict` ficam em
`catalog_import_candidates`. O relatório mostra a classificação planejada; o banco
mostra o estado da promoção. Proveniência usa a convenção existente `section__field`,
com `field` contendo o caminho pontuado e confirmações preservando todas as fontes.

## Busca e implantação

`GET /components/resolve?category=cpu&q=Ryzen%207%205700X` usa igualdade em
`(category, lookup_keys)` e limita candidatos a 32. Ambiguidades não são resolvidas
por truncamento. Normalização também alimenta índices por nome, marca, modelo e MPN;
IDs externos têm índices próprios. O resolver usa aliases/MPNs explícitos e nomes
canônicos; nunca remove sufixos, capacidades ou termos adicionais desconhecidos.

Antes de usar a nova rota sobre um banco antigo, promova um plano revisado para
popular as chaves de busca. Não há backfill implícito em requisições. A API de catálogo
deve ser atualizada junto da API de orçamentos; o cliente de análise não faz fallback
para busca por regex nem varredura integral quando a rota está ausente.
As opções de upgrade da análise são limitadas a 24 itens por categoria.

Relatórios extensos ficam locais em `reports/` e são ignorados pelo Git. Manifestos,
licenças, documentação e o relatório Markdown de entrega permanecem versionáveis.
