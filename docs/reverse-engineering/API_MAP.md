# PC2YOU — Mapa de endpoints (FastAPI)

Fonte: decoradores `@app.*` / `@router.*` de `api-usuarios/main.py`, `api-catalogo/main.py`, `api-orcamentos/main.py`, `api-orcamentos/ai_routes.py`. Total: **12 + 23 + 14 = 49 rotas**. Legenda de autenticação: **—** pública; **JWT** `Authorization: Bearer` (HS256, assinado por api-usuarios); **ADMIN** header `X-Admin-Key` (`ADMIN_API_KEY`, `hmac.compare_digest`).

## 1. api-usuarios (:8001) — PostgreSQL

Auth: `auth.get_current_user` (OAuth2PasswordBearer → decodifica JWT, **busca o usuário no Postgres**), `auth.require_owner(user_id, current_user)` (403 se não for o próprio).

| METHOD | ROUTE | Função (`main.py`) | Entrada | Saída | Banco | Auth | Frontend |
|---|---|---|---|---|---|---|---|
| GET | `/health`, `/health/live`, `/health/ready` | `health*` | — | status (`ready` faz `SELECT 1`) | PG | — | healthcheck Docker |
| POST | `/auth/register` | `register` | `UserCreate` (name, email, password) | `UserResponse` 201; 400 se e-mail duplicado | PG `users` | — | `Register.jsx` |
| POST | `/auth/login` | `login` | `LoginRequest` | `{user, access_token, token_type}`; 401 | PG | — | `Login.jsx`, `Register.jsx` |
| GET | `/users` | `read_users` | skip/limit | **apenas o próprio usuário** (`[current_user]`) | PG | JWT | não usado |
| GET | `/users/{user_id}` | `read_user` | — | `UserResponse` | PG | JWT + dono | não usado |
| PUT | `/users/{user_id}` | `update_user` | `UserUpdate` | `UserResponse` | PG | JWT + dono | não usado |
| DELETE | `/users/{user_id}` | `delete_user` | — | 204 | PG | JWT + dono | não usado |
| POST | `/favorites` | `add_favorite` | `FavoriteCreate` (user_id, component_id) | `FavoriteResponse` | PG `favorites` | JWT + dono | `FavoriteButton.jsx` |
| GET | `/favorites/{user_id}` | `read_favorites` | — | lista | PG | JWT + dono | `Home.jsx`, `ComponentDetails.jsx`, `Favorites.jsx` |
| DELETE | `/favorites/{user_id}/{component_id}` | `remove_favorite` | — | 204 | PG | JWT + dono | `FavoriteButton.jsx` |

## 2. api-catalogo (:8002) — MongoDB (`components` + coleções comerciais)

