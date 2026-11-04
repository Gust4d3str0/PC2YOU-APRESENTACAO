# PC2YOU — Mapa funcional

Rastreio: FUNCIONALIDADE → FRONTEND → ENDPOINT → FUNÇÃO BACKEND → BANCO/SERVIÇO → RESPOSTA. "Login?" = exige JWT. Estado: **ativo** (funciona com os serviços de pé), **opcional** (depende de integração/configuração), **restrito** (capacidade bloqueada externamente), **script** (só por CLI), **sem UI** (backend sem tela).

## 1. Tabela completa de funcionalidades

| # | Funcionalidade | Frontend (arquivo) | Rota frontend | Endpoint | Backend (arquivo → função) | Banco | Externo | Login? | Estado |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Cadastro | `Register.jsx` | `/register` | `POST /auth/register` | `api-usuarios/main.py → register` → `crud.create_user` | PG `users` | — | não | ativo |
| 2 | Login | `Login.jsx` | `/login` | `POST /auth/login` | `main.login` → `auth.create_access_token` | PG | — | não | ativo |
| 3 | Logout | `Header.jsx` | (qualquer) | — (limpa `localStorage`) | — | — | — | — | ativo |
| 4 | Favoritar/desfavoritar | `FavoriteButton.jsx` | `/`, `/components/:id`, `/favorites` | `POST /favorites`, `DELETE /favorites/{u}/{c}` | `main.add_favorite/remove_favorite` → `crud.create_favorite/delete_favorite` | PG `favorites` | — | **sim** | ativo |
| 5 | Listar favoritos | `Favorites.jsx`, `Home.jsx`, `ComponentDetails.jsx` | `/favorites` | `GET /favorites/{user_id}` + `GET /components/{id}` por item | `main.read_favorites` | PG + Mongo | — | **sim** | ativo |
| 6 | Catálogo / busca / filtro por categoria | `Home.jsx`, `ComponentCard.jsx` | `/` (`?q=`) | `GET /commerce/catalog?q&category` | `api-catalogo/main.py → commerce_catalog` → `commerce.snapshot` | Mongo `components`, `telegram_promotions` | — | não | ativo |
| 7 | Promoções (abas ativas/histórico, paginação 4) | `PromotionSection.jsx` | `/` | `GET /promotions?status&category&limit&skip` | `main.public_promotions` → `commerce.build_snapshot/dedupe/listing_order` | Mongo | — | não | ativo |
| 8 | Detalhes do componente | `ComponentDetails.jsx` | `/components/:id` | `GET /components/{id}` | `services.get_component` → `_public_component` | Mongo | — | não | ativo |
| 9 | Comparação de ofertas / melhor oferta (geral e condicional) | `OfferComparison.jsx`, `PromotionSection.jsx` | `/components/:id`, `/` | `GET /components/{id}/offers` | `main.component_offers` → `commerce.best_offer/best_general_offer/best_conditional_offer` | Mongo | — | não | ativo |
| 10 | Resumo e histórico de preços (tabela + gráfico) | `PriceTable.jsx`, `PriceChart.jsx` | `/components/:id` | `GET /components/{id}/price-summary`, `/price-history` | `services.price_summary`, `real_price_history` | Mongo `components`, `product_price_history` | — | não | ativo |
| 11 | Atualizar preços reais (botão) | `ComponentDetails.jsx` | `/components/:id` | `POST /components/{id}/refresh-real-prices` | `ml_service.refresh_component_real_prices` (cooldown) | Mongo | Mercado Livre | **sim** | opcional |
| 12 | Validar oferta manualmente | `OfferValidation.jsx` | `/components/:id` | `POST /promotions/{id}/validation` | `main.validate_promotion` | Mongo (escreve) | — | **sim** | ativo |
| 13 | Especificações externas (ML) | `ExternalSpecs.jsx` | `/components/:id` | (embutido em `GET /components/{id}`) | `external_enrichment.mercado_livre` | Mongo | ML (via script) | não | opcional |
| 14 | Imagens (proxy ML) | `HardwareImage.jsx`, `api.js` | todas | `GET /images/proxy` | `main.proxy_image` | — | `*.mlstatic.com` | não | ativo |
| 15 | **Analisar meu PC (IA)** | `AnalyzePC.jsx`, `PCAnalysisResult.jsx` | `/analyze-pc` | `POST /ai/analyze-pc` | `ai_routes.analyze_pc` → `ai_context.build_context` → `AIService.analyze_pc` | Mongo (via catálogo) | **Gemini** | não | opcional (`AI_ENABLED`) |
| 16 | **Recomendar upgrades (IA v2)** | `UpgradeRecommendations.jsx` | `/analyze-pc` (após análise) | `POST /ai/recommend-upgrades` | `ai_routes.recommend_pc_upgrades` → `build_upgrade_bundle`, `recommend_upgrades` | Mongo (read), catálogo | Gemini | não | opcional |
| 17 | Wizard de montagem (próximas opções compatíveis) | `Build.jsx` | `/build` | `POST /build/next-options` | `api-orcamentos/main.py → next_options` → `compatibility.check_components/next_category` | — (catálogo HTTP) | — | não | ativo |
| 18 | Checagem de compatibilidade | (usada em `Build.jsx`) | `/build` | `POST /compatibility/check` | `main.check` → `compatibility.check_components` | — | — | não | ativo (sem UI direta) |
| 19 | Finalizar montagem → orçamento | `Build.jsx` | `/build` → `/budget/:id` | `POST /build/finalize` | `main.finalize` → `services.create_or_update_budget` | PG `budgets`, `budget_items` | — | **sim** | ativo |
| 20 | Ver orçamento + desempenho estimado | `BudgetResult.jsx`, `BudgetSummary.jsx`, `PerformanceBox.jsx` | `/budget/:id` | `GET /budgets/{id}` (desempenho no corpo) | `main.read_budget` → `services.budget_to_response`, `performance.estimate_performance` | PG | — | **sim** | ativo |
| 21 | CRUD de orçamentos / performance avulsa | — | — | `POST/PUT/DELETE /budgets*`, `GET /budgets/user/{id}`, `GET /performance/{id}` | `main.*` | PG | — | **sim** | sem UI |
| 22 | Preços de componente (APIs de leitura) | — | — | `GET /components/{id}/prices`, `/best-price` | `main.read_prices/read_best_price` | Mongo | — | não | sem UI |
| 23 | Administração do catálogo | — | — | `POST/PUT/DELETE /components`, `POST /seed`, `POST /components/sync-ml-prices` | `main.*` | Mongo | ML | **admin key** | sem UI |
| 24 | Coleta Telegram → promoções | — | — | (processo, não HTTP) | `collector.process_message` → `parse_message` → `PromotionRepository.save` | Mongo | Telegram | — | opcional (profile `telegram`) |
| 25 | Resolução de links de oferta | — | — | (background) | `repository.resolve_link` → `destinations.resolve_redirects` | Mongo | lojas (redirect) | — | opcional |
| 26 | Bot de alertas de preço | — | Telegram | (Bot API) | `AlertHandlers`, `NotificationWorker` | Mongo `price_alerts` etc. | Telegram | — | opcional |
| 27 | Enriquecimento ML (Product API) | `ExternalSpecs`, imagens | `/components/:id` | (script) | `scripts/enrich_mercado_livre_products.py` → `MercadoLivreProductEnrichment` | Mongo `external_product_enrichment` | ML | — | script |
| 28 | Status da integração ML | — | — | `GET /integrations/mercado-livre/status` | `ml_products.integration_status` | Mongo `ml_integration_state` | — | não | sem UI |
| 29 | Price/Item API ML (validação oficial de preço) | — | — | (sonda por script) | `MercadoLivrePriceCapability/Validator` | Mongo | ML | — | **restrito (403)** |
| 30 | Auditorias/backfills/reprocessamento | — | — | — | `scripts/*.py` | Mongo | — | — | script |
| 31 | Saúde dos serviços | — | — | `GET /health*` (3 APIs) | `health*` | PG/Mongo | — | não | ativo |

