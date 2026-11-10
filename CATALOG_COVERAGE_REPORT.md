# PC2YOU — cobertura técnica do catálogo

Auditoria de 09/11/2026. Valores ausentes não foram inventados.

Catálogo local: **121 → 150 componentes**, com **29 novas identidades reais**.

Backfill aplicado: **32 campos em 22 componentes existentes**. Todos os campos originais dos 121 documentos foram preservados, inclusive preços, histórico, imagens e enriquecimento.

O seed inicial continua usando `$setOnInsert`; o script de manutenção usa `$set` condicionado ao valor lido, sem upsert. O Atlas de produção não foi consultado nem alterado: não há MONGO_URI de produção configurada neste ambiente.

## Cobertura antes e depois

| Categoria | Antes | Depois |
|---|---:|---:|
| cpu | 22/36 | 37/40 |
| motherboard | 3/14 | 14/27 |
| ram | 13/13 | 18/18 |
| gpu | 20/26 | 23/29 |
| psu | 7/7 | 10/10 |
| case | 6/6 | 6/6 |
| storage | 10/10 | 11/11 |

RAM inclui `kit-ram`. `modules` é informado separadamente: 6/13 → 11/18 conhecidos. A regra `ram_slots` agora exige a contagem real; não presume um ou dois módulos. Os 9 coolers foram inventariados, mas estão fora das sete categorias/regras solicitadas.

**Completude significa presença e formato válidos dos campos necessários. Não é certificação independente de cada dado legado.** Os dados antigos foram preservados. As dimensões de GPUs genéricas do seed continuam sendo dados legados; não devem ser tratadas como dimensões de qualquer placa de parceiro. O novo mapper impede transferir dimensões e requisitos de energia de um SKU do Mercado Livre para uma família genérica. Também impede copiar slots ou capacidade máxima de um SKU para uma família de placa-mãe.

## Campos obrigatórios por categoria

| Categoria | Campo canônico | Antes | Depois |
|---|---|---:|---:|
| cpu | `compatibility.socket` | 36/36 | 40/40 |
| cpu | `technical_specs.cores` | 36/36 | 40/40 |
| cpu | `technical_specs.threads` | 36/36 | 40/40 |
| cpu | `technical_specs.tdp_watts` | 22/36 | 37/40 |
| motherboard | `compatibility.socket` | 14/14 | 27/27 |
| motherboard | `compatibility.memory_type` | 14/14 | 27/27 |
| motherboard | `technical_specs.memory_slots` | 8/14 | 17/27 |
| motherboard | `technical_specs.max_memory_gb` | 3/14 | 18/27 |
| motherboard | `compatibility.form_factor` | 14/14 | 26/27 |
| ram | `technical_specs.capacity` | 13/13 | 18/18 |
| ram | `compatibility.memory_type` | 13/13 | 18/18 |
| ram | `technical_specs.speed` | 13/13 | 18/18 |
| gpu | `technical_specs.memory` | 26/26 | 29/29 |
| gpu | `technical_specs.length_mm` | 20/26 | 23/29 |
| gpu | `compatibility.min_psu_watts` | 20/26 | 23/29 |
| psu | `technical_specs.wattage` | 7/7 | 10/10 |
| case | `compatibility.supported_form_factors` | 6/6 | 6/6 |
| case | `compatibility.max_gpu_length_mm` | 6/6 | 6/6 |
| storage | `technical_specs.capacity` | 10/10 | 11/11 |
| storage | `technical_specs.interface` | 10/10 | 11/11 |

GPU usa `min_psu_watts`: consumo isolado não foi convertido em potência recomendada de fonte.

## Participação nas sete regras

| Regra | Antes, por categoria | Depois, por categoria |
|---|---|---|
| `cpu_socket` | cpu: 36/36; motherboard: 14/14 | cpu: 40/40; motherboard: 27/27 |
| `ram_type` | motherboard: 14/14; ram: 13/13 | motherboard: 27/27; ram: 18/18 |
| `ram_slots` | motherboard: 8/14; ram: 6/13 | motherboard: 17/27; ram: 11/18 |
| `ram_capacity` | motherboard: 3/14; ram: 13/13 | motherboard: 18/27; ram: 18/18 |
| `gpu_power` | gpu: 20/26; psu: 7/7 | gpu: 23/29; psu: 10/10 |
| `board_case` | motherboard: 14/14; case: 6/6 | motherboard: 26/27; case: 6/6 |
| `gpu_case` | gpu: 20/26; case: 6/6 | gpu: 23/29; case: 6/6 |

## Famílias prioritárias e limites restantes

Todas as 16 CPUs prioritárias solicitadas estão presentes e completas. Foram adicionadas Ryzen 5 3600, Ryzen 5 5600X, Ryzen 7 5800X e Core i5-13600K.

GPU: RTX 2060 recebeu um SKU completo real (Gigabyte GV-N2060D6-6GD rev. 2.0). RTX 3060 Ti e RTX 4080 **ainda não receberam um registro completo**: os retornos oficiais consultados não forneceram identidade/dimensões/requisito de fonte suficientes sem conflitos. RTX 4080 Super é outra identidade. Os outros modelos prioritários já estavam no seed e foram preservados. As seis famílias novas de GPUs da expansão anterior continuam incompletas; foram adicionados SKUs próprios completos Palit RTX 5050 Dual e Gigabyte RTX 5060 Ti WINDFORCE MAX OC 8GB, sem emprestar seus tamanhos às famílias.

Placas-mãe: novos SKUs completos de A520, B450, B550, A620, B650, H610 e B760; B660 e Asus TUF X670E-PLUS existentes receberam limite de RAM de fonte estruturada. Os SKUs novos X570 AORUS ULTRA, X670 AORUS ELITE AX, MSI PRO Z690-A DDR4 e Z790 AORUS ELITE AX ainda têm campos ausentes. Não foi deduzido número de slots a partir de chipset, foto ou quantidade de canais. `SUPPORTED_RAM_MEMORY_MODULES` não foi convertido em slots, pois sua semântica não é inequívoca.

RAM: SKUs DIMM de 8GB DDR4 2666/3200, 16GB DDR4 3200, 32GB DDR4 3200 e 16GB DDR5 5600, com número de módulos explícito; kits DDR5 de 32GB já existentes. Fonte: Corsair CV450, CX500 e Thermaltake SMART RGB 600W completam as potências prioritárias. Armazenamento: Samsung 970 EVO Plus 1TB PCIe 3.0 complementa SATA e PCIe 4.0 existentes.

**A meta não está concluída para todo componente comercial possível.** Uma família como B760M sem DDR4/DDR5 continua ambígua; um SKU desconhecido não recebe specs do primeiro modelo parecido.

## Normalização, origem e rejeições

Normalização única: `services/catalog_specs/normalization.py`; mapeamento por categoria: `mapper.py`. Ordem de propostas: atributos estruturados oficiais → campo estruturado já existente → referência técnica do repositório com identidade coincidente → parser de notação explícita de módulos. Conflitos entre propostas deixam o campo ausente. Nenhum título de anúncio alimenta socket, TDP, slots, potência ou dimensões.

Os atributos utilizados estão nos arquivos de evidência. Cada valor inserido guarda `spec_provenance`, o atributo original, valor bruto e PRODUCT_ID quando aplicável. `api-catalogo/catalog_spec_sources.json` contém os produtos oficiais revisados; `catalog_coverage_v2.json` é reproduzível, sem preços ou benchmarks fabricados.

