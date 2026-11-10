# Relatório de resolução de entradas humanas

Execução: rota real `/ai/analyze-pc` + MongoDB local (127.0.0.1, snapshot de 18.213 componentes). Provedor de prosa simulado: nenhum Gemini, nenhum Atlas, nenhum dado externo.

## Resumo

- Catálogo antes/depois: 18213 / 18213; alterações técnicas: 0
- Entradas unitárias: 52/52
- Ambíguas sem resolução arbitrária: 10/10
- PCs informais: 30/30 (status: {'partial': 14, 'compatible': 6, 'incompatible': 10})
- Benchmark (1000 resoluções): p50 1.2956 ms, p95 3.3665 ms, máx 7.0462 ms (meta p95 < 10 ms: ok)
- Plano: IXSCAN `ix_catalog_human_lookup_keys`, 1 doc examinado; full scans por requisição: 0; máx. candidatos 1; chamadas Gemini no matching: 0

## Antes / depois dos três PCs informais anteriores

| PC | Antes (reconhecidos / regras / pendentes) | Depois |
|---|---|---|
| 1 | 5 / 4 / 3 | 7 / 4 / 3 |
| 2 | 4 / 1 / 6 | 6 / 3 / 4 |
| 3 | 4 / 2 / 5 | 6 / 3 / 4 |

## Entradas unitárias