**Contagem:** 31 funcionalidades relevantes (20 visíveis ao usuário ou diretamente demonstráveis + 11 de infraestrutura/pipeline/scripts).

## 2. Rotas do frontend (`frontend/src/App.jsx`, React Router v6, `BrowserRouter`)

| URL | Componente | Objetivo | APIs chamadas | Estado principal | Filhos importantes | Login | Classe |
|---|---|---|---|---|---|---|---|
| `/` | `pages/Home.jsx` | catálogo, busca, destaques de promoção | `GET /commerce/catalog`; `GET /favorites/{id}` (se logado) | `components, favoriteIds, loading, error, reloadKey`; query `q` | `Header`, `PromotionSection`, `ComponentCard`, `EmptyState`, `LoadingState` | não (favoritos opcionais) | **ESSENCIAL** |
| `/components/:id` | `pages/ComponentDetails.jsx` | ficha técnica, ofertas, preços, favoritar | `GET /components/{id}`, `/price-summary`, `/price-history`, `/offers`; favoritos; `POST …/refresh-real-prices` | `component, commerce, favorite, priceSummary, priceHistory, refreshing, priceNotice…` | `OfferComparison`, `PriceTable`, `PriceChart`, `ExternalSpecs`, `HardwareImage`, `FavoriteButton`, `OfferValidation` | não (ações sim) | **ESSENCIAL** |
| `/analyze-pc` | `pages/AnalyzePC.jsx` | análise por IA + upgrades | `POST /ai/analyze-pc`, `POST /ai/recommend-upgrades` | `values, usage, resolution, refreshRate, games, budget, result, submittedPayload, error, loading` (+ `AbortController`) | `PCAnalysisResult`, `UpgradeRecommendations` | não | **ESSENCIAL** |
| `/build` | `pages/Build.jsx` | wizard de montagem | `POST /build/next-options`, `POST /build/finalize` | `selected, options, selectedDetails, nextCategory, ramQuantity, loading, error` | `LoadingState` | finalizar **sim** | **IMPORTANTE** |
| `/budget/:id` | `pages/BudgetResult.jsx` | resultado do orçamento | `GET /budgets/{id}` | `budget`, loading | `BudgetSummary`, `PerformanceBox` | **sim** | **IMPORTANTE** |
| `/favorites` | `pages/Favorites.jsx` | favoritos | `GET /favorites/{id}`, `GET /components/{id}` × N | `components, favoriteIds, loading` | `ComponentCard` | **sim** | **SECUNDÁRIA** |
| `/login` | `pages/Login.jsx` | entrar | `POST /auth/login` | email, password, erro | `Header` | — | **AUTENTICAÇÃO** |
| `/register` | `pages/Register.jsx` | criar conta | `POST /auth/register`, `/auth/login` | name, email, password | `Header` | — | **AUTENTICAÇÃO** |