| METHOD | ROUTE | Função | Entrada | Saída | Banco | Externo | Auth | Frontend |
|---|---|---|---|---|---|---|---|---|
| GET | `/health`, `/health/live`, `/health/ready` | `health*` | — | status (ready faz ping Mongo) | Mongo | — | — | Docker, `catalog_client.health` |
| GET | `/images/proxy?url=` | `proxy_image` | URL (máx. 2048) | bytes da imagem | — | `*.mlstatic.com` (https, host público, limite `IMAGE_PROXY_MAX_BYTES`, redirects validados — `_validate_proxy_url`, `_download_image`) | — | `api.js: proxiedImageUrl` |
| POST | `/components` | `create_component` | `ComponentCreate` | `Component` 201 / 409 | Mongo | — | **ADMIN** | — |
| GET | `/components` | `read_components` | `category`, `q`, `brand`, `skip`, `limit` (≤ `CATALOG_MAX_PAGE_SIZE`=100) | `list[Component]` (via `services._public_component`) | Mongo | — | — | `api-orcamentos` (HTTP) |
| POST | `/components/batch` | `read_components_batch` | `{component_ids}` (≤100) | lista | Mongo | — | — | `catalog_client.get_components` |
| GET | `/components/{id}` | `read_component` | — | `Component` ou 404 | Mongo | — | — | `ComponentDetails.jsx`, `Favorites.jsx` |
| PUT / DELETE | `/components/{id}` | `update_component` / `delete_component` | `ComponentUpdate` | `Component` | Mongo | — | **ADMIN** | — |
| GET | `/components/{id}/prices` | `read_prices` | — | `prices` crus do documento | Mongo | — | — | — |
| GET | `/components/{id}/best-price` | `read_best_price` | — | `services.best_price` ou 404 | Mongo | — | — | — |
| GET | `/components/{id}/price-summary` | `read_price_summary` | — | `services.price_summary` | Mongo | — | — | `api.js: fetchPriceSummary` |
| GET | `/components/{id}/price-history` | `read_price_history` | — | `history` (campo do documento, `source: real_observations`) | Mongo | — | — | `api.js: fetchPriceHistory` |
| POST | `/seed` | `seed` | — | `{inserted}` | Mongo | — | **ADMIN** | — |
| POST | `/components/{id}/sync-ml-price` | `sync_ml_price` | — | resultado `refresh_component_real_prices` (cooldown `REFRESH_COOLDOWN_SECONDS`) | Mongo | ML (busca de ofertas) | **JWT** (qualquer token válido; sem consulta ao banco) | — |
| POST | `/components/{id}/refresh-real-prices` | `refresh_real_prices` | — | idem | Mongo | ML | **JWT** | `api.js: refreshRealPrices` → botão de atualizar preços em `ComponentDetails.jsx:183` (sem token → 401) |
| POST | `/components/sync-ml-prices` | `sync_all_ml_prices` | — | `{total, updated, failed}` | Mongo | ML | **ADMIN** | — |
| GET | `/promotions` | `public_promotions` | `status` (`active|recent|all`), `component_id`, `category`, `source`, `limit` ≤100, `skip` | `{items,total,counts,refresh_seconds:45}` | Mongo (`telegram_promotions`, `components`) via `commerce.snapshot` | — | — | `PromotionSection.jsx` |
| GET | `/components/{id}/offers` | `component_offers` | — | `{best_offer, best_general_offer, best_conditional_offer, offers, history[:100]}` | Mongo | — | — | `OfferComparison.jsx`, `PromotionSection.jsx` |
| POST | `/promotions/{promotion_id}/validation` | `validate_promotion` | `OfferValidation{status: valid|invalid|unknown|working|not_working, observed_price?}` | `{id, manual_validation_status, status, state, updated_documents}` | Mongo (**escreve** `telegram_promotions`, `product_price_history`) | — | **JWT** | `OfferValidation.jsx` (visível só com token) |
| GET | `/commerce/catalog?q&category` | `commerce_catalog` | texto ≤120 | `{items,total}` componentes + `current_offers`, `best_*_offer`, `offers_count` | Mongo | — | — | `Home.jsx` |
| GET | `/integrations/mercado-livre/status` | `mercado_livre_status` | — | status seguro (sem token): `configured, authorized, product_api, item_api, price_validation, metrics...` | Mongo `ml_integration_state` | — | — | nenhum (diagnóstico) |

Middleware: `request_context_middleware` (propaga/gera `X-Request-ID`). CORS com origens explícitas (`CORS_ORIGINS`; `*` é recusado em `config._origins`).

**Não existe rota PC2YOU `GET /products/{PRODUCT_ID}`**: isso é a rota da API do Mercado Livre, chamada por `ml_products.MercadoLivreApi.get_product`. Ver [MERCADO_LIVRE.md](MERCADO_LIVRE.md).

## 3. api-orcamentos (:8003) — PostgreSQL + Mongo (leitura) + Gemini

Auth: `auth.get_current_user` (JWT local, `sub` inteiro positivo; **não** consulta o banco), `require_payload_owner`, e depois `services.ensure_user_exists` (SQL em `users`).

| METHOD | ROUTE | Função | Entrada | Saída | Banco | Externo | Auth | Frontend |
|---|---|---|---|---|---|---|---|---|
| GET | `/health`, `/health/live`, `/health/ready` | `health*` | — | status (ready: Postgres + catálogo) | PG | catálogo | — | Docker |
| POST | `/budgets` | `create_budget` | `BudgetCreate` | `BudgetResponse` 201 | PG | catálogo (batch) | JWT + dono | — (frontend usa `/build/finalize`) |
| GET | `/budgets/{budget_id}` | `read_budget` | — | `BudgetResponse` | PG | — | JWT + dono | `BudgetResult.jsx` |
| GET | `/budgets/user/{user_id}` | `read_user_budgets` | — | lista | PG | — | JWT + dono | — |
| PUT | `/budgets/{budget_id}` | `update_budget` | `BudgetUpdate` | `BudgetResponse` | PG | catálogo | JWT + dono | — |
| DELETE | `/budgets/{budget_id}` | `delete_budget` | — | `BudgetResponse` | PG | — | JWT + dono | — |
| POST | `/compatibility/check` | `check` | `CompatibilityCheck` (*_id) | `{compatible, errors, warnings...}` | — | catálogo (batch) | — | — |
| POST | `/build/next-options` | `next_options` | `NextOptionsRequest{selected_components}` | `{done, next_category, options[+best_price], compatibility}` | — | catálogo (list por categoria) | — | `Build.jsx` |
| POST | `/build/finalize` | `finalize` | `BuildFinalize{user_id,name,components,quantities}` | `BudgetResponse` 201 | PG | catálogo | **JWT** + dono | `Build.jsx` |
| GET | `/performance/{budget_id}` | `performance` | — | `performance.estimate_performance` | PG | catálogo | JWT + dono | — (desempenho já vem no `BudgetResponse`) |
| POST | `/ai/analyze-pc` | `ai_routes.analyze_pc` | `AnalyzePCRequest` | `AnalyzePCResponse` | — (catálogo via HTTP) | **Gemini** | **— (sem login)** | `AnalyzePC.jsx` |
| POST | `/ai/recommend-upgrades` | `ai_routes.recommend_pc_upgrades` | `RecommendUpgradesRequest` (= AnalyzePC + `include_promotions`) | `RecommendUpgradesResponse` | Mongo (read-only) + catálogo | **Gemini** | **— (sem login)** | `UpgradeRecommendations.jsx` |

