# PC2YOU — Product Matcher (`services/product_matching/`)

Versão do algoritmo: `VERSION = 'product-match-v1.0'` (`matcher.py:8`). É **determinístico**, sem IA, sem rede e sem banco. Os "scores" são **heurísticas de evidência, não probabilidades** (docstring do módulo).

## 1. Arquitetura

| Arquivo | Papel |
|---|---|
| `normalization.py` | `normalize_text`, `normalize_brand`, `named_brands`, `normalize_store`, `capacity_values`, `capacity_label`, lista `BRANDS` |
| `matcher.py` | `features(data)`, `compare_product(product, component)`, `match_product(product, catalog)`, `CatalogMatcher`, `MatchResult` |
| `promotions.py` | adaptador Telegram: `promotion_match`, `enrich_promotion` (matcher + condições + qualidade + status) |
| `quality.py` | `price_quality`, `best_known_price`, `equivalence_key`, `catalog_offers`, `offer_state`, limites de frescor |
| `offers.py` | condições, status comercial, validadores ([TELEGRAM_FLOW.md](TELEGRAM_FLOW.md)) |
| `destinations.py` | URLs/lojas ([TELEGRAM_FLOW.md](TELEGRAM_FLOW.md)) |
| `ml_ids.py` | `extract_product_id`, `extract_item_id` ([MERCADO_LIVRE.md](MERCADO_LIVRE.md)) |
| `reporting.py` | agregações para relatórios |

Quem chama: `services/telegram_collector/repository.py` (ao salvar), `api-catalogo/commerce.py` (snapshot), `api-orcamentos/ai_upgrade_context.py` (IA v2), `api-catalogo/ml_products.py` (`evaluate_match` usa `compare_product`), scripts de auditoria/reprocessamento.

## 2. Passo a passo do algoritmo

1. **Normalização** (`normalize_text`): NFKD → ASCII minúsculo; remove URLs; mantém só `[a-z0-9.,]`; cola unidade ao número (`16 gb`→`16gb`; também tb/mhz/w); `ddr 5`→`ddr5`; `7800 x3d`→`7800x3d` (sufixos x3d/kf/ks/x/g/f/k em números de 4–5 dígitos); `micro atx/m atx`→`matx`; `mini itx`→`itx`.
2. **Features** (`features`): título (`title` ou `name`) + specs (`compatibility`, `technical_specs`, `attributes`) viram `all_text`; extrai:
   - **modelo** de GPU (`GPU` regex: `rtx|gtx|rx` + 4 dígitos + sufixo `ti super|super|ti|xtx|xt|gre`) → ex. `rtx5060ti`; de CPU (`CPU`: `ryzen N NNNN…` ou `core iN NNNN…`) → ex. `77800x3d` (a regex concatena o "7" da linha com o modelo); placa-mãe: chipsets `[abhxz]\d{3}[a-z]*`; demais: tokens tipo `nv3`, excluindo `ddrN/amN/lgaN/chipsets`.
   - **categoria**: explícita (`category`/`component_type`) ou inferida (gpu, cpu, storage, psu, motherboard, ram); `kit-ram`→`ram`.
   - **marca**: `BRANDS` (asus, gigabyte, galax, msi, zotac, sapphire, xfx, asrock, palit, pny, gainward, inno3d, biostar, amd, nvidia, intel, kingston, corsair, crucial, adata, western digital, samsung, seagate, lexar, superframe, redragon, cooler master, deepcool) + alias (`wd`, `galaxy`→galax, `asustek`, `microstar`); em GPU, **amd/nvidia/intel não contam como marca** (fabricante do chip).
   - **capacidade** (GB; 1 TB = 1024; 1000 GB é distinto), módulos (`2x8gb`), tipo (`ddr3/4/5`), frequência (`NNNNmhz`), socket (`am3/4/5`, `lgaNNNN`), potência (`NNNw` – só PSU), geração, formato (matx/atx/itx/sodimm/dimm), interface (nvme/sata/hdd).
   - **múltiplos produtos**: `len(kinds)>1`, `kit upgrade|combo|bundle`, ou >1 modelo.
3. **Conflitos** (`compare_product`) — qualquer um zera a possibilidade de match (score fixo **0.20**): `category_conflict`, `multiple_products`, `variant_conflict` (modelo diferente), `brand_conflict`, `ram_module_conflict`, `ram_module_kind_conflict`, `capacity_conflict`, `memory_type_conflict`, `frequency_conflict`, `socket_conflict`, `power_conflict` (só PSU), `format_conflict`, `storage_conflict` (interface), `generation_conflict`. Só compara um atributo quando **ambos** os lados o possuem; se iguais, vira "sinal".
4. **Pontuação** (sem conflitos):
   - base: `0.05` se há categoria; `+0.80` se o sinal `model` bateu, senão `+0.35`.
   - pesos de sinais: brand `.08`, vram `.08`, capacity `.12`, memory_type `.10`, frequency `.04`, socket `.04`, power `.22`, format `.03`, interface `.10`, generation `.03`.
   - nome idêntico (`len>5`): `exact_name` → piso **0.90**; sem modelo em ambos e `SequenceMatcher ≥ 0.94`: `name_typo` → piso **0.70**.
   - **tetos**: componente genérico (sem modelo e sem marca) sem nome exato → **≤ 0.80**; produto sem modelo mas componente com modelo → **≤ 0.64**; componente tem marca e o produto não (exceto CPU com nome exato) → **≤ 0.80**; RAM sem (capacidade **e** tipo) → **≤ 0.64**; storage sem (capacidade **e** interface) → **≤ 0.64**; PSU sem potência → **≤ 0.64**. Máximo **0.99**.