Não há rotas administrativas nem internas no frontend, nem rota protegida (guards): a proteção é por ação.

## 3. Componentes de frontend com comportamento significativo

| Componente | Props | Estado | APIs | Responsabilidade |
|---|---|---|---|---|
| `Header.jsx` | — | `darkMode`, busca | — | navegação, tema (`localStorage.darkMode`), busca (`/?q=`), login/logout |
| `PromotionSection.jsx` | `category`, `mode` (`active`/`recent`) | `rows, bestId, page, data, error, copied, open` | `GET /promotions`, `GET /components/{id}/offers` | cartões de promoção, paginação de 4, cupom copiável (`copyText`), destino da URL (`destinationLabel`), rótulos honestos |
| `OfferComparison.jsx` | `componentId`, `onLoad` | `data, error` | `GET /components/{id}/offers` | melhor geral × melhor condicional, tabela de ofertas, histórico |
| `OfferValidation.jsx` | `offer`, `onChanged` | `busy, message` | `POST /promotions/{id}/validation` | botões "funcionando / não funciona mais" (só com token e `source:'telegram'`) |
| `PCAnalysisResult.jsx` | `result` | — | — | exibe análise, compatibilidade (veredito do **backend**), candidatos |
| `UpgradeRecommendations.jsx` | `payload` (mesmo da análise) | `includePromotions, result, loading, error` (+AbortController) | `POST /ai/recommend-upgrades` | pede upgrades, exibe preço/fonte/condições/promoção (links validados por `safeOfferUrl`) |
| `ComponentCard.jsx` | `component, favorite, onFavoriteChange` | — | — | cartão de catálogo com melhor oferta, imagem, favorito |
| `FavoriteButton.jsx` | `componentId`, estado | — | favoritos | alterna favorito, redireciona a `/login` sem usuário |
| `ExternalSpecs.jsx` | `component` | — | — | specs do ML quando `matched` |
| `HardwareImage.jsx` | `component` | índice do candidato | `/images/proxy` | tenta o próximo candidato de `imageCandidates` ao falhar |
| `PriceChart.jsx` / `PriceTable.jsx` | histórico / resumo | — | — | gráfico e tabela |
| `BudgetSummary.jsx` / `PerformanceBox.jsx` | `budget` | — | — | itens, total, desempenho estimado |
| `utils/commerce.js` | — | — | — | `currentOffers`, `offerLabel`, `announcedAgo`, `imageCandidates`, `safeLink`, `copyText` |

