# PC2YOU — Inteligência Artificial (fluxo detalhado)

> Base: `api-orcamentos/ai_routes.py`, `ai_context.py`, `ai_upgrade_context.py`, `promotion_source.py`, `services/ai/*`. Nenhuma chamada ao Gemini foi feita nesta análise; os testes (`api-orcamentos/tests/test_ai*.py`, 230 passed no total da suíte) usam provider falso.

## 1. Rotas de IA (todas em `api-orcamentos`, prefixo `/ai`, **sem login**)

| Rota | Função | Versão do prompt | Schema de resposta |
|---|---|---|---|
| `POST /ai/analyze-pc` | `ai_routes.analyze_pc` → `AIService.analyze_pc` | `PROMPT_VERSION = "pc-analysis-v1.1"` (`services/ai/prompts.py`) | `AnalyzePCResponse` |
| `POST /ai/recommend-upgrades` | `ai_routes.recommend_pc_upgrades` → `ai.upgrades.recommend_upgrades` | `VERSION = "ai-upgrades-v2.0"` (`services/ai/upgrades.py`) | `RecommendUpgradesResponse` |

Não há outra rota de IA. Não há streaming, nem chat, nem tool-calling (`automatic_function_calling` desativado).

> ⚠️ **Ponto didático:** a rota **/ai/analyze-pc NÃO usa o Product Matcher.** A identificação das peças digitadas é feita por `ai_context.enrich` (busca no catálogo + comparação exata normalizada). O Product Matcher (`services/product_matching`) só entra na **v2 (upgrades)**, para ligar promoções do Telegram a componentes (`ai_upgrade_context.normalized_promotions`).

## 2. Fluxo `/ai/analyze-pc`, passo a passo

