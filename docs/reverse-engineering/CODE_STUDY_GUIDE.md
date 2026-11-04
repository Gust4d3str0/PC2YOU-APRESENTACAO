# PC2YOU — Guia de estudo do código

Ordem sugerida: visão geral → frontend → FastAPI → Mongo → matcher → IA → Telegram → Mercado Livre → Docker. Todos os caminhos são relativos a `PC2YOU/`.

## Prioridades de estudo

**PRIORIDADE 1** (explicam o produto e a IA)
- `services/ai/service.py`, `services/ai/provider.py`, `services/ai/prompts.py`, `services/ai/schemas.py`, `services/ai/upgrades.py`, `services/ai/prose.py`
- `api-orcamentos/ai_routes.py`, `ai_context.py`, `ai_upgrade_context.py`
- `services/product_matching/matcher.py`, `normalization.py`, `offers.py`
- `api-catalogo/commerce.py`
- `services/telegram_collector/parser.py`, `repository.py`
- `frontend/src/pages/AnalyzePC.jsx`, `components/UpgradeRecommendations.jsx`

**PRIORIDADE 2**
- `services/product_matching/quality.py`, `promotions.py`, `destinations.py`, `ml_ids.py`
- `api-catalogo/main.py`, `services.py`, `ml_products.py`
- `services/telegram_collector/collector.py`, `links.py`
- `api-orcamentos/compatibility.py`, `performance.py`, `services.py`
- `frontend/src/utils/commerce.js`, `api.js`, `pages/Home.jsx`, `ComponentDetails.jsx`, `components/PromotionSection.jsx`
- `docker-compose.yml`

**PRIORIDADE 3**
- `services/telegram_bot/*`, `api-usuarios/*`, `api-catalogo/seed.py`, `ml_commerce.py`, `ml_service.py`, `scripts/*`, `services/ai/contract.py`, `diagnostics.py`, `config.py`

## Passo a passo

### 1. Visão geral
- **Abrir:** `docs/reverse-engineering/ARCHITECTURE.md`, `docker-compose.yml`.
- **Conceitos:** microsserviços FastAPI, dois bancos, código compartilhado copiado nas imagens, JWT compartilhado.
- **Perguntas possíveis:** *Por que Mongo e Postgres?* (catálogo/promoções são documentos flexíveis; usuários/orçamentos são relacionais). *Como os serviços se comunicam?* (frontend → 3 APIs por HTTP; orçamentos → catálogo por HTTP; ambos leem Mongo/PG diretamente em casos pontuais). *O que acontece se o Telegram parar?* (catálogo e IA seguem; ofertas envelhecem para `stale`).

### 2. Frontend (React 18 + Vite + axios + React Router v6)
- **Abrir:** `src/App.jsx` (rotas), `src/api.js` (3 clientes axios, interceptor JWT, `proxiedImageUrl`), `pages/AnalyzePC.jsx`, `components/PromotionSection.jsx`, `utils/commerce.js`.
- **Estudar:** `AnalyzePC.submit` (payload, `AbortController`, tratamento de 422), `offerLabel` (linguagem honesta: "anunciada", nunca "ativa"), `imageCandidates`.
- **Conceitos:** estado local sem Redux, login em `localStorage`, ausência de rotas protegidas.
- **Perguntas:** *Onde o token é anexado?* (`api.js`, interceptor em todos os clientes). *Por que o resultado da IA não mostra nomes escritos pelo modelo?* (backend injeta nomes e preços dos candidatos).

### 3. FastAPI
- **Abrir:** `api-catalogo/main.py` (middleware `X-Request-ID`, `startup`, rotas), `api-orcamentos/main.py`, `api-usuarios/main.py`, `dependencies.py`/`auth.py`.
- **Funções:** `commerce_catalog`, `public_promotions`, `component_offers`, `validate_promotion`, `proxy_image` (`_validate_proxy_url`), `finalize`, `next_options`.
- **Conceitos:** `Depends`, Pydantic (`extra="forbid"`), JWT com `PyJWT`, CORS com origens explícitas, healthchecks live/ready, Alembic.
- **Perguntas:** *Qual a diferença entre `get_current_user` do catálogo e do usuário?* (o do catálogo só valida o token; o de usuários consulta o banco). *Por que a IA não exige login?* (decisão do projeto: `docs/AI.md`; risco de custo).