5. **Níveis** (`matcher.py:9-10,154`): **High `score ≥ 0.85`**, **Medium `≥ 0.65`**, **Low `< 0.65`**. `matched = score ≥ MEDIUM`; `component_id` só é preenchido se `matched`.
6. **Escolha no catálogo** (`match_product`): avalia todos os componentes (ou só o `component_id` explícito); se **mais de um** passa de Medium → `variant_ambiguous` (score 0.64, sem id); se 1 → resultado dele; se nenhum, devolve o diagnóstico do candidato mais próximo **sem** id.
7. **Uso do nível pelo sistema** (valores reais):
   - **High**: único nível que torna uma oferta `verified` (`quality.price_quality`: fonte telegram/mercado_livre/manual, match matched, sem conflitos, `confidence ≥ HIGH`, frescor, disponibilidade, estado ativo, preço > 0), entra em `commerce.build_snapshot` (`match_level != 'high'` → descartada), no histórico `product_price_history`, e na IA v2.
   - **Medium** (0.65–0.84): registrado, **não publicado** nem usado como preço; `ml_products.evaluate_match` exige `result.matched and confidence ≥ HIGH` (ou variante de marca) para enriquecer.
   - **Low**: ignorado.

## 3. Exemplos reais (executados com o catálogo `seed.py`, 121 componentes)

| Texto original | Normalizado | Features | Melhores candidatos | Resultado |
|---|---|---|---|---|
| `Placa de Vídeo RTX 5060 Ti 8GB Gigabyte Windforce OC` | `placa de video rtx 5060 ti 8gb gigabyte windforce oc` | modelo `rtx5060ti`, marca `gigabyte`, cap. `8`, cat. gpu | `rtx-5060-ti-8gb` **0.93 high** (model+vram+category); demais ≤ 0.20 por `category/variant/brand_conflict` | **match** `rtx-5060-ti-8gb`, 0.93, High |
| `Processador AMD Ryzen 7 7800X3D 4.2GHz AM5` | `processador amd ryzen 7 7800x3d 4.2ghz am5` | modelo `77800x3d`, marca `amd`, socket `am5` | `ryzen-7-7800x3d` **0.97 high** (model, brand, socket, category) | **match**, 0.97, High |
| `Placa de vídeo RTX 5060 Ti` (sem VRAM) — **ambíguo** | `…rtx 5060 ti` | modelo `rtx5060ti`, sem capacidade | candidatos `rtx-5060-ti-8gb` **e** `rtx-5060-ti-16gb` | **sem match**: `variant_ambiguous`, 0.64, Low |
| `Kit Upgrade Ryzen 5 5600 + B550M` | `kit upgrade ryzen 5 5600 b550m` | `multiple=True` | todos com `multiple_products` | **sem match**: 0.20, conflito `multiple_products` |
| `Placa de video RTX 5060` | — | modelo `rtx5060`, sem marca/VRAM | `rtx-5060-8gb` **0.85 high** (exatamente no limiar) | match High (borda) |
| `Memória Kingston Fury Beast 16GB DDR5 5600MHz` | — | marca kingston, 16 GB, ddr5, 5600 MHz | `ram-16gb-ddr5` **0.74 medium** (conta: 0.05 categoria + 0.35 sem sinal de modelo + 0.08 marca + 0.12 capacidade + 0.10 tipo + 0.04 frequência = 0.74) | **Medium** (não publicado) |
| `Memória RAM DDR5 16GB 6000MHz` | — | 16 GB, ddr5, 6000 MHz | catálogo tem 5600 MHz | **sem match**: `frequency_conflict` (0.20) |
| `Memória RAM 16GB DDR5` | — | 16 GB, ddr5 | `ram-16gb-ddr5` 0.62 | Low (sinais fracos, sem marca/frequência) |
| Telegram real-like: `Processador Ryzen 7 7800X3D … KaBuM` (sem "AMD") | `cpu\|77800x3d\|\|\|` | sem marca no texto | `ryzen-7-7800x3d` **0.80 medium** (teto "componente tem marca e o produto não") | Medium → **não** vira oferta verificada; com "AMD" no texto sobe para **0.93 High** |

Dado de campo (relatório `reports/post-backfill-quality-audit.json`, 2026-11-01, **654** promoções auditadas, 121 componentes): distribuição recalculada **low 541 / high 110 / medium 3**; `dangling_component_ids: 0`; histórico: 79 observações, todas `verified` e High.

## 4. Pontos fortes e limites (para explicar)
- Conservador: preferir não casar a casar errado (`variant_ambiguous`, tetos por falta de modelo).
- Limites: regex específicas de GPU RTX/GTX/RX e CPU Ryzen/Core; categorias sem modelo (RAM/SSD/PSU) dependem de capacidade/tipo/potência; marca ausente rebaixa para Medium (efeito observado em CPUs); 6000 MHz vs 5600 MHz gera conflito mesmo sendo a "mesma família".
- O catálogo é a fonte de identidade: componente ausente do seed nunca é casado.