| Categoria | Entrada | Normalizada | Escopo | catalog_id | Campos derivados | Tempo (ms) | Rejeições |
|---|---|---|---|---|---|---|---|
| cpu | ryzen 7 5700x | ryzen 7 5700x | model | ryzen-7-5700x | - | 5.6901 | - |
| cpu | AMD Ryzen 7 5700X | amd ryzen 7 5700x | model | ryzen-7-5700x | - | 1.4121 | - |
| cpu | Processador Ryzen 7 5700X | processador ryzen 7 5700x | model | ryzen-7-5700x | - | 0.9818 | - |
| cpu | Ryzen5700X | ryzen 5700x | model | ryzen-7-5700x | - | 2.0021 | - |
| cpu | Ryzen 5700X | ryzen 5700x | model | ryzen-7-5700x | - | 5.9787 | - |
| cpu | 5700X | 5700x | model | ryzen-7-5700x | - | 2.1012 | - |
| cpu | 5600X | 5600x | model | ryzen-5-5600x | - | 2.1256 | - |
| cpu | 5600G | 5600g | model | cpu-ext-ad10a2523ea89885f6facc2d | - | 1.7141 | - |
| cpu | 7800X3D | 7800x3d | model | ryzen-7-7800x3d | - | 1.9318 | - |
| cpu | i5 12400F | i5 12400f | model | intel-i5-12400f | - | 1.1834 | - |
| cpu | i5-13600K | i5 13600k | model | intel-i5-13600k | - | 1.5772 | - |
| cpu | Intel Core i5-13600KF | intel core i5 13600kf | model | cpu-ext-d5a472b721f87dbecff720c8 | - | 1.717 | - |
| gpu | rtx4060ti | rtx 4060 ti | family | rtx-4060-ti | - | 2.453 | - |
| gpu | RTX 4060 Ti | rtx 4060 ti | family | rtx-4060-ti | - | 1.4164 | - |
| gpu | GeForce RTX4060Ti | geforce rtx 4060 ti | family | rtx-4060-ti | - | 1.5598 | - |
| gpu | Nvidia GeForce RTX 4060 Ti | nvidia geforce rtx 4060 ti | family | rtx-4060-ti | - | 2.2747 | - |
| gpu | RTX 4070 | rtx 4070 | family | rtx-4070 | - | 1.8605 | - |
| gpu | RTX 4070 Super | rtx 4070 super | family | rtx-4070-super | - | 1.3864 | - |
| gpu | RTX 4070 Ti | rtx 4070 ti | family | - | - | 1.5132 | - |
| gpu | RTX4070TiSuper | rtx 4070 ti super | family | - | - | 3.4001 | - |
| gpu | RX 7800 XT | rx 7800 xt | family | rx-7800-xt | - | 2.8195 | - |
| gpu | RX7900XTX | rx 7900 xtx | family | rx-7900-xtx | - | 1.6386 | - |
| gpu | RX 7900 GRE | rx 7900 gre | family | rx-7900-gre | - | 1.3827 | - |
| gpu | RTX 4060 Ti 16GB | rtx 4060 ti 16gb | family | - | technical_specs.memory=user_text | 3.0984 | - |
| ram | 32GB DDR4 3200 | 32gb ddr4 3200 | generic | - | technical_specs.capacity=user_text, compatibility.memory_type=user_text, technical_specs.memory_type=user_text, technical_specs.speed=user_text | 1.2815 | - |
| ram | 2x16GB DDR4 3200 | 2x16gb ddr4 3200 | generic | - | technical_specs.modules=user_text, technical_specs.capacity=user_text, compatibility.memory_type=user_text, technical_specs.memory_type=user_text, technical_specs.speed=user_text | 0.6675 | - |
| ram | 16 GB 3200 DDR4 | 16 gb 3200 ddr4 | generic | - | technical_specs.capacity=user_text, compatibility.memory_type=user_text, technical_specs.memory_type=user_text, technical_specs.speed=user_text | 0.6074 | - |
| ram | DDR5 32GB 6000 | ddr5 32gb 6000 | generic | - | technical_specs.capacity=user_text, compatibility.memory_type=user_text, technical_specs.memory_type=user_text, technical_specs.speed=user_text | 0.5874 | - |
| ram | 2×16GB DDR5 6000 CL30 | 2x16gb ddr5 6000 cl30 | generic | - | technical_specs.modules=user_text, technical_specs.capacity=user_text, compatibility.memory_type=user_text, technical_specs.memory_type=user_text, technical_specs.speed=user_text, technical_specs.cas_latency=user_text | 0.7966 | - |
| ram | DDR4 8GB 2666MHz | ddr4 8gb 2666mhz | generic | - | technical_specs.capacity=user_text, compatibility.memory_type=user_text, technical_specs.memory_type=user_text, technical_specs.speed=user_text | 1.205 | - |
| ram | 4x8GB DDR4 3200 CL16 | 4x8gb ddr4 3200 cl16 | generic | - | technical_specs.modules=user_text, technical_specs.capacity=user_text, compatibility.memory_type=user_text, technical_specs.memory_type=user_text, technical_specs.speed=user_text, technical_specs.cas_latency=user_text | 3.0454 | - |
| ram | DDR5 16GB 5600MT/s | ddr5 16gb 5600mt/s | generic | - | technical_specs.capacity=user_text, compatibility.memory_type=user_text, technical_specs.memory_type=user_text, technical_specs.speed=user_text | 1.6414 | - |
| psu | 650w | 650w | generic | - | technical_specs.wattage=user_text | 1.3137 | - |
| psu | 650W 80 plus gold | 650w 80 plus gold | generic | - | technical_specs.wattage=user_text, technical_specs.efficiency=user_text | 0.7591 | - |
| psu | Fonte 750 watts | fonte 750 watts | generic | - | technical_specs.wattage=user_text | 0.6658 | - |
| psu | Corsair 650W | corsair 650w | generic | - | technical_specs.wattage=user_text | 0.5501 | - |
| psu | 450 watts | 450 watts | generic | - | technical_specs.wattage=user_text | 0.5516 | - |
| psu | 850W 80+ Platinum | 850w 80+ platinum | generic | - | technical_specs.wattage=user_text, technical_specs.efficiency=user_text | 0.698 | - |
| storage | 1TB NVMe | 1tb nvme | generic | - | technical_specs.capacity=user_text, technical_specs.interface=user_text | 1.3814 | - |
| storage | SSD 1TB | ssd 1tb | generic | - | technical_specs.capacity=user_text, technical_specs.type=user_text | 0.8949 | - |
| storage | NVMe 2TB | nvme 2tb | generic | - | technical_specs.capacity=user_text, technical_specs.interface=user_text | 0.6612 | - |
| storage | 500GB SATA SSD | 500gb sata ssd | generic | - | technical_specs.capacity=user_text, technical_specs.interface=user_text, technical_specs.type=user_text | 0.6166 | - |
| storage | NVMe 1TB PCIe 4.0 M.2 | nvme 1tb pcie 4.0 m.2 | generic | - | technical_specs.capacity=user_text, technical_specs.interface=user_text, technical_specs.form_factor=user_text | 0.763 | - |
| motherboard | B550M | b550m | family | b550m-am4-ddr4 | - | 1.9599 | - |
| motherboard | B550M DDR4 | b550m ddr4 | family | b550m-am4-ddr4 | - | 1.4447 | - |
| motherboard | B650 DDR5 | b650 ddr5 | family | b650-am5-ddr5 | - | 3.4041 | - |
| motherboard | B760M DDR4 | b760m ddr4 | family | b760m-lga1700-ddr4 | - | 1.9194 | - |
| motherboard | Z790 DDR5 | z790 ddr5 | family | z790-lga1700-ddr5 | - | 1.3873 | - |
| motherboard | AM5 B650 ATX DDR5 | am5 b650 atx ddr5 | family | b650-am5-ddr5 | - | 2.3857 | - |
| case | ATX | atx | generic | - | compatibility.supported_form_factors=user_text | 1.4296 | - |
| case | mATX | matx | generic | - | compatibility.supported_form_factors=user_text | 0.7498 | - |
| case | Mini-ITX GPU até 300mm | itx gpu ate 300mm | generic | - | compatibility.supported_form_factors=user_text, compatibility.max_gpu_length_mm=user_text | 1.0037 | - |

## Entradas ambíguas

| Categoria | Entrada | Motivo | Resultado |
|---|---|---|---|
| ram | 16GB ou 32GB DDR4 | alternative_range_or_negation, conflicting_capacity | unresolved |
| ram | DDR4 DDR5 32GB | conflicting_memory_type | unresolved |
| ram | 3200 3600 DDR4 16GB | conflicting_speed | unresolved |
| ram | 32GB 2x8GB DDR4 | conflicting_capacity | unresolved |
| psu | 650W 750W | conflicting_wattage | unresolved |
| psu | 500-650W | alternative_range_or_negation | unresolved |
| storage | 1TB 2TB NVMe | conflicting_capacity | unresolved |
| storage | 1TB SATA NVMe | conflicting_interface | unresolved |
| cpu | Ryzen 5600X ou 5600G | alternative_range_or_negation | unresolved |
| gpu | RTX 4070 RTX 4070 Super | multiple_models | unresolved |