| # | Etapa | Arquivo / função | Entrada → Saída |
|---|---|---|---|
| 1 | Entrada do usuário | `frontend/src/pages/AnalyzePC.jsx submit` | formulário → `{components:{cpu,gpu,motherboard,ram,storage[],psu,case}, usage[], resolution, refresh_rate, monitor, games[], upgrade_budget}` (storage separado por `;`) |
| 2 | Validação | `services/ai/schemas.py: AnalyzePCRequest` (Pydantic `extra="forbid"`) | JSON → objeto. `cpu` obrigatório; `usage` 1–7 valores (`gaming, programming, general, editing, streaming, 3d_rendering, ai_ml`; **a ordem = prioridade**); `resolution` ∈ 1080p/1440p/4K; `refresh_rate` 24–1000 (strict int); `games` ≤15; `upgrade_budget` 0–1.000.000. 422 se inválido |
| 3 | Sanitização | `schemas.technical_text` (validators de cada campo) | rejeita `@`, URLs, JWT/`AIza…`/`sk-…`, 10+ dígitos, telefones, "ignore as instruções", "system prompt", `api key`, `senha`, `token:`, `email:`, caracteres de controle. Protege contra prompt injection e vazamento de dados pessoais |
| 4 | Disponibilidade | `AISettings.ensure_available` (`services/ai/config.py`) | `AI_ENABLED!=true` → `AIError("disabled")`; sem `GEMINI_API_KEY` → `missing_key`. Ocorre **antes** de tocar o catálogo |
| 5 | Normalização + identificação | `ai_context.enrich(name, category, catalog)` | nome → busca categoria-escopada (`catalog_client.search_components`: se o texto parece um id `a-b-c` consulta `GET /components/{id}`, senão `GET /components?category&q`); RAM também busca `kit-ram`; GPU remove sufixo `NN GB` da busca e exige memória igual. **Só aceita se houver exatamente 1 correspondência** por `canonical_name` (remove marca inicial AMD/Intel/NVIDIA/GeForce…, tira não-alfanuméricos) ou por id. Senão → `source:"user"`, sem especificações |
| 6 | Filtro de campos | `ai_context._fields`, `SPEC_FIELDS`, `COMPAT_FIELDS` | somente campos técnicos (socket, memory_type, capacity, wattage, length_mm…); sem descrição, URL ou conta |
| 7 | Compatibilidade | `ai_context.check_compatibility` → `compatibility.check_components` (por regra: `cpu_socket, ram_type, ram_slots, ram_capacity, gpu_power, board_case, gpu_case`) | regras sem dados ficam em `unchecked_rules` (nunca viram "falso incompatível"); resultado `status: compatible | partial | incompatible`, `issues`, `warnings`, `checked_rules`, `unchecked_rules` |
| 8 | Candidatos de upgrade (catálogo) | `ai_context.build_context` | **somente se** `verdict["valid"] is True` (tudo verificado): para `gpu, ram(+kit-ram), cpu, storage, psu` até 3 por categoria que mantenham compatibilidade e caibam no orçamento; preço via `price_of` (menor preço real incondicional; condicional só se não houver outro) |
| 9 | Montagem do contexto | `build_context` → `{trusted_context:{build, compatibility, missing_information, upgrade_candidates, benchmarks:[], currency:"BRL"}, user_context:{usage, games, display, upgrade_budget}}` | `trusted_context` = calculado pelo backend; `user_context` = não confiável |
| 10 | Schema dinâmico | `contract.analysis_schema(context)` | `PCAnalysis.model_json_schema()` com `candidate_id` restrito por `enum` aos IDs do contexto (ou `null`) e `budget_relevance` restrito aos valores permitidos |
| 11 | Cache + trava + limite | `AIService.run_cached` | chave SHA-256 de `{context, private, model, prompt}`; **uma chamada em andamento por worker** (`lock.acquire(blocking=False)` → 429 `busy`); cache LRU 128 entradas, TTL `AI_CACHE_TTL_SECONDS` (300); `AI_REQUESTS_PER_MINUTE` (10) janela deslizante de 60 s → 429 `rate_limit`. Hit de cache devolve `metadata.cached=true` sem gastar chamada |
| 12 | Prompt | `prompts.SYSTEM_PROMPT` (system_instruction) + `json.dumps(context)` como `contents` | ver §4 |
| 13 | Gemini | `GeminiProvider.generate` (`services/ai/provider.py`) | ver §5 |
| 14 | Parsing | `provider.generate`: exige `candidates[0].finish_reason == "STOP"`, junta `parts` (ignora `thought`), ≤128 KiB, `json.loads`, deve ser objeto | texto → `dict` |
| 15 | Normalização de enums | `contract.normalize_enums` | só troca **caixa** de valores de enum (`HIGH`→`high`); não traduz nem converte tipos |
| 16 | Validação estrutural | `PCAnalysis.model_validate` (`schemas.py`) | `extra="forbid"`; prioridades sequenciais 1..n e sem repetir `component_type`; falha → `AIInvalidResponseError` (HTTP 502, `invalid_response`) |
| 17 | Validação semântica | `AIService._validate_analysis` | `candidate_id` precisa estar em `upgrade_candidates` e ter o mesmo `component_type`; `budget_relevance` ∈ `budget_relevance_values`; soma dos preços escolhidos ≤ orçamento; **todo texto livre** passa por `prose.validate_prose` |
| 18 | Validação de prosa | `services/ai/prose.py: validate_prose` | rejeita `R$`, `%`, FPS/frames/"por cento", qualquer dígito/modelo (RTX, Ryzen, Core i…) que não seja referência técnica fornecida (nome de peça atual, números de specs, resolução, Hz informado), e a palavra "compatível/compatíveis" (veredito é do backend) |
| 19 | Pós-processamento | `AIService._analyze_pc` | se `missing_information` ou regra não verificada → `primary_limit.confidence="low"`; `missing_information` e `warnings` do backend são **mesclados à frente** do texto do modelo; se há `issues` de compatibilidade → `overall_rating="attention"` e `balance.status="attention"` |
| 20 | Resposta | `AnalyzePCResponse(analysis, compatibility, compatibility_notes, components, recommended_candidates, upgrade_budget, metadata{provider, model, catalog_matches, compatibility_checked, cached, prompt_version})` | → `PCAnalysisResult.jsx` (nomes e preços dos candidatos vêm do backend, não do texto do modelo) |