Erros de IA: `AIError` → `HTTPException(status, detail={code,message})` (+ `Retry-After: 60` se 429); `ValueError/KeyError/TypeError` → 503 (`catalog_invalid` / `upgrade_context_invalid`).

## 4. Outros "serviços" (sem HTTP)

| Processo | Interface | Detalhe |
|---|---|---|
| `telegram-collector` | CLI `auth | list-chats | import-history | listen` | ver [TELEGRAM_FLOW.md](TELEGRAM_FLOW.md) |
| `telegram-bot` | Telegram Bot API | comandos `/start /status /ajuda /meuid /acompanhar /alertas /remover /pausar /ofertas /cancelar` (`bot.py:63`, `handlers.py:288-294`) |
| scripts | CLI | `scripts/README.md` |

## 5. Rastreamento ponta a ponta das funcionalidades centrais

### 5.1 Análise de PC
`AnalyzePC.jsx submit` → `budgetsApi.post('/ai/analyze-pc')` (axios, timeout 130 s) → FastAPI `ai_routes.analyze_pc` → validação Pydantic `AnalyzePCRequest` (`services/ai/schemas.py`) → `service.ensure_available()` → `ai_context.build_context` (`enrich` → `catalog_client.search_components` → HTTP api-catalogo `GET /components/{id}` ou `GET /components?category&q`; `check_compatibility`) → `AIService.analyze_pc` → `GeminiProvider.generate` → validações → `AnalyzePCResponse` → `PCAnalysisResult.jsx`. Detalhe em [AI_FLOW.md](AI_FLOW.md).

### 5.2 Recomendação de upgrade
`UpgradeRecommendations.jsx recommend` → `POST /ai/recommend-upgrades` → `ai_routes.recommend_pc_upgrades` → `ai_upgrade_context.build_upgrade_bundle` (catálogo por categoria `gpu/cpu/ram/kit-ram/psu`; `PromotionSource.recent/history` no Mongo; `normalized_promotions` → `enrich_promotion` → matcher; `prices`, `history_stats`, `replacement_compatibility`) → `ai.upgrades.recommend_upgrades` → Gemini → `validate_choices` → `RecommendUpgradesResponse`.

### 5.3 Consulta de catálogo
`Home.jsx` → `catalogApi.get('/commerce/catalog', {params:{q,category}})` → `main.commerce_catalog` → `commerce.snapshot(db)` (cache 30 s: `build_snapshot`) → itens com `current_offers`, `best_current_offer`, `best_general_offer`, `best_conditional_offer` → `ComponentCard.jsx`. Detalhe técnico direto: `GET /components/{id}` → `services.get_component` → `_public_component` (une preços reais do catálogo + ofertas Telegram vigentes; seed ignorado).

### 5.4 Promoções
`PromotionSection.jsx` → `GET /promotions?status=active|recent&category&limit=4&skip` → `main.public_promotions` → `commerce.snapshot` → `dedupe`/`listing_order` → JSON paginado (45 s de refresh sugerido).

### 5.5 Detalhes de componente
`ComponentDetails.jsx` → `GET /components/{id}` + `GET /favorites/{user}` (se logado) + `OfferComparison` → `GET /components/{id}/offers` + `PriceChart/PriceTable` (`price-summary`/`price-history`) + `ExternalSpecs` (`external_enrichment.mercado_livre`).