### 4. Mongo
- **Abrir:** `api-catalogo/database.py` (índices), `seed.py`, `services.py` (`_public_component`), `docs/reverse-engineering/DATABASE_MAP.md`.
- **Funções:** `ensure_indexes`, `seed_components`, `real_price_history`, `PromotionRepository.save` (`$setOnInsert` + upsert).
- **Conceitos:** upsert idempotente, índice único composto, TTL index (`notification_dedup`), `Decimal128`.
- **Perguntas:** *Como evita promoções duplicadas?* (índice único chat+mensagem; `equivalence_key`; `commerce.dedupe`). *Preço do seed aparece?* (não: `prices: []` e `source=seed` é ignorado).

### 5. Matcher
- **Abrir:** `matcher.py` (`features`, `compare_product`, `match_product`), `normalization.py`, `quality.py` (`price_quality`), `PRODUCT_MATCHER.md`.
- **Conceitos:** normalização, conflitos duros, pontuação por sinais, tetos, níveis High ≥ 0,85 / Medium ≥ 0,65.
- **Perguntas:** *Por que "RTX 5060 Ti" sem VRAM não casa?* (`variant_ambiguous`: 8 GB e 16 GB). *Por que "Ryzen 7 7800X3D" sem "AMD" dá Medium?* (teto 0,80 por faltar marca). *Score é probabilidade?* (não, heurística).

### 6. IA
- **Abrir:** `AI_FLOW.md`, depois `ai_routes.py` → `ai_context.build_context` → `service.run_cached` → `provider.generate` → `_validate_analysis` → `prose.validate_prose`.
- **Conceitos:** structured output (JSON schema), prompt de sistema, contexto "confiável × não confiável", cache/lock/rate limit, validação semântica pós-LLM, defesa contra prompt injection.
- **Perguntas:** *O modelo decide compatibilidade?* (não, o backend). *O que impede o modelo de inventar uma peça?* (`candidate_id` com `enum` no schema + validação). *Por que o texto não pode ter números?* (`validate_prose`: evita preços/FPS inventados). *E se o Gemini falhar?* (mapeamento de erros; sem retry/fallback).

### 7. Telegram
- **Abrir:** `TELEGRAM_FLOW.md`, `collector.process_message`, `parser.parse_message`, `offers.extract_conditions/evaluate_offer`, `destinations.resolve_redirects`, `repository.save`.
- **Conceitos:** Telethon (conta de usuário), idempotência, parser conservador ("desconhecido = None"), SSRF, status derivado em leitura.
- **Perguntas:** *Quando uma oferta vira "confirmada"?* (só com validação manual ≤ 6 h). *Como lida com cupom/condições?* (campos `conditions`, melhor oferta geral × condicional).

### 8. Mercado Livre
- **Abrir:** `MERCADO_LIVRE.md`, `ml_products.py` (`MercadoLivreTokenManager`, `MercadoLivreApi`, `MercadoLivreProductNormalizer`, `evaluate_match`, `MercadoLivreProductEnrichment`), `ml_ids.py`.
- **Conceitos:** OAuth com refresh rotativo, PRODUCT_ID × ITEM_ID, cache 24 h, capacidade × veredito (403).
- **Perguntas:** *Por que o preço não é validado pelo ML?* (Item/Price API retorna 403 para terceiros). *Como as imagens do ML entram?* (enriquecimento aprovado pelo matcher → `resolve_image`).

### 9. Docker
- **Abrir:** `docker-compose.yml`, `*/Dockerfile`, `api-usuarios/entrypoint.sh`, `api-orcamentos/entrypoint.py`.
- **Conceitos:** healthchecks, `depends_on: service_healthy`, profiles, volumes nomeados, build com contexto na raiz para copiar `services/`.
- **Perguntas:** *Por que `api-orcamentos` depende de três serviços?* (Postgres, catálogo, usuários). *Onde ficam sessão do Telegram e tokens ML?* (volumes `telegram_sessions`, `ml_tokens`).

## Funções importantes (por que estudar)