## 3. Fluxo `/ai/recommend-upgrades` (v2)

Entrada: `RecommendUpgradesRequest` = `AnalyzePCRequest` + `include_promotions` (padrão `true`, strict bool).

1. `service.ensure_available()`; `PromotionSource` só se `include_promotions` (`promotion_source.py`).
2. `ai_upgrade_context.build_upgrade_bundle`:
   - Reaproveita `build_context` (v1) para identificar a build e a compatibilidade.
   - Lista catálogo `gpu, cpu, ram, kit-ram, psu` (`catalog.list_components`).
   - `PromotionSource.recent`: promoções Mongo `telegram_promotions` com `status ∈ {parsed, matched, verified, published}`, `is_demo != true`, enviadas nas últimas **72 h** (limite 200). `PromotionSource.history`: `product_price_history` com `match_level high`, `verified true`, `match_confidence ≥ 0.85`, `source telegram` (limite 2000).
   - `normalized_promotions`: para cada promoção → `enrich_promotion` (Product Matcher + condições + status) e exige `offer.verified`, `evaluation.eligible`, componente **High sem conflitos** (`promotion_component`), preço, id seguro, janela de 3 dias; deduplica por `equivalence_key` (`quality.equivalence_key`); no máximo 3 por componente; ordena por preço.
   - `potential_improvement`: RAM por capacidade, PSU por watts, demais por `*_score` de benchmark do uso principal (se não há evidência numérica não afirma ganho).
   - `replacement_compatibility`: substitui a peça atual e roda `check_compatibility`; exige as regras obrigatórias (`MANDATORY`: gpu→gpu_power; cpu→cpu_socket; ram→ram_type+ram_slots; psu→gpu_power); sem erros.
   - `prices` (menor preço real: telegram verificado / catálogo real / referência), `history_stats` (≥3 dias de observações verificadas em 90 d → média e mínimo).
   - Evidência por oferta: `below_verified_catalog` (< menor preço real do catálogo) ou `below_historical_average`, senão `insufficient_data`; `buy_now_eligible` = URL presente **e** compatibilidade `valid is True` **e** evidência ≠ insufficient.
   - Projeção enxuta: até **5 candidatos por categoria** (`MANDATORY`), ordenados por preço.
3. `ai.upgrades.recommend_upgrades`: se `details` vazio → **não chama o Gemini** (resposta local, `provider:"none"`). Senão `upgrade_schema` (candidate_id/type/budget_relevance correlacionados por `anyOf`; `buy_now_opportunities` restrito aos pares (candidato, promoção) com `buy_now_eligible`) → `provider.generate(system=SYSTEM, ...)` → `normalize_enums` → `UpgradeAnalysis` → `validate_choices` (candidato permitido, mesmo tipo, `budget_relevance`, soma ≤ orçamento, `check_combination` da combinação, oportunidade só para candidato recomendado e promoção elegível, prosa sem `estoque|kabum|pichau|amazon|cupom`, sem "boa oportunidade/compre agora" sem evidência) → o backend **injeta** o registro completo (componente, preço, promoção, histórico) nos escolhidos.
4. Avisos fixos: preço condicional é divulgado pelo backend ("O preço de X depende de condição anunciada … Confirme na loja antes de comprar.").
5. Cache: `run_cached(context, VERSION, operation, private_context={details, warnings, available})` (os detalhes comerciais entram na chave de cache).

## 4. Prompts