Exclusões explícitas: TDP 105W do produto ML do Ryzen 5 9600X não identifica o modo padrão; TDP 65W e 28 threads do produto ML do i5-14600KF contradizem a referência oficial. Esses valores não foram aproveitados. [AMD 9600X](https://shop-us-en.amd.com/amd-ryzen-5-9600x-processor/), [Intel 14600KF](https://www.intel.com/content/www/us/en/products/sku/236778/intel-core-i5-processor-14600kf-24m-cache-up-to-5-30-ghz/specifications.html).

Também foram rejeitados: sockets múltiplos ou sem prefixo inequívoco, DDR4/DDR5 combinados, dimensões com eixos contraditórios, combos, módulos incompatíveis com a capacidade total e domínios de produto incorretos.

## Campos preenchidos em documentos existentes

| Componente | Campo | Valor inserido | Origem |
|---|---|---|---|
| `intel-i5-12400f` | `technical_specs.socket` | `"LGA1700"` | catalog.compatibility.socket |
| `ryzen-5-5600` | `technical_specs.socket` | `"AM4"` | catalog.compatibility.socket |
| `ryzen-7-5700x` | `technical_specs.socket` | `"AM4"` | catalog.compatibility.socket |
| `b550-am4-ddr4` | `technical_specs.socket` | `"AM4"` | catalog.compatibility.socket |
| `b550-am4-ddr4` | `technical_specs.memory_type` | `"DDR4"` | catalog.compatibility.memory_type |
| `b550m-am4-ddr4` | `technical_specs.socket` | `"AM4"` | catalog.compatibility.socket |
| `b550m-am4-ddr4` | `technical_specs.memory_type` | `"DDR4"` | catalog.compatibility.memory_type |
| `x570-am4-ddr4` | `technical_specs.socket` | `"AM4"` | catalog.compatibility.socket |
| `x570-am4-ddr4` | `technical_specs.memory_type` | `"DDR4"` | catalog.compatibility.memory_type |
| `b650-am5-ddr5` | `technical_specs.socket` | `"AM5"` | catalog.compatibility.socket |
| `b650-am5-ddr5` | `technical_specs.memory_type` | `"DDR5"` | catalog.compatibility.memory_type |
| `x670e-am5-ddr5` | `technical_specs.socket` | `"AM5"` | catalog.compatibility.socket |
| `x670e-am5-ddr5` | `technical_specs.memory_type` | `"DDR5"` | catalog.compatibility.memory_type |
| `x670e-am5-ddr5` | `technical_specs.max_memory_gb` | `128` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB22651390) |
| `b660-lga1700-ddr4` | `technical_specs.socket` | `"LGA1700"` | catalog.compatibility.socket |
| `b660-lga1700-ddr4` | `technical_specs.memory_type` | `"DDR4"` | catalog.compatibility.memory_type |
| `b660-lga1700-ddr4` | `technical_specs.max_memory_gb` | `128` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB22650260) |
| `gabinete-micro-atx` | `technical_specs.supported_form_factors` | `["Micro-ATX", "Mini-ITX"]` | catalog.compatibility.supported_form_factors |
| `gabinete-micro-atx` | `technical_specs.max_gpu_length_mm` | `320` | catalog.compatibility.max_gpu_length_mm |
| `gabinete-compacto-itx` | `technical_specs.supported_form_factors` | `["Mini-ITX"]` | catalog.compatibility.supported_form_factors |
| `gabinete-compacto-itx` | `technical_specs.max_gpu_length_mm` | `270` | catalog.compatibility.max_gpu_length_mm |
| `ryzen-5-5500x3d` | `technical_specs.tdp_watts` | `105` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB52967964) |
| `ryzen-5-8400f` | `technical_specs.tdp_watts` | `65` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB53500536) |
| `ryzen-7-5800x3d` | `technical_specs.tdp_watts` | `105` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB75448717) |
| `ryzen-5-8600g` | `technical_specs.tdp_watts` | `65` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB32470567) |
| `ryzen-7-5700` | `technical_specs.tdp_watts` | `65` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB31054937) |
| `ryzen-7-5800xt` | `technical_specs.tdp_watts` | `105` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB38775722) |
| `ryzen-7-7700` | `technical_specs.tdp_watts` | `65` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB69750845) |
| `ryzen-9-7900` | `technical_specs.tdp_watts` | `65` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB61075833) |
| `ryzen-7-9700x` | `technical_specs.tdp_watts` | `65` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB80105267) |
| `ryzen-9-5900xt` | `technical_specs.tdp_watts` | `105` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB38775549) |
| `intel-i7-14700kf` | `technical_specs.tdp_watts` | `125` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB28111906) |

## Valores técnicos dos novos componentes e respectivas fontes