| Arquivo | Função | Responsabilidade | Entrada → Saída | Por que estudar |
|---|---|---|---|---|
| `services/product_matching/matcher.py` | `compare_product` | pontuar produto × componente | dict produto/componente → `MatchResult` | coração do matching: conflitos, pesos, tetos |
| `services/product_matching/matcher.py` | `match_product` | escolher componente do catálogo | produto + catálogo → `MatchResult` | trata ambiguidade (`variant_ambiguous`) |
| `services/product_matching/offers.py` | `extract_conditions` | ler condições do texto | texto, cupom, data → dict `conditions` | regex honestas ("None = desconhecido") |
| `services/product_matching/offers.py` | `evaluate_offer` | status comercial | oferta, agora → `{status, eligible…}` | regra de frescor/validade/confirmação |
| `services/product_matching/destinations.py` | `resolve_redirects` | seguir redirects com segurança | URL → dict | SSRF, limites, cache |
| `services/telegram_collector/parser.py` | `parse_message`, `extract_prices` | texto → oferta estruturada | texto → dict | heurísticas de preço/cupom |
| `services/telegram_collector/repository.py` | `PromotionRepository.save` | persistir idempotente | documento → bool | upsert + enriquecimento |
| `api-catalogo/commerce.py` | `build_snapshot`, `best_offer`, `dedupe`, `resolve_image` | leitura comercial pública | Mongo → snapshot | junta tudo que o frontend vê |
| `api-orcamentos/ai_context.py` | `enrich`, `check_compatibility`, `build_context` | contexto confiável da IA | request → contexto | o que o Gemini recebe |
| `api-orcamentos/ai_upgrade_context.py` | `build_upgrade_bundle`, `normalized_promotions`, `prices` | candidatos, ofertas e evidências | payload → bundle | IA v2 = matcher + ofertas |
| `services/ai/service.py` | `run_cached`, `_validate_analysis` | cache, limites, validação semântica | contexto → resposta | segurança do uso do LLM |
| `services/ai/provider.py` | `GeminiProvider.generate` | chamada ao Gemini + erros | schema/contexto → dict | SDK, JSON schema, mapeamento de erros |
| `services/ai/prose.py` | `validate_prose` | impedir invenções no texto | texto → ok/violação | barreira anti-alucinação |
| `api-orcamentos/compatibility.py` | `check_components` | regras de compatibilidade | componentes → `{compatible,…}` | base do wizard e da IA |
| `api-catalogo/ml_products.py` | `MercadoLivreTokenManager.refresh` | OAuth rotativo | refresh token → novos tokens persistidos | segurança/concorrência |
| `api-catalogo/ml_products.py` | `evaluate_match` | casar produto ML com componente | normalizado + componente → status | reuso do matcher |

## Trechos de código bons para uma futura apresentação (candidatos; nada implementado)

Todos reais e sem segredos; ver arquivo/linha para extrair.

1. **FastAPI** — rota enxuta de IA com mapeamento de erro: `api-orcamentos/ai_routes.py:62-75` (`analyze_pc`, `AIError → HTTPException`).
2. **FastAPI** — dependência JWT: `api-catalogo/dependencies.py:14-33` (`get_current_user`).
3. **IA** — structured output: `services/ai/provider.py:37-41` (`temperature=0.2`, `response_mime_type`, `response_json_schema`).
4. **IA** — schema dinâmico com `enum` dos candidatos: `services/ai/contract.py:12-30` (`analysis_schema`).
5. **IA** — regra de orçamento no prompt: `services/ai/prompts.py` (trecho "Modelos de upgrade específicos só podem ser escolhidos por candidate_id…").
6. **IA** — trava + cache + rate limit: `services/ai/service.py:32-62` (`run_cached`).
7. **Matcher** — níveis e pesos: `matcher.py:8-10` e `matcher.py:121-156`.
8. **Matcher** — normalização: `normalization.py:13-22`.
9. **MongoDB** — upsert idempotente: `repository.py:36-52` (`save`) e índice único (`ensure_indexes`).
10. **Telegram** — parser de preço/cupom: `parser.py:45-86`; condições: `offers.py:110-130`.
11. **Mercado Livre** — refresh de token com rotação: `ml_products.py:106-135`; tratamento de 403: `ml_products.py:225-230`, `413-433`.
12. **React** — rótulos honestos: `frontend/src/utils/commerce.js` (`offerLabel`); chamada de IA com cancelamento: `AnalyzePC.jsx:56`.
13. **Docker** — `depends_on: condition: service_healthy` em `docker-compose.yml` (`api-orcamentos`).

Sanitização: nenhum snippet acima contém chaves, tokens, senhas, e-mails ou telefones; ao copiar, **não** incluir `.env`.