## 4. FUNCIONALIDADES DESCOBERTAS (código funcional pouco ou nada citado no pedido/README principal)

- **FUNCIONALIDADE DESCOBERTA — Wizard de montagem `/build` + motor de compatibilidade + estimativa de desempenho** (`api-orcamentos/compatibility.py`, `performance.py`): `check_components`, `next_category`; passos `cpu → cooler → motherboard → ram → storage → gpu → psu → case`; só oferece opções compatíveis com o já escolhido (`next_options`).
- **FUNCIONALIDADE DESCOBERTA — Bot Telegram de alertas pessoais** (`services/telegram_bot/`): comandos `/acompanhar`, `/alertas`, `/pausar`, `/remover`, `/ofertas`, filtros por marca/loja/desconto, entrega idempotente com lease, deduplicação por oferta equivalente (6 h).
- **FUNCIONALIDADE DESCOBERTA — Proxy de imagens** com proteção SSRF (`/images/proxy`).
- **FUNCIONALIDADE DESCOBERTA — Resolução de redirects segura** (`destinations.py`, proteção contra hosts não públicos).
- **FUNCIONALIDADE DESCOBERTA — Arquitetura de validadores** (`OfferValidator`, `TelegramOfferValidator`, `MercadoLivreOfferValidator`, `MercadoLivrePriceValidator`): preparada para validação oficial de preço.
- **FUNCIONALIDADE DESCOBERTA — `catalog_audit` / `catalog_enrichment`** (`services/`) e arquivos `seed_identity_*.json`, `catalog_enrichment_*.json`: auditoria e sincronização de identidade/enriquecimento do seed (scripts `sync_catalog_*`, `preview_catalog_*`).
- **FUNCIONALIDADE DESCOBERTA — Rastreamento de requisição** (`X-Request-ID` em middleware das 3 APIs e repassado por `catalog_client`).
- **FUNCIONALIDADE DESCOBERTA — Scripts de demonstração de IA** (`scripts/ai_analyze_pc_demo.py`, `ai_upgrade_demo.py`, `ai_structured_output_debug.py`) e `scripts/telegram_demo.py` (simulação offline; `--enqueue` grava promoção fictícia com `is_demo`).
- **FUNCIONALIDADE DESCOBERTA — Duas rotas de preço do catálogo quase sem consumidores** (`/prices`, `/best-price`) e `GET /users` que só devolve o próprio usuário.

## 5. Essencialidade dos módulos

| Classe | Módulos |
|---|---|
| **ESSENCIAL AO PRODUTO** | `api-catalogo` (catálogo, `commerce.py`, `services.py`, `seed.py`), MongoDB, `services/product_matching`, frontend (`Home`, `ComponentDetails`, `AnalyzePC`), `api-orcamentos` rotas `/ai/*` + `ai_context*`, `services/ai` |
| **IMPORTANTE** | Telegram collector (fonte das ofertas reais), `api-orcamentos` wizard/compatibilidade/performance, `PromotionSection`/`OfferComparison`, `destinations.py` |
| **OPCIONAL** | Mercado Livre (Product API/enriquecimento), bot de alertas, favoritos, `ExternalSpecs`, proxy de imagens, resolver de links |
| **ADMINISTRATIVO** | `POST/PUT/DELETE /components`, `/seed`, `/components/sync-ml-prices`, `X-Admin-Key`, `integration_status`, validação manual |
| **AUTENTICAÇÃO** | `api-usuarios` inteira, `Login.jsx`, `Register.jsx`, `Header` (parte), `auth.py` das 3 APIs, PostgreSQL `users` |
| **DESENVOLVIMENTO** | `tests/` (1.131 testes), `scripts/*` (auditoria/backfill/demo), `reports/`, `docs/` antigos, `.venv*`, `eslint.config.js` |
| **LEGADO** | `ml_service.py` (busca/ofertas ML antigas, com `base_price` ignorado no seed), campos `price_history` embutido em `components`, aliases `working/not_working` de validação, `unverified_prices`, `seed` com `prices: []` |