| ID | Campo | Valor | Origem |
|---|---|---|---|
| `ryzen-5-3600` | `compatibility.socket` | `"AM4"` | [mercado_livre.COMPATIBLE_SOCKETS](https://api.mercadolibre.com/products/MLB24968544) |
| `ryzen-5-3600` | `technical_specs.cores` | `6` | [mercado_livre.CPU_CORES_NUMBER](https://api.mercadolibre.com/products/MLB24968544) |
| `ryzen-5-3600` | `technical_specs.threads` | `12` | [mercado_livre.CPU_THREADS_NUMBER](https://api.mercadolibre.com/products/MLB24968544) |
| `ryzen-5-3600` | `technical_specs.tdp_watts` | `65` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB24968544) |
| `ryzen-5-3600` | `technical_specs.socket` | `"AM4"` | [mercado_livre.COMPATIBLE_SOCKETS](https://api.mercadolibre.com/products/MLB24968544) |
| `ryzen-5-5600x` | `compatibility.socket` | `"AM4"` | [mercado_livre.COMPATIBLE_SOCKETS](https://api.mercadolibre.com/products/MLB46582763) |
| `ryzen-5-5600x` | `technical_specs.cores` | `6` | [mercado_livre.CPU_CORES_NUMBER](https://api.mercadolibre.com/products/MLB46582763) |
| `ryzen-5-5600x` | `technical_specs.threads` | `12` | [mercado_livre.CPU_THREADS_NUMBER](https://api.mercadolibre.com/products/MLB46582763) |
| `ryzen-5-5600x` | `technical_specs.tdp_watts` | `65` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB46582763) |
| `ryzen-5-5600x` | `technical_specs.socket` | `"AM4"` | [mercado_livre.COMPATIBLE_SOCKETS](https://api.mercadolibre.com/products/MLB46582763) |
| `ryzen-7-5800x` | `compatibility.socket` | `"AM4"` | [mercado_livre.COMPATIBLE_SOCKETS](https://api.mercadolibre.com/products/MLB16328465) |
| `ryzen-7-5800x` | `technical_specs.cores` | `8` | [mercado_livre.CPU_CORES_NUMBER](https://api.mercadolibre.com/products/MLB16328465) |
| `ryzen-7-5800x` | `technical_specs.threads` | `16` | [mercado_livre.CPU_THREADS_NUMBER](https://api.mercadolibre.com/products/MLB16328465) |
| `ryzen-7-5800x` | `technical_specs.tdp_watts` | `105` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB16328465) |
| `ryzen-7-5800x` | `technical_specs.socket` | `"AM4"` | [mercado_livre.COMPATIBLE_SOCKETS](https://api.mercadolibre.com/products/MLB16328465) |
| `intel-i5-13600k` | `compatibility.socket` | `"LGA1700"` | [mercado_livre.COMPATIBLE_SOCKETS](https://api.mercadolibre.com/products/MLB19917323) |
| `intel-i5-13600k` | `technical_specs.cores` | `14` | [mercado_livre.CPU_CORES_NUMBER](https://api.mercadolibre.com/products/MLB19917323) |
| `intel-i5-13600k` | `technical_specs.threads` | `20` | [mercado_livre.CPU_THREADS_NUMBER](https://api.mercadolibre.com/products/MLB19917323) |
| `intel-i5-13600k` | `technical_specs.tdp_watts` | `125` | [mercado_livre.TDP](https://api.mercadolibre.com/products/MLB19917323) |
| `intel-i5-13600k` | `technical_specs.socket` | `"LGA1700"` | [mercado_livre.COMPATIBLE_SOCKETS](https://api.mercadolibre.com/products/MLB19917323) |
| `gigabyte-b550m-k` | `compatibility.socket` | `"AM4"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB58338391) |
| `gigabyte-b550m-k` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB58338391) |
| `gigabyte-b550m-k` | `technical_specs.memory_slots` | `4` | [mercado_livre.RAM_MEMORY_SLOTS](https://api.mercadolibre.com/products/MLB58338391) |
| `gigabyte-b550m-k` | `technical_specs.max_memory_gb` | `128` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB58338391) |
| `gigabyte-b550m-k` | `compatibility.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB58338391) |
| `gigabyte-b550m-k` | `technical_specs.socket` | `"AM4"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB58338391) |
| `gigabyte-b550m-k` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB58338391) |
| `gigabyte-b550m-k` | `technical_specs.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB58338391) |
| `asrock-b550-pg-velocita` | `compatibility.socket` | `"AM4"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB22582329) |
| `asrock-b550-pg-velocita` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB22582329) |
| `asrock-b550-pg-velocita` | `technical_specs.memory_slots` | `4` | [mercado_livre.RAM_MEMORY_SLOTS](https://api.mercadolibre.com/products/MLB22582329) |
| `asrock-b550-pg-velocita` | `technical_specs.max_memory_gb` | `128` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB22582329) |
| `asrock-b550-pg-velocita` | `compatibility.form_factor` | `"ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB22582329) |
| `asrock-b550-pg-velocita` | `technical_specs.socket` | `"AM4"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB22582329) |
| `asrock-b550-pg-velocita` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB22582329) |
| `asrock-b550-pg-velocita` | `technical_specs.form_factor` | `"ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB22582329) |
| `gigabyte-b650-gaming-x-ax-v2` | `compatibility.socket` | `"AM5"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB36866100) |
| `gigabyte-b650-gaming-x-ax-v2` | `compatibility.memory_type` | `"DDR5"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB36866100) |
| `gigabyte-b650-gaming-x-ax-v2` | `technical_specs.memory_slots` | `4` | [mercado_livre.RAM_MEMORY_SLOTS](https://api.mercadolibre.com/products/MLB36866100) |
| `gigabyte-b650-gaming-x-ax-v2` | `technical_specs.max_memory_gb` | `256` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB36866100) |
| `gigabyte-b650-gaming-x-ax-v2` | `compatibility.form_factor` | `"ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB36866100) |
| `gigabyte-b650-gaming-x-ax-v2` | `technical_specs.socket` | `"AM5"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB36866100) |
| `gigabyte-b650-gaming-x-ax-v2` | `technical_specs.memory_type` | `"DDR5"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB36866100) |
| `gigabyte-b650-gaming-x-ax-v2` | `technical_specs.form_factor` | `"ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB36866100) |
| `asrock-a520m-hdv` | `compatibility.socket` | `"AM4"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB48781530) |
| `asrock-a520m-hdv` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB48781530) |
| `asrock-a520m-hdv` | `technical_specs.max_memory_gb` | `64` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB48781530) |
| `asrock-a520m-hdv` | `compatibility.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB48781530) |
| `asrock-a520m-hdv` | `technical_specs.memory_slots` | `2` | [mercado_livre.RAM_MEMORY_SLOTS](https://api.mercadolibre.com/products/MLB22760100) |
| `asrock-a520m-hdv` | `technical_specs.socket` | `"AM4"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB48781530) |
| `asrock-a520m-hdv` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB48781530) |
| `asrock-a520m-hdv` | `technical_specs.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB48781530) |
| `asrock-a620m-c` | `compatibility.socket` | `"AM5"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB50137583) |
| `asrock-a620m-c` | `compatibility.memory_type` | `"DDR5"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB50137583) |
| `asrock-a620m-c` | `technical_specs.memory_slots` | `4` | [mercado_livre.RAM_MEMORY_SLOTS](https://api.mercadolibre.com/products/MLB50137583) |
| `asrock-a620m-c` | `technical_specs.max_memory_gb` | `256` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB50137583) |
| `asrock-a620m-c` | `compatibility.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB50137583) |
| `asrock-a620m-c` | `technical_specs.socket` | `"AM5"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB50137583) |
| `asrock-a620m-c` | `technical_specs.memory_type` | `"DDR5"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB50137583) |
| `asrock-a620m-c` | `technical_specs.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB50137583) |
| `foxstar-fs-h610mb-eg` | `compatibility.socket` | `"LGA1700"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB53615178) |
| `foxstar-fs-h610mb-eg` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB53615178) |
| `foxstar-fs-h610mb-eg` | `technical_specs.memory_slots` | `2` | [mercado_livre.RAM_MEMORY_SLOTS](https://api.mercadolibre.com/products/MLB53615178) |
| `foxstar-fs-h610mb-eg` | `technical_specs.max_memory_gb` | `32` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB53615178) |
| `foxstar-fs-h610mb-eg` | `compatibility.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB53615178) |
| `foxstar-fs-h610mb-eg` | `technical_specs.socket` | `"LGA1700"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB53615178) |
| `foxstar-fs-h610mb-eg` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB53615178) |
| `foxstar-fs-h610mb-eg` | `technical_specs.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB53615178) |
| `gigabyte-b760m-k-ddr4` | `compatibility.socket` | `"LGA1700"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB35994506) |
| `gigabyte-b760m-k-ddr4` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB35994506) |
| `gigabyte-b760m-k-ddr4` | `technical_specs.memory_slots` | `2` | [mercado_livre.RAM_MEMORY_SLOTS](https://api.mercadolibre.com/products/MLB35994506) |
| `gigabyte-b760m-k-ddr4` | `technical_specs.max_memory_gb` | `64` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB35994506) |
| `gigabyte-b760m-k-ddr4` | `compatibility.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB35994506) |
| `gigabyte-b760m-k-ddr4` | `technical_specs.socket` | `"LGA1700"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB35994506) |
| `gigabyte-b760m-k-ddr4` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB35994506) |
| `gigabyte-b760m-k-ddr4` | `technical_specs.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB35994506) |
| `gigabyte-b760m-ds3h-ddr5` | `compatibility.socket` | `"LGA1700"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB29042931) |
| `gigabyte-b760m-ds3h-ddr5` | `compatibility.memory_type` | `"DDR5"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB29042931) |
| `gigabyte-b760m-ds3h-ddr5` | `technical_specs.memory_slots` | `4` | [mercado_livre.RAM_MEMORY_SLOTS](https://api.mercadolibre.com/products/MLB29042931) |
| `gigabyte-b760m-ds3h-ddr5` | `technical_specs.max_memory_gb` | `192` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB29042931) |
| `gigabyte-b760m-ds3h-ddr5` | `compatibility.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB29042931) |
| `gigabyte-b760m-ds3h-ddr5` | `technical_specs.socket` | `"LGA1700"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB29042931) |
| `gigabyte-b760m-ds3h-ddr5` | `technical_specs.memory_type` | `"DDR5"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB29042931) |
| `gigabyte-b760m-ds3h-ddr5` | `technical_specs.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB29042931) |
| `revenger-g-b450` | `compatibility.socket` | `"AM4"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB61205180) |
| `revenger-g-b450` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB61205180) |
| `revenger-g-b450` | `technical_specs.memory_slots` | `2` | [mercado_livre.RAM_MEMORY_SLOTS](https://api.mercadolibre.com/products/MLB61205180) |
| `revenger-g-b450` | `technical_specs.max_memory_gb` | `32` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB61205180) |
| `revenger-g-b450` | `compatibility.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB61205180) |
| `revenger-g-b450` | `technical_specs.socket` | `"AM4"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB61205180) |
| `revenger-g-b450` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB61205180) |
| `revenger-g-b450` | `technical_specs.form_factor` | `"Micro-ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB61205180) |
| `gigabyte-x570-aorus-ultra` | `compatibility.socket` | `"AM4"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB49582748) |
| `gigabyte-x570-aorus-ultra` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB49582748) |
| `gigabyte-x570-aorus-ultra` | `technical_specs.max_memory_gb` | `128` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB49582748) |
| `gigabyte-x570-aorus-ultra` | `compatibility.form_factor` | `"ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB49582748) |
| `gigabyte-x570-aorus-ultra` | `technical_specs.socket` | `"AM4"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB49582748) |
| `gigabyte-x570-aorus-ultra` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB49582748) |
| `gigabyte-x570-aorus-ultra` | `technical_specs.form_factor` | `"ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB49582748) |
| `gigabyte-x670-aorus-elite-ax` | `compatibility.socket` | `"AM5"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB22415604) |
| `gigabyte-x670-aorus-elite-ax` | `compatibility.memory_type` | `"DDR5"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB22415604) |
| `gigabyte-x670-aorus-elite-ax` | `technical_specs.max_memory_gb` | `128` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB22415604) |
| `gigabyte-x670-aorus-elite-ax` | `technical_specs.socket` | `"AM5"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB22415604) |
| `gigabyte-x670-aorus-elite-ax` | `technical_specs.memory_type` | `"DDR5"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB22415604) |
| `msi-pro-z690-a-ddr4` | `compatibility.socket` | `"LGA1700"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB22623610) |
| `msi-pro-z690-a-ddr4` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB22623610) |
| `msi-pro-z690-a-ddr4` | `technical_specs.max_memory_gb` | `128` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB22623610) |
| `msi-pro-z690-a-ddr4` | `compatibility.form_factor` | `"ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB22623610) |
| `msi-pro-z690-a-ddr4` | `technical_specs.socket` | `"LGA1700"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB22623610) |
| `msi-pro-z690-a-ddr4` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB22623610) |
| `msi-pro-z690-a-ddr4` | `technical_specs.form_factor` | `"ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB22623610) |
| `gigabyte-z790-aorus-elite-ax` | `compatibility.socket` | `"LGA1700"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB22694309) |
| `gigabyte-z790-aorus-elite-ax` | `compatibility.memory_type` | `"DDR5"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB22694309) |
| `gigabyte-z790-aorus-elite-ax` | `technical_specs.max_memory_gb` | `192` | [mercado_livre.MAX_SUPPORTED_RAM_MEMORY_CAPACITY](https://api.mercadolibre.com/products/MLB22694309) |
| `gigabyte-z790-aorus-elite-ax` | `compatibility.form_factor` | `"ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB22694309) |
| `gigabyte-z790-aorus-elite-ax` | `technical_specs.socket` | `"LGA1700"` | [mercado_livre.SOCKET](https://api.mercadolibre.com/products/MLB22694309) |
| `gigabyte-z790-aorus-elite-ax` | `technical_specs.memory_type` | `"DDR5"` | [mercado_livre.SUPPORTED_RAM_MEMORY_TYPE](https://api.mercadolibre.com/products/MLB22694309) |
| `gigabyte-z790-aorus-elite-ax` | `technical_specs.form_factor` | `"ATX"` | [mercado_livre.FORM_FACTOR](https://api.mercadolibre.com/products/MLB22694309) |
| `palit-rtx-5050-dual-8gb` | `technical_specs.memory` | `"8GB"` | [mercado_livre.MEMORY_SIZE](https://api.mercadolibre.com/products/MLB54179883) |
| `palit-rtx-5050-dual-8gb` | `technical_specs.length_mm` | `262.1` | [mercado_livre.LENGTH](https://api.mercadolibre.com/products/MLB54179883) |
| `palit-rtx-5050-dual-8gb` | `technical_specs.power_consumption_watts` | `130` | [mercado_livre.TOTAL_GRAPHICS_POWER](https://api.mercadolibre.com/products/MLB54179883) |
| `palit-rtx-5050-dual-8gb` | `compatibility.min_psu_watts` | `550` | [mercado_livre.POWER_REQUIREMENT](https://api.mercadolibre.com/products/MLB54179883) |
| `gigabyte-rtx-5060-ti-windforce-max-oc-8gb` | `technical_specs.memory` | `"8GB"` | [mercado_livre.MEMORY_SIZE](https://api.mercadolibre.com/products/MLB78085963) |
| `gigabyte-rtx-5060-ti-windforce-max-oc-8gb` | `technical_specs.length_mm` | `208` | [mercado_livre.LENGTH](https://api.mercadolibre.com/products/MLB78085963) |
| `gigabyte-rtx-5060-ti-windforce-max-oc-8gb` | `technical_specs.power_consumption_watts` | `180` | [mercado_livre.TOTAL_GRAPHICS_POWER](https://api.mercadolibre.com/products/MLB78085963) |
| `gigabyte-rtx-5060-ti-windforce-max-oc-8gb` | `compatibility.min_psu_watts` | `650` | [mercado_livre.POWER_REQUIREMENT](https://api.mercadolibre.com/products/MLB78085963) |
| `corsair-cv450` | `technical_specs.wattage` | `450` | [mercado_livre.POWER_OUTPUT](https://api.mercadolibre.com/products/MLB58545794) |
| `corsair-cv450` | `compatibility.wattage` | `450` | [mercado_livre.POWER_OUTPUT](https://api.mercadolibre.com/products/MLB58545794) |
| `corsair-cx500` | `technical_specs.wattage` | `500` | [mercado_livre.POWER_OUTPUT](https://api.mercadolibre.com/products/MLB7679847) |
| `corsair-cx500` | `compatibility.wattage` | `500` | [mercado_livre.POWER_OUTPUT](https://api.mercadolibre.com/products/MLB7679847) |
| `thermaltake-smart-rgb-600w` | `technical_specs.wattage` | `600` | [mercado_livre.POWER_OUTPUT](https://api.mercadolibre.com/products/MLB44126768) |
| `thermaltake-smart-rgb-600w` | `compatibility.wattage` | `600` | [mercado_livre.POWER_OUTPUT](https://api.mercadolibre.com/products/MLB44126768) |
| `kingston-kvr26n19s8-8` | `technical_specs.capacity` | `"8GB"` | [mercado_livre.RAM_MEMORY_MODULE_TOTAL_CAPACITY](https://api.mercadolibre.com/products/MLB18914707) |
| `kingston-kvr26n19s8-8` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.RAM_MEMORY_MODULE_TYPE](https://api.mercadolibre.com/products/MLB18914707) |
| `kingston-kvr26n19s8-8` | `technical_specs.speed` | `"2666MHz"` | [mercado_livre.RAM_MEMORY_MODULE_SPEED](https://api.mercadolibre.com/products/MLB18914707) |
| `kingston-kvr26n19s8-8` | `technical_specs.modules` | `1` | [mercado_livre.RAM_MEMORY_MODULES](https://api.mercadolibre.com/products/MLB18914707) |
| `kingston-kvr26n19s8-8` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.RAM_MEMORY_MODULE_TYPE](https://api.mercadolibre.com/products/MLB18914707) |
| `kingston-kf432c16bb-8` | `technical_specs.capacity` | `"8GB"` | [mercado_livre.RAM_MEMORY_MODULE_TOTAL_CAPACITY](https://api.mercadolibre.com/products/MLB80105537) |
| `kingston-kf432c16bb-8` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.RAM_MEMORY_MODULE_TYPE](https://api.mercadolibre.com/products/MLB80105537) |
| `kingston-kf432c16bb-8` | `technical_specs.speed` | `"3200MHz"` | [mercado_livre.RAM_MEMORY_MODULE_SPEED](https://api.mercadolibre.com/products/MLB80105537) |
| `kingston-kf432c16bb-8` | `technical_specs.modules` | `1` | [mercado_livre.RAM_MEMORY_MODULES](https://api.mercadolibre.com/products/MLB80105537) |
| `kingston-kf432c16bb-8` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.RAM_MEMORY_MODULE_TYPE](https://api.mercadolibre.com/products/MLB80105537) |
| `kingston-kf432c16bb-16` | `technical_specs.capacity` | `"16GB"` | [mercado_livre.RAM_MEMORY_MODULE_TOTAL_CAPACITY](https://api.mercadolibre.com/products/MLB54112928) |
| `kingston-kf432c16bb-16` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.RAM_MEMORY_MODULE_TYPE](https://api.mercadolibre.com/products/MLB54112928) |
| `kingston-kf432c16bb-16` | `technical_specs.speed` | `"3200MHz"` | [mercado_livre.RAM_MEMORY_MODULE_SPEED](https://api.mercadolibre.com/products/MLB54112928) |
| `kingston-kf432c16bb-16` | `technical_specs.modules` | `"1x16GB"` | [mercado_livre.RAM_MEMORY_MODULES](https://api.mercadolibre.com/products/MLB54112928) |
| `kingston-kf432c16bb-16` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.RAM_MEMORY_MODULE_TYPE](https://api.mercadolibre.com/products/MLB54112928) |
| `kingston-kf432c16bb-32` | `technical_specs.capacity` | `"32GB"` | [mercado_livre.RAM_MEMORY_MODULE_TOTAL_CAPACITY](https://api.mercadolibre.com/products/MLB18706822) |
| `kingston-kf432c16bb-32` | `compatibility.memory_type` | `"DDR4"` | [mercado_livre.RAM_MEMORY_MODULE_TYPE](https://api.mercadolibre.com/products/MLB18706822) |
| `kingston-kf432c16bb-32` | `technical_specs.speed` | `"3200MHz"` | [mercado_livre.RAM_MEMORY_MODULE_SPEED](https://api.mercadolibre.com/products/MLB18706822) |
| `kingston-kf432c16bb-32` | `technical_specs.modules` | `1` | [mercado_livre.RAM_MEMORY_MODULES](https://api.mercadolibre.com/products/MLB18706822) |
| `kingston-kf432c16bb-32` | `technical_specs.memory_type` | `"DDR4"` | [mercado_livre.RAM_MEMORY_MODULE_TYPE](https://api.mercadolibre.com/products/MLB18706822) |
| `kingston-kf556c40bb-16` | `technical_specs.capacity` | `"16GB"` | [mercado_livre.RAM_MEMORY_MODULE_TOTAL_CAPACITY](https://api.mercadolibre.com/products/MLB19153019) |
| `kingston-kf556c40bb-16` | `compatibility.memory_type` | `"DDR5"` | [mercado_livre.RAM_MEMORY_MODULE_TYPE](https://api.mercadolibre.com/products/MLB19153019) |
| `kingston-kf556c40bb-16` | `technical_specs.speed` | `"5600MHz"` | [mercado_livre.RAM_MEMORY_MODULE_SPEED](https://api.mercadolibre.com/products/MLB19153019) |
| `kingston-kf556c40bb-16` | `technical_specs.modules` | `1` | [mercado_livre.RAM_MEMORY_MODULES](https://api.mercadolibre.com/products/MLB19153019) |
| `kingston-kf556c40bb-16` | `technical_specs.memory_type` | `"DDR5"` | [mercado_livre.RAM_MEMORY_MODULE_TYPE](https://api.mercadolibre.com/products/MLB19153019) |
| `samsung-mz-v7s1t0` | `technical_specs.capacity` | `"1TB"` | [mercado_livre.CAPACITY](https://api.mercadolibre.com/products/MLB21487224) |
| `samsung-mz-v7s1t0` | `technical_specs.interface` | `"NVMe PCIe 3.0"` | [mercado_livre.INTERFACES](https://api.mercadolibre.com/products/MLB21487224) |
| `gigabyte-rtx-2060-d6-6gb-rev2` | `technical_specs.memory` | `"6GB"` | [mercado_livre.MEMORY_SIZE](https://api.mercadolibre.com/products/MLB18617723) |
| `gigabyte-rtx-2060-d6-6gb-rev2` | `technical_specs.length_mm` | `225.65` | [mercado_livre.LENGTH](https://api.mercadolibre.com/products/MLB18617723) |
| `gigabyte-rtx-2060-d6-6gb-rev2` | `compatibility.min_psu_watts` | `500` | [mercado_livre.POWER_REQUIREMENT](https://api.mercadolibre.com/products/MLB18617723) |

## Execução de /ai/analyze-pc em 10 configurações

Rota FastAPI real, `enrich()`, regras e validação da resposta reais; transporte do catálogo substituído pelo snapshot local. Somente a redação da IA usa um substituto de teste identificado. **Não houve chamada ao Gemini nem teste HTTP contra produção.** Compatibilidade técnica e IDs abaixo são resultados calculados, não saídas simuladas.

| PC | Configuração | HTTP | Reconhecidos | Regras verificadas | Faltantes | Compatibilidade |
|---|---|---:|---:|---:|---:|---|
| 1 | AM4 B550 / RTX 3060 | 200 | 7/7 | 7/7 | 0 | compatible |
| 2 | AM4 B550 / RTX 4070 Super | 200 | 7/7 | 7/7 | 0 | compatible |
| 3 | Intel B660 / RTX 4060 | 200 | 7/7 | 7/7 | 0 | compatible |
| 4 | AM5 B650 / RX 7800 XT | 200 | 7/7 | 7/7 | 0 | compatible |
| 5 | AM4 B450 / RX 6600 | 200 | 7/7 | 7/7 | 0 | compatible |
| 6 | AM4 A520 / RX 6650 XT | 200 | 7/7 | 7/7 | 0 | compatible |
| 7 | AM4 B550 / RTX 4060 Ti | 200 | 7/7 | 7/7 | 0 | compatible |
| 8 | AM5 A620 / RX 7700 XT | 200 | 7/7 | 7/7 | 0 | compatible |
| 9 | Intel B760 DDR4 / RTX 4070 | 200 | 7/7 | 7/7 | 0 | compatible |
| 10 | Intel B760 DDR5 / RTX 4080 Super | 200 | 7/7 | 7/7 | 0 | compatible |

### PC 1: AM4 B550 / RTX 3060

| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |
|---|---|---|---|
| cpu: Processador AMD Ryzen 5 5600 | `ryzen-5-5600` | {"cores": 6, "threads": 12, "tdp_watts": 65, "socket": "AM4"} | {"socket": "AM4"} |
| gpu: RTX 3060 | `rtx-3060` | {"memory": "12GB GDDR6", "interface": "PCIe 4.0", "power_consumption_watts": 170, "length_mm": 200} | {"min_psu_watts": 550} |
| motherboard: Gigabyte B550M K | `gigabyte-b550m-k` | {"memory_slots": 4, "max_memory_gb": 128, "socket": "AM4", "memory_type": "DDR4"} | {"socket": "AM4", "memory_type": "DDR4", "form_factor": "Micro-ATX"} |
| ram: kingston-kf432c16bb-16 | `kingston-kf432c16bb-16` | {"capacity": "16GB", "speed": "3200MHz", "modules": "1x16GB", "memory_type": "DDR4"} | {"memory_type": "DDR4"} |
| storage: ['Kingston NV3 1TB NVMe M.2'] | `ssd-nvme-1tb` | {"capacity": "1TB", "interface": "NVMe PCIe 4.0"} | {} |
| psu: 650W | `fonte-650w` | {"wattage": 650} | {} |
| case: Lian Li LANCOOL 216 | `gabinete-lian-li-lancool` | {} | {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"], "max_gpu_length_mm": 392} |

Regras verificadas: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`. Regras faltantes: `[]`.

### PC 2: AM4 B550 / RTX 4070 Super

| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |
|---|---|---|---|
| cpu: Ryzen 7 5700X AMD | `ryzen-7-5700x` | {"cores": 8, "threads": 16, "tdp_watts": 65, "socket": "AM4"} | {"socket": "AM4"} |
| gpu: RTX 4070 Super | `rtx-4070-super` | {"memory": "12GB GDDR6X", "interface": "PCIe 4.0", "power_consumption_watts": 220, "length_mm": 305} | {"min_psu_watts": 650} |
| motherboard: ASRock B550 PG VELOCITA | `asrock-b550-pg-velocita` | {"memory_slots": 4, "max_memory_gb": 128, "socket": "AM4", "memory_type": "DDR4"} | {"socket": "AM4", "memory_type": "DDR4", "form_factor": "ATX"} |
| ram: kit-ram-32gb-ddr4-3600 | `kit-ram-32gb-ddr4-3600` | {"capacity": "32GB", "modules": "2x16GB", "memory_type": "DDR4", "speed": "3600MHz"} | {"memory_type": "DDR4"} |
| storage: ['Kingston NV3 1TB NVMe M.2'] | `ssd-nvme-1tb` | {"capacity": "1TB", "interface": "NVMe PCIe 4.0"} | {} |
| psu: 750W | `fonte-750w` | {"wattage": 750} | {} |
| case: Lian Li LANCOOL 216 | `gabinete-lian-li-lancool` | {} | {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"], "max_gpu_length_mm": 392} |

Regras verificadas: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`. Regras faltantes: `[]`.

### PC 3: Intel B660 / RTX 4060

| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |
|---|---|---|---|
| cpu: i5-12400F | `intel-i5-12400f` | {"cores": 6, "threads": 12, "tdp_watts": 65, "socket": "LGA1700"} | {"socket": "LGA1700"} |
| gpu: RTX 4060 | `rtx-4060` | {"memory": "8GB GDDR6", "interface": "PCIe 4.0", "power_consumption_watts": 115, "length_mm": 240} | {"min_psu_watts": 550} |
| motherboard: Gigabyte B660M AORUS PRO | `b660-lga1700-ddr4` | {"memory_slots": 4, "socket": "LGA1700", "memory_type": "DDR4", "max_memory_gb": 128} | {"socket": "LGA1700", "memory_type": "DDR4", "form_factor": "Micro-ATX"} |
| ram: kingston-kf432c16bb-16 | `kingston-kf432c16bb-16` | {"capacity": "16GB", "speed": "3200MHz", "modules": "1x16GB", "memory_type": "DDR4"} | {"memory_type": "DDR4"} |
| storage: ['Kingston NV3 1TB NVMe M.2'] | `ssd-nvme-1tb` | {"capacity": "1TB", "interface": "NVMe PCIe 4.0"} | {} |
| psu: 650W | `fonte-650w` | {"wattage": 650} | {} |
| case: Lian Li LANCOOL 216 | `gabinete-lian-li-lancool` | {} | {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"], "max_gpu_length_mm": 392} |

Regras verificadas: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`. Regras faltantes: `[]`.

### PC 4: AM5 B650 / RX 7800 XT

| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |
|---|---|---|---|
| cpu: AMD Ryzen 5 7600 | `ryzen-5-7600` | {"cores": 6, "threads": 12, "tdp_watts": 65, "socket": "AM5"} | {"socket": "AM5"} |
| gpu: RX 7800 XT | `rx-7800-xt` | {"memory": "16GB GDDR6", "interface": "PCIe 4.0", "power_consumption_watts": 263, "length_mm": 320} | {"min_psu_watts": 750} |
| motherboard: Gigabyte B650 Gaming X AX V2 | `gigabyte-b650-gaming-x-ax-v2` | {"memory_slots": 4, "max_memory_gb": 256, "socket": "AM5", "memory_type": "DDR5"} | {"socket": "AM5", "memory_type": "DDR5", "form_factor": "ATX"} |
| ram: kit-ram-32gb-ddr5-6000 | `kit-ram-32gb-ddr5-6000` | {"capacity": "32GB", "modules": "2x16GB", "memory_type": "DDR5", "speed": "6000MHz"} | {"memory_type": "DDR5"} |
| storage: ['Kingston NV3 1TB NVMe M.2'] | `ssd-nvme-1tb` | {"capacity": "1TB", "interface": "NVMe PCIe 4.0"} | {} |
| psu: 750W | `fonte-750w` | {"wattage": 750} | {} |
| case: Lian Li LANCOOL 216 | `gabinete-lian-li-lancool` | {} | {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"], "max_gpu_length_mm": 392} |

Regras verificadas: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`. Regras faltantes: `[]`.

### PC 5: AM4 B450 / RX 6600

| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |
|---|---|---|---|
| cpu: AMD Ryzen 5 3600 | `ryzen-5-3600` | {"cores": 6, "threads": 12, "tdp_watts": 65, "socket": "AM4"} | {"socket": "AM4"} |
| gpu: RX 6600 | `rx-6600` | {"memory": "8GB GDDR6", "interface": "PCIe 4.0", "power_consumption_watts": 132, "length_mm": 200} | {"min_psu_watts": 500} |
| motherboard: Revenger G-B450 | `revenger-g-b450` | {"memory_slots": 2, "max_memory_gb": 32, "socket": "AM4", "memory_type": "DDR4"} | {"socket": "AM4", "memory_type": "DDR4", "form_factor": "Micro-ATX"} |
| ram: kingston-kvr26n19s8-8 | `kingston-kvr26n19s8-8` | {"capacity": "8GB", "speed": "2666MHz", "modules": 1, "memory_type": "DDR4"} | {"memory_type": "DDR4"} |
| storage: ['Samsung 970 EVO Plus MZ-V7S1T0 1TB NVMe PCIe 3.0'] | `samsung-mz-v7s1t0` | {"capacity": "1TB", "interface": "NVMe PCIe 3.0"} | {} |
| psu: Corsair CX500 | `corsair-cx500` | {"wattage": 500} | {} |
| case: Lian Li LANCOOL 216 | `gabinete-lian-li-lancool` | {} | {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"], "max_gpu_length_mm": 392} |

Regras verificadas: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`. Regras faltantes: `[]`.

### PC 6: AM4 A520 / RX 6650 XT

| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |
|---|---|---|---|
| cpu: AMD Ryzen 5 5500 | `ryzen-5-5500` | {"cores": 6, "threads": 12, "tdp_watts": 65, "socket": "AM4"} | {"socket": "AM4"} |
| gpu: RX 6650 XT | `rx-6650-xt` | {"memory": "8GB GDDR6", "interface": "PCIe 4.0", "power_consumption_watts": 176, "length_mm": 215} | {"min_psu_watts": 550} |
| motherboard: ASRock A520M-HDV | `asrock-a520m-hdv` | {"max_memory_gb": 64, "memory_slots": 2, "socket": "AM4", "memory_type": "DDR4"} | {"socket": "AM4", "memory_type": "DDR4", "form_factor": "Micro-ATX"} |
| ram: kingston-kf432c16bb-8 | `kingston-kf432c16bb-8` | {"capacity": "8GB", "speed": "3200MHz", "modules": 1, "memory_type": "DDR4"} | {"memory_type": "DDR4"} |
| storage: ['Kingston NV3 1TB NVMe M.2'] | `ssd-nvme-1tb` | {"capacity": "1TB", "interface": "NVMe PCIe 4.0"} | {} |
| psu: 550W | `fonte-550w` | {"wattage": 550} | {} |
| case: Lian Li LANCOOL 216 | `gabinete-lian-li-lancool` | {} | {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"], "max_gpu_length_mm": 392} |

Regras verificadas: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`. Regras faltantes: `[]`.

### PC 7: AM4 B550 / RTX 4060 Ti

| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |
|---|---|---|---|
| cpu: AMD Ryzen 5 5600X | `ryzen-5-5600x` | {"cores": 6, "threads": 12, "tdp_watts": 65, "socket": "AM4"} | {"socket": "AM4"} |
| gpu: RTX 4060 Ti | `rtx-4060-ti` | {"memory": "8GB GDDR6", "interface": "PCIe 4.0", "power_consumption_watts": 160, "length_mm": 240} | {"min_psu_watts": 550} |
| motherboard: ASRock B550 PG VELOCITA | `asrock-b550-pg-velocita` | {"memory_slots": 4, "max_memory_gb": 128, "socket": "AM4", "memory_type": "DDR4"} | {"socket": "AM4", "memory_type": "DDR4", "form_factor": "ATX"} |
| ram: kingston-kf432c16bb-32 | `kingston-kf432c16bb-32` | {"capacity": "32GB", "speed": "3200MHz", "modules": 1, "memory_type": "DDR4"} | {"memory_type": "DDR4"} |
| storage: ['Kingston NV3 1TB NVMe M.2'] | `ssd-nvme-1tb` | {"capacity": "1TB", "interface": "NVMe PCIe 4.0"} | {} |
| psu: 650W | `fonte-650w` | {"wattage": 650} | {} |
| case: Lian Li LANCOOL 216 | `gabinete-lian-li-lancool` | {} | {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"], "max_gpu_length_mm": 392} |

Regras verificadas: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`. Regras faltantes: `[]`.

### PC 8: AM5 A620 / RX 7700 XT

| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |
|---|---|---|---|
| cpu: AMD Ryzen 7 7800X3D | `ryzen-7-7800x3d` | {"cores": 8, "threads": 16, "tdp_watts": 120, "socket": "AM5"} | {"socket": "AM5"} |
| gpu: RX 7700 XT | `rx-7700-xt` | {"memory": "12GB GDDR6", "interface": "PCIe 4.0", "power_consumption_watts": 245, "length_mm": 267} | {"min_psu_watts": 700} |
| motherboard: ASRock A620M-C | `asrock-a620m-c` | {"memory_slots": 4, "max_memory_gb": 256, "socket": "AM5", "memory_type": "DDR5"} | {"socket": "AM5", "memory_type": "DDR5", "form_factor": "Micro-ATX"} |
| ram: kit-ram-32gb-ddr5-6000 | `kit-ram-32gb-ddr5-6000` | {"capacity": "32GB", "modules": "2x16GB", "memory_type": "DDR5", "speed": "6000MHz"} | {"memory_type": "DDR5"} |
| storage: ['Kingston NV3 1TB NVMe M.2'] | `ssd-nvme-1tb` | {"capacity": "1TB", "interface": "NVMe PCIe 4.0"} | {} |
| psu: 750W | `fonte-750w` | {"wattage": 750} | {} |
| case: Lian Li LANCOOL 216 | `gabinete-lian-li-lancool` | {} | {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"], "max_gpu_length_mm": 392} |

Regras verificadas: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`. Regras faltantes: `[]`.

### PC 9: Intel B760 DDR4 / RTX 4070

| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |
|---|---|---|---|
| cpu: Intel Core i5-13600K | `intel-i5-13600k` | {"cores": 14, "threads": 20, "tdp_watts": 125, "socket": "LGA1700"} | {"socket": "LGA1700"} |
| gpu: RTX 4070 | `rtx-4070` | {"memory": "12GB GDDR6X", "interface": "PCIe 4.0", "power_consumption_watts": 200, "length_mm": 285} | {"min_psu_watts": 650} |
| motherboard: Gigabyte B760M K DDR4 | `gigabyte-b760m-k-ddr4` | {"memory_slots": 2, "max_memory_gb": 64, "socket": "LGA1700", "memory_type": "DDR4"} | {"socket": "LGA1700", "memory_type": "DDR4", "form_factor": "Micro-ATX"} |
| ram: kit-ram-16gb-ddr4-3200 | `kit-ram-16gb-ddr4-3200` | {"capacity": "16GB", "modules": "2x8GB", "memory_type": "DDR4", "speed": "3200MHz"} | {"memory_type": "DDR4"} |
| storage: ['Kingston NV3 1TB NVMe M.2'] | `ssd-nvme-1tb` | {"capacity": "1TB", "interface": "NVMe PCIe 4.0"} | {} |
| psu: 750W | `fonte-750w` | {"wattage": 750} | {} |
| case: Lian Li LANCOOL 216 | `gabinete-lian-li-lancool` | {} | {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"], "max_gpu_length_mm": 392} |

Regras verificadas: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`. Regras faltantes: `[]`.

### PC 10: Intel B760 DDR5 / RTX 4080 Super

| Categoria / entrada | catalog_id | Specs disponíveis | Compatibilidade técnica |
|---|---|---|---|
| cpu: Intel Core i7-14700K | `intel-i7-14700k` | {"cores": 20, "threads": 28, "tdp_watts": 125, "socket": "LGA1700"} | {"socket": "LGA1700"} |
| gpu: RTX 4080 Super | `rtx-4080-super` | {"memory": "16GB GDDR6X", "interface": "PCIe 4.0", "power_consumption_watts": 320, "length_mm": 340} | {"min_psu_watts": 850} |
| motherboard: Gigabyte B760M DS3H DDR5 | `gigabyte-b760m-ds3h-ddr5` | {"memory_slots": 4, "max_memory_gb": 192, "socket": "LGA1700", "memory_type": "DDR5"} | {"socket": "LGA1700", "memory_type": "DDR5", "form_factor": "Micro-ATX"} |
| ram: kit-ram-64gb-ddr5-6000 | `kit-ram-64gb-ddr5-6000` | {"capacity": "64GB", "modules": "2x32GB", "memory_type": "DDR5", "speed": "6000MHz"} | {"memory_type": "DDR5"} |
| storage: ['Kingston NV3 1TB NVMe M.2'] | `ssd-nvme-1tb` | {"capacity": "1TB", "interface": "NVMe PCIe 4.0"} | {} |
| psu: 850W | `fonte-850w` | {"wattage": 850} | {} |
| case: Lian Li LANCOOL 216 | `gabinete-lian-li-lancool` | {} | {"supported_form_factors": ["ATX", "Micro-ATX", "Mini-ITX"], "max_gpu_length_mm": 392} |

Regras verificadas: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`. Regras faltantes: `[]`.

## Auditoria individual de todos os componentes

| ID | Categoria / escopo | Campos obrigatórios ausentes |
|---|---|---|
| `intel-i5-14600k` | cpu / model | Nenhum |
| `intel-i7-14700k` | cpu / model | Nenhum |
| `intel-i5-12400f` | cpu / model | Nenhum |
| `ryzen-5-5600` | cpu / model | Nenhum |
| `ryzen-7-5700x` | cpu / model | Nenhum |
| `ryzen-5-7600` | cpu / model | Nenhum |
| `ryzen-7-7800x3d` | cpu / model | Nenhum |
| `ryzen-9-7950x` | cpu / model | Nenhum |
| `b550-am4-ddr4` | motherboard / family | technical_specs.max_memory_gb |
| `b550m-am4-ddr4` | motherboard / family | Nenhum |
| `x570-am4-ddr4` | motherboard / family | technical_specs.max_memory_gb |
| `b650-am5-ddr5` | motherboard / family | technical_specs.max_memory_gb |
| `x670e-am5-ddr5` | motherboard / sku | Nenhum |
| `b760-lga1700-ddr5` | motherboard / family | Nenhum |
| `z790-lga1700-ddr5` | motherboard / family | Nenhum |
| `b660-lga1700-ddr4` | motherboard / sku | Nenhum |
| `ram-16gb-ddr4` | ram / sku | modules não conhecido (ram_slots pendente) |
| `ram-32gb-ddr4` | ram / sku | modules não conhecido (ram_slots pendente) |
| `ram-16gb-ddr5` | ram / sku | modules não conhecido (ram_slots pendente) |
| `ram-32gb-ddr5` | ram / sku | modules não conhecido (ram_slots pendente) |
| `ram-64gb-ddr5` | ram / sku | modules não conhecido (ram_slots pendente) |
| `ssd-nvme-500gb` | storage / sku | Nenhum |
| `ssd-nvme-1tb` | storage / sku | Nenhum |
| `ssd-nvme-2tb` | storage / sku | Nenhum |
| `rtx-4060` | gpu / family | Nenhum |
| `rtx-4070-super` | gpu / family | Nenhum |
| `rtx-4080-super` | gpu / family | Nenhum |
| `rtx-5090` | gpu / family | Nenhum |
| `rx-7600` | gpu / family | Nenhum |
| `rx-7800-xt` | gpu / family | Nenhum |
| `fonte-650w` | psu / family | Nenhum |
| `fonte-750w` | psu / family | Nenhum |
| `fonte-850w` | psu / family | Nenhum |
| `fonte-1000w` | psu / family | Nenhum |
| `fonte-1200w` | psu / family | Nenhum |
| `gabinete-atx` | case / sku | Nenhum |
| `gabinete-micro-atx` | case / sku | Nenhum |
| `gabinete-compacto-itx` | case / family | Nenhum |
| `intel-i3-12100f` | cpu / model | Nenhum |
| `intel-i5-13400f` | cpu / model | Nenhum |
| `intel-i5-14400f` | cpu / model | Nenhum |
| `intel-i7-13700k` | cpu / model | Nenhum |
| `intel-i9-13900ks` | cpu / model | Nenhum |
| `intel-i9-14900k` | cpu / model | Nenhum |
| `ryzen-3-5300g` | cpu / model | Nenhum |
| `ryzen-5-5500` | cpu / model | Nenhum |
| `ryzen-9-5900x` | cpu / model | Nenhum |
| `ryzen-9-5950x` | cpu / model | Nenhum |
| `ryzen-5-7600x` | cpu / model | Nenhum |
| `ryzen-9-7900x` | cpu / model | Nenhum |
| `ryzen-7-9800x3d` | cpu / model | Nenhum |
| `ryzen-9-9950x` | cpu / model | Nenhum |
| `rtx-3060` | gpu / family | Nenhum |
| `rtx-3070` | gpu / family | Nenhum |
| `rtx-3080` | gpu / family | Nenhum |
| `rtx-4060-ti` | gpu / family | Nenhum |
| `rtx-4070` | gpu / family | Nenhum |
| `rtx-4090` | gpu / family | Nenhum |
| `rtx-5070` | gpu / family | Nenhum |
| `rtx-5070-ti` | gpu / family | Nenhum |
| `rtx-5080` | gpu / family | Nenhum |
| `rx-6600` | gpu / family | Nenhum |
| `rx-6650-xt` | gpu / family | Nenhum |
| `rx-7700-xt` | gpu / family | Nenhum |
| `rx-7900-gre` | gpu / family | Nenhum |
| `rx-7900-xtx` | gpu / family | Nenhum |
| `cooler-cm-hyper212` | cooler / sku | Cooler: sem critério solicitado |
| `cooler-deepcool-ak400` | cooler / sku | Cooler: sem critério solicitado |
| `cooler-deepcool-ak620` | cooler / sku | Cooler: sem critério solicitado |
| `cooler-noctua-nhd15` | cooler / sku | Cooler: sem critério solicitado |
| `cooler-liquid-120mm` | cooler / sku | Cooler: sem critério solicitado |
| `cooler-liquid-240mm` | cooler / sku | Cooler: sem critério solicitado |
| `cooler-nzxt-kraken-240` | cooler / sku | Cooler: sem critério solicitado |
| `cooler-nzxt-kraken-360` | cooler / sku | Cooler: sem critério solicitado |
| `cooler-corsair-h150i` | cooler / sku | Cooler: sem critério solicitado |
| `kit-ram-16gb-ddr4-3200` | kit-ram / sku | Nenhum |
| `kit-ram-32gb-ddr4-3600` | kit-ram / sku | Nenhum |
| `kit-ram-64gb-ddr4-3200` | kit-ram / sku | Nenhum |
| `kit-ram-32gb-ddr5-6000` | kit-ram / sku | Nenhum |
| `kit-ram-64gb-ddr5-6000` | kit-ram / sku | Nenhum |
| `kit-ram-96gb-ddr5-6400` | kit-ram / sku | Nenhum |
| `ram-8gb-ddr4` | ram / sku | modules não conhecido (ram_slots pendente) |
| `ram-8gb-ddr5` | ram / sku | modules não conhecido (ram_slots pendente) |
| `ssd-sata-480gb` | storage / sku | Nenhum |
| `ssd-sata-1tb` | storage / family | Nenhum |
| `hdd-1tb` | storage / sku | Nenhum |
| `hdd-2tb` | storage / sku | Nenhum |
| `hdd-4tb` | storage / sku | Nenhum |
| `ssd-nvme-4tb` | storage / sku | Nenhum |
| `gabinete-lian-li-lancool` | case / sku | Nenhum |
| `gabinete-nzxt-h510` | case / sku | Nenhum |
| `gabinete-phanteks-p360a` | case / sku | Nenhum |
| `fonte-550w` | psu / family | Nenhum |
| `fonte-1100w` | psu / family | Nenhum |
| `ryzen-5-5500x3d` | cpu / model | Nenhum |
| `ryzen-5-7500f` | cpu / model | technical_specs.tdp_watts |
| `ryzen-5-8400f` | cpu / model | Nenhum |
| `ryzen-7-5800x3d` | cpu / model | Nenhum |
| `ryzen-5-8600g` | cpu / model | Nenhum |
| `ryzen-7-5700` | cpu / model | Nenhum |
| `ryzen-7-5800xt` | cpu / model | Nenhum |
| `ryzen-7-7700` | cpu / model | Nenhum |
| `ryzen-9-7900` | cpu / model | Nenhum |
| `ryzen-5-9600x` | cpu / model | technical_specs.tdp_watts |
| `ryzen-7-9700x` | cpu / model | Nenhum |
| `ryzen-9-5900xt` | cpu / model | Nenhum |
| `intel-i5-14600kf` | cpu / model | technical_specs.tdp_watts |
| `intel-i7-14700kf` | cpu / model | Nenhum |
| `rtx-5050-8gb` | gpu / family | technical_specs.length_mm, compatibility.min_psu_watts |
| `rtx-5060-8gb` | gpu / family | technical_specs.length_mm, compatibility.min_psu_watts |
| `rtx-5060-ti-8gb` | gpu / family | technical_specs.length_mm, compatibility.min_psu_watts |
| `rtx-5060-ti-16gb` | gpu / family | technical_specs.length_mm, compatibility.min_psu_watts |
| `rx-9060-xt-16gb` | gpu / family | technical_specs.length_mm, compatibility.min_psu_watts |
| `rx-9070-xt-16gb` | gpu / family | technical_specs.length_mm, compatibility.min_psu_watts |
| `a520m-am4-ddr4` | motherboard / family | technical_specs.memory_slots, technical_specs.max_memory_gb |
| `b450m-am4-ddr4` | motherboard / family | technical_specs.memory_slots, technical_specs.max_memory_gb |
| `b760m-lga1700-ddr4` | motherboard / family | technical_specs.memory_slots, technical_specs.max_memory_gb |
| `b760m-lga1700-ddr5` | motherboard / family | technical_specs.memory_slots, technical_specs.max_memory_gb |
| `b850m-am5-ddr5` | motherboard / family | technical_specs.memory_slots, technical_specs.max_memory_gb |
| `b840m-am5-ddr5` | motherboard / family | technical_specs.memory_slots, technical_specs.max_memory_gb |
| `ssd-wd-green-wds200t5g0a-2tb` | storage / model | Nenhum |
| `ryzen-5-3600` | cpu / model | Nenhum |
| `ryzen-5-5600x` | cpu / model | Nenhum |
| `ryzen-7-5800x` | cpu / model | Nenhum |
| `intel-i5-13600k` | cpu / model | Nenhum |
| `gigabyte-b550m-k` | motherboard / sku | Nenhum |
| `asrock-b550-pg-velocita` | motherboard / sku | Nenhum |
| `gigabyte-b650-gaming-x-ax-v2` | motherboard / sku | Nenhum |
| `asrock-a520m-hdv` | motherboard / sku | Nenhum |
| `asrock-a620m-c` | motherboard / sku | Nenhum |
| `foxstar-fs-h610mb-eg` | motherboard / sku | Nenhum |
| `gigabyte-b760m-k-ddr4` | motherboard / sku | Nenhum |
| `gigabyte-b760m-ds3h-ddr5` | motherboard / sku | Nenhum |
| `revenger-g-b450` | motherboard / sku | Nenhum |
| `gigabyte-x570-aorus-ultra` | motherboard / sku | technical_specs.memory_slots |
| `gigabyte-x670-aorus-elite-ax` | motherboard / sku | technical_specs.memory_slots, compatibility.form_factor |
| `msi-pro-z690-a-ddr4` | motherboard / sku | technical_specs.memory_slots |
| `gigabyte-z790-aorus-elite-ax` | motherboard / sku | technical_specs.memory_slots |
| `palit-rtx-5050-dual-8gb` | gpu / sku | Nenhum |
| `gigabyte-rtx-5060-ti-windforce-max-oc-8gb` | gpu / sku | Nenhum |
| `corsair-cv450` | psu / sku | Nenhum |
| `corsair-cx500` | psu / sku | Nenhum |
| `thermaltake-smart-rgb-600w` | psu / sku | Nenhum |
| `kingston-kvr26n19s8-8` | ram / sku | Nenhum |
| `kingston-kf432c16bb-8` | ram / sku | Nenhum |
| `kingston-kf432c16bb-16` | ram / sku | Nenhum |
| `kingston-kf432c16bb-32` | ram / sku | Nenhum |
| `kingston-kf556c40bb-16` | ram / sku | Nenhum |
| `samsung-mz-v7s1t0` | storage / sku | Nenhum |
| `gigabyte-rtx-2060-d6-6gb-rev2` | gpu / sku | Nenhum |

## Testes e reprodução local

Resultado: **1.197 testes passaram, 1 ignorado**: 275 em api-orcamentos; 399 em api-catalogo (mais 1 ignorado); 523 em services. Inclui concorrência Mongo, idempotência, ausência de sobrescritas, paridade entre seed Mongo vazio e snapshot enriquecido, ambiguidades, sufixos Ti/Super/X, módulos ausentes, incompatibilidades reais e enriquecimento futuro pela integração oficial. Um teste de deduplicação de ofertas teve seu relógio fixado na data do próprio fixture para não expirar conforme o calendário; a lógica de produção correspondente não mudou.

Reexecução após aplicar o backfill: **0 campos a preencher**. O sync insert-only também propõe 0 novas inserções após a primeira aplicação.

```powershell
python scripts/audit_catalog_coverage.py --output reports/catalog-audit.json
python scripts/backfill_demo_specs.py --dry-run
python scripts/sync_catalog_coverage.py --dry-run
python scripts/build_catalog_coverage.py
python scripts/validate_catalog_pcs.py
python -m pytest api-orcamentos/tests -q
python -m pytest api-catalogo/tests -q
python -m pytest services/tests -q
```

Não execute os três diretórios de testes num único processo pytest: eles usam módulos locais de mesmo nome (`main`, `services`, `database`). As dependências declaradas dos dois serviços têm versões conflitantes; esta execução usou um ambiente local com os requisitos de api-orcamentos e mongomock/serviços adicionais. Para ambientes separados, instale os requirements do serviço correspondente.

## Aplicação no MongoDB Atlas de produção, sem apagar dados

Execute a partir da raiz deste checkout atualizado, em um ambiente de manutenção com `pymongo` instalado. `MONGO_URI` deve vir do gerenciador de segredos/ambiente de produção, com a URI `mongodb+srv` real; `MONGO_DB` deve indicar o banco correto. Nenhum comando abaixo importa o loader de demo ou substitui documentos. O índice único de `components.id`, já exigido pela API, deve existir; o sync recusa aplicação sem esse índice. Os scripts não removem nem recriam índices.

```powershell
# MONGO_URI e MONGO_DB já definidos pelo ambiente seguro de produção.
New-Item -ItemType Directory -Force reports | Out-Null
python scripts/audit_catalog_coverage.py --mongo --db $env:MONGO_DB --output reports/atlas-before.json
python scripts/backfill_demo_specs.py --mongo --db $env:MONGO_DB --dry-run --report reports/atlas-backfill-plan.json
python scripts/sync_catalog_coverage.py --mongo --db $env:MONGO_DB --dry-run

# Após revisar os valores e suas origens nos relatórios:
python scripts/backfill_demo_specs.py --mongo --db $env:MONGO_DB --apply --report reports/atlas-backfill-applied.json
python scripts/sync_catalog_coverage.py --mongo --db $env:MONGO_DB --apply
python scripts/audit_catalog_coverage.py --mongo --db $env:MONGO_DB --output reports/atlas-after.json
python scripts/backfill_demo_specs.py --mongo --db $env:MONGO_DB --dry-run --report reports/atlas-backfill-idempotence.json
```

O backfill percorre todos os documentos e o cache `external_product_enrichment` do próprio banco. As referências persistidas no projeto só se aplicam quando ID, nome, marca e categoria coincidem. Campos existentes — inclusive valores diferentes, zero ou inválidos — são preservados e exigem revisão separada. Campos preenchidos entre a leitura e a gravação não são sobrescritos. O sync adiciona somente os 29 IDs revisados que não existirem; não altera nenhum ID presente.

Publique as versões atualizadas de api-catalogo e api-orcamentos para ativar o mapper no enriquecimento futuro e o matching novo. O seed na inicialização não faz o backfill de documentos existentes. Os Dockerfiles incluem o módulo compartilhado.

Evidências completas: `docs/demo/catalog-coverage-before.json`, `catalog-coverage-after.json`, `catalog-backfill-changes.json`, `catalog-pc-validation.json`, `api-catalogo/catalog_spec_sources.json` e `catalog_spec_references.json`.