## PCs (30 informais, incluindo 10 incompatíveis)

| # | Cenário | Esperado | Obtido | Reconhecidos | Catálogo/Derivado | Regras verificadas | Pendentes | Problemas | Tempo (ms) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Pedido PC 1 | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 0 | 40.917 |
| 2 | Pedido PC 2 | partial | partial | 7/7 | 2/5 | cpu_socket, ram_type, gpu_power, board_case | ram_slots, ram_capacity, gpu_case | 0 | 18.77 |
| 3 | Pedido PC 3 | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power, board_case | ram_slots, ram_capacity, gpu_case | 0 | 17.924 |
| 4 | Pedido PC 4 | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 0 | 24.825 |
| 5 | CPU sem tier | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 0 | 15.706 |
| 6 | CPU X | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 0 | 18.139 |
| 7 | CPU G | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 0 | 16.686 |
| 8 | PSU marca sem SKU | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 0 | 17.469 |
| 9 | DDR5 48GB | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power, board_case | ram_slots, ram_capacity, gpu_case | 0 | 18.797 |
| 10 | B760 DDR4 | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 0 | 18.379 |
| 11 | B760 DDR5 | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 0 | 19.701 |
| 12 | VRAM explícita sem SKU arbitrário | partial | partial | 7/7 | 2/5 | cpu_socket, ram_type | ram_slots, ram_capacity, gpu_power, board_case, gpu_case | 0 | 18.019 |
| 13 | SSD sem interface | partial | partial | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 0 | 17.469 |
| 14 | Família sem PSU recomendado | partial | partial | 7/7 | 2/5 | cpu_socket, ram_type | ram_slots, ram_capacity, gpu_power, board_case, gpu_case | 0 | 21.798 |
| 15 | Completo com campos explícitos 1 | compatible | compatible | 7/7 | 3/4 | cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case | - | 0 | 37.237 |
| 16 | Completo com campos explícitos 2 | compatible | compatible | 7/7 | 3/4 | cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case | - | 0 | 36.71 |
| 17 | Completo com campos explícitos 3 | compatible | compatible | 7/7 | 3/4 | cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case | - | 0 | 39.213 |
| 18 | Completo com campos explícitos 4 | compatible | compatible | 7/7 | 3/4 | cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case | - | 0 | 38.089 |
| 19 | Completo com campos explícitos 5 | compatible | compatible | 7/7 | 3/4 | cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case | - | 0 | 37.72 |
| 20 | Completo com campos explícitos 6 | compatible | compatible | 7/7 | 3/4 | cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case | - | 0 | 40.052 |
| 21 | Socket AM5 em AM4 | incompatible | incompatible | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 1 | 17.035 |
| 22 | Socket Intel em AM5 | incompatible | incompatible | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power, board_case | ram_slots, ram_capacity, gpu_case | 1 | 18.756 |
| 23 | DDR5 em placa DDR4 | incompatible | incompatible | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 1 | 21.093 |
| 24 | DDR4 em placa DDR5 | incompatible | incompatible | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power, board_case | ram_slots, ram_capacity, gpu_case | 1 | 31.495 |
| 25 | Fonte abaixo da GPU | incompatible | incompatible | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 1 | 23.881 |
| 26 | Outra fonte insuficiente | incompatible | incompatible | 7/7 | 3/4 | cpu_socket, ram_type, gpu_power | ram_slots, ram_capacity, board_case, gpu_case | 1 | 20.092 |
| 27 | RAM acima do limite SKU | incompatible | incompatible | 7/7 | 3/4 | cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power | board_case, gpu_case | 1 | 19.245 |
| 28 | Mais módulos que slots SKU | incompatible | incompatible | 7/7 | 3/4 | cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power | board_case, gpu_case | 1 | 23.505 |
| 29 | Gabinete com exclusão explícita | incompatible | incompatible | 7/7 | 3/4 | cpu_socket, ram_type, ram_capacity, gpu_power, board_case | ram_slots, gpu_case | 1 | 25.325 |
| 30 | GPU explicitamente maior que espaço | incompatible | incompatible | 7/7 | 3/4 | cpu_socket, ram_type, ram_capacity, gpu_power, board_case, gpu_case | ram_slots | 1 | 26.946 |

## Limitações deliberadas

- Slots de RAM, RAM máxima, comprimento de GPU, espaço máximo de GPU e formato de placa só são verificados quando vêm do SKU do catálogo ou do texto do usuário; família/modelo genéricos não os inventam.
- Lista positiva de formatos de gabinete (ex.: "ATX") não exclui outros formatos; só vale como prova de incompatibilidade com "apenas".
- Entradas com alternativas, faixas, negação ou valores conflitantes ficam sem resolução.