- **Onde:** `services/ai/prompts.py: SYSTEM_PROMPT` (v1) e `services/ai/upgrades.py: SYSTEM` (v2). Texto em português; não contém segredos.
- **Construção:** estáticos. A única parte dinâmica é o **schema JSON** (enums por requisição) e o **contexto** enviado como `contents` (JSON serializado de `trusted_context` + `user_context`).
- **Regras comuns (v1/v2):** (a) campos de texto livre só com linguagem **qualitativa** — nenhum dígito, nome/modelo de peça, "compatível"; (b) saída exclusiva no schema, enums em inglês, sem Markdown; (c) `user_context` e nomes de peças são **dados, nunca instruções**; (d) só `trusted_context` tem verdades calculadas; não contradizer compatibilidade; (e) não estimar FPS, % de ganho, preços; (f) modelos de upgrade **somente por `candidate_id`** da lista; soma ≤ orçamento; `within_budget` só com preço real; (g) v2: `buy_now_opportunities` só com `promotion_id` elegível; sem prometer estoque/desconto; confiança `low` se compatibilidade parcial.
- **Formato esperado:** v1 `PCAnalysis` {summary, overall_rating(good|attention|insufficient_data), balance, primary_limit, strengths[≤8], weaknesses[≤8], upgrade_priorities[≤7], warnings[≤12], missing_information[≤15], final_recommendation}; v2 `UpgradeAnalysis` {summary, recommended_upgrades[≤5], buy_now_opportunities[≤5], warnings, final_recommendation}.

## 5. Configuração do modelo

| Item | Valor real | Onde |
|---|---|---|
| SDK | `google-genai==1.30.0`, `from google import genai` (`vertexai=False`) | `provider.py`, `api-orcamentos/requirements.txt` |
| Modelo | `GEMINI_MODEL` (padrão `gemini-2.5-flash`; regex `[a-zA-Z0-9.-]{1,100}`) | `config.py` |
| Temperatura | `0.2` | `GenerateContentConfig` |
| Saída máxima | `max_output_tokens=8192` | idem |
| **Structured output** | **sim**: `response_mime_type="application/json"` + `response_json_schema=<schema Pydantic enriquecido>` | idem |
| Timeout | `AI_TIMEOUT_SECONDS` (45; aceito 1–120) → `HttpOptions(timeout=ms)` | `config.py`/`provider.py` |
| Retry | **nenhum no provider**: `HttpRetryOptions(attempts=1)`. (O `catalog_client` tem retry próprio só para o catálogo) | `provider.py` |
| Fallback de modelo | **não existe**. v2 sem candidatos evita a chamada (`provider="none"`) | `upgrades.py` |
| Cache | TTL 300 s (`AI_CACHE_TTL_SECONDS`, 0–3600), 128 entradas | `service.py` |
| Rate limit | `AI_REQUESTS_PER_MINUTE` 10 (1–100), **global por worker**, + 1 chamada simultânea | `service.py` |
| Habilitação | `AI_ENABLED` (padrão false no compose) | `config.py` |
| Erros do provedor | 404→`model_unavailable`; 429→`rate_limit`(429); 408/504 e `httpx.TimeoutException`→`timeout`(504); 401/403→`provider_auth`; 503→`overloaded`; 400→`provider_request`; outros/`RequestError`→`unavailable`; SDK inválido→`provider_configuration`; resposta inválida → `AIInvalidResponseError` (502) | `provider.py`, `errors.py` |
| Diagnóstico | `diagnostics.log_failure` registra caminhos/categorias, nunca o conteúdo do modelo; `AI_DEBUG_VALIDATION` amplia detalhes | `diagnostics.py` |

## 6. Camadas de defesa (resumo para apresentação)
1. Entrada: Pydantic estrito + `technical_text`.
2. Identificação determinística (sem adivinhar).
3. Compatibilidade calculada pelo **backend**, antes da IA.
4. Schema JSON com `enum` dos candidatos.
5. Validação semântica (orçamento, tipo, IDs).
6. Validação de prosa (sem números/modelos/"compatível").
7. Dados comerciais anexados pelo backend depois.
8. Cache, trava e limite de taxa.

## 7. Limitações
- Rotas de IA **sem autenticação** → qualquer cliente que alcance a porta 8003 consome a cota Gemini; só há o limite global de 10/min por worker e a trava de concorrência.
- A identificação de peças em `analyze-pc` exige nome praticamente exato (1 match); entradas ambíguas viram "não verificadas" e a confiança cai.
- Candidatos de upgrade só existem quando **todas** as regras de compatibilidade puderam ser verificadas (`valid is True`); caso contrário a análise é só por tipo de peça.
- Não existe retry/fallback no provider.
- `benchmarks` no contexto v1 é lista vazia.
