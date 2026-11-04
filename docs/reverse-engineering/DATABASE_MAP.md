# PC2YOU — Mapa de bancos de dados

Inspeção **somente de código** (e de relatórios gerados em `reports/`). Nenhuma consulta foi feita a MongoDB/PostgreSQL reais.

## 1. MongoDB (`MONGO_DB`, padrão `orcapc_catalog`)

Collections encontradas no código (grep de `database[...]`/`db[...]`): `components`, `telegram_promotions`, `product_price_history`, `external_product_enrichment`, `ml_integration_state`, `telegram_service_status`, `price_alerts`, `notification_history`, `notification_dedup`, `telegram_notification_state`, `legacy_seed_commercial` (só scripts de auditoria, `scripts/audit_seed_commercial_data.py --apply`).

> Não existe collection chamada `price_history`. "Histórico de preços" = (a) coleção **`product_price_history`** (observações reais) e (b) campo embutido `components.price_history` (snapshots legados).

| Collection | Objetivo | Principais campos | Índices (criados no código) | Quem escreve | Quem lê |
|---|---|---|---|---|---|
| `components` | catálogo técnico (121 itens do seed: case 6, cooler 9, cpu 36, gpu 26, kit-ram 6, motherboard 14, psu 7, ram 7, storage 10) | `id`, `name`, `category`, `brand`, `image`, `description`, `technical_specs{}`, `compatibility{}`, `benchmark{gaming_score,workstation_score,ai_score}`, `prices[]` (vazio no seed), `price_history[]`, `real_image`, `images[]`, `external_enrichment.mercado_livre{}`, `last_external_price_*` | `uq_components_id` (único em `id`), `ix_components_category`, `ix_components_brand`, `ix_components_name` (`database.ensure_indexes`) | `seed.seed_components` (startup api-catalogo; só insere), admin `POST/PUT/DELETE /components`, `ml_service.refresh_*`, `ml_products.enrich`, scripts `sync_*` | api-catalogo, `commerce`, matcher (`repository.save` lê todo o catálogo), scripts; api-orcamentos via HTTP |
| `telegram_promotions` | uma mensagem de oferta por documento | `telegram{chat_id,chat_name,chat_username,message_id,message_url,sent_at}`, `raw_text`, `product{name,normalized_key,component_id,component_type,match_confidence,match_level,matched_by,conflicts,matcher_version,previous_component_id}`, `offer{store,price,original_price,coupon,url,url_source,valid_until,conditions{…},source,verified,state,coupon_status,product_match_*,captured_at,url_valid,store_key,resolved_url,url_kind,resolved_kind,resolved_store,link_status,link_hops,link_checked_at,manual_validation_status,manual_validated_at,manual_validated_by,verified_price,verification_source,verified_at}`, `links[]`, `equivalence_key`, `price_observation`, `status`, `created_at`, `processed_at`, `is_demo`, `notifications_processed_at`, `notification_retry_at` | `uq_telegram_chat_message` (único em chat_id+message_id); `ix_promotion_notifications` (created_at, notifications_processed_at) | collector (`save`, `_complete_links`, `resolve_link`, `refresh_quality`), `validate_promotion` (api-catalogo), notifier (campos de processamento), scripts de backfill/reprocess | `commerce.build_snapshot`, `PromotionSource.recent` (IA), bot, scripts |
| `product_price_history` | observações **reais** e verificadas de preço | `component_id`, `date`, `observed_at`, `price`, `source` (`telegram`/`mercado_livre_api`), `store`, `store_key`, `match_level`, `match_confidence`, `verified`, `equivalence_key`, `matcher_version`, `coupon`, `telegram{chat_id,message_id}`, `invalidated_by`, (ML) `item_id`, `day` | nenhum criado no código | `repository._save_observation`, `validate_promotion` (invalida), `ml_products.record_official_price` | `services.real_price_history`, `PromotionSource.history` (IA) |
| `external_product_enrichment` | cache 24 h da Product API do ML | `_id`=PRODUCT_ID, `product_id`, `catalog_product_id`, `name`, `brand`, `model`, `images[]`, `attributes`, `specs`, `domain_id`, `fetched_at`, `matches.<component_id>{status,basis,confidence,conflicts,brand_variant}`, `component_ids[]` | `_id` | `ml_products.MercadoLivreProductEnrichment` (via script) | `enrich`, relatórios |
| `ml_integration_state` | contadores/estado da integração ML | `_id:"state"`, `metrics.*`, `product_api`, `item_api`, `price_validation`, `ml_price_validation_capability`, `capability_checked_at`, `last_error`, `last_product_success` | `_id` | `ml_products.record_state` | `GET /integrations/mercado-livre/status` |
| `telegram_service_status` | heartbeat do coletor | `_id:"collector"`, `connected`, `source_count`, `updated_at` | `_id` | collector (`heartbeat`, a cada 30 s) | bot (`/status`) |
| `price_alerts` | alertas pessoais do bot | `telegram_user_id`, `query`, `normalized_terms`, `max_price`, `component_type`, `brands`, `ignored_brands`, `stores`, `ignored_stores`, `minimum_discount`, `enabled`, `created_at`, `updated_at` | `ix_alert_user_created`, `ix_alert_enabled_created` | bot (`AlertRepository`) | notifier |
| `notification_history` | entrega por (usuário, alerta, promoção) | `telegram_user_id`, `alert_id`, `promotion_id`, `status`, `claim_id`, `lease_until`, `retry_at`, `sent_at`, `telegram_message_id` | único `uq_notification_user_alert_promotion` | notifier | notifier |
| `notification_dedup` | supressão de oferta equivalente | `_id`=`user:alert:hash`, `status`, `claim_id`, `lease_until`, `expires_at` | TTL `ttl_equivalent_offer` (`expireAfterSeconds=0`) | notifier | notifier |
| `telegram_notification_state` | marco do worker | `_id:"worker"`, `started_at`, `next_send_at` | `_id` | notifier | notifier |

### Exemplos sanitizados (estrutura real, valores fictícios)

```json
// components
{ "id": "rtx-5060-ti-8gb", "name": "GeForce RTX 5060 Ti 8GB", "category": "gpu", "brand": "NVIDIA",
  "technical_specs": {"memory": "8GB GDDR7"}, "compatibility": {"min_psu_watts": 550},
  "benchmark": {"gaming_score": 0, "workstation_score": 0, "ai_score": 0},
  "prices": [], "price_history": [],
  "external_enrichment": {"mercado_livre": {"product_id": "MLB00000000", "match_status": "matched",
      "external_conflict": false, "images": ["https://http2.mlstatic.com/..."], "specs": {"memory_size": "8 GB"}}} }
```
```json
// telegram_promotions
{ "_id": "ObjectId", "telegram": {"chat_id": -1001234567890, "message_id": 4242, "sent_at": "2026-11-04T12:00:00Z"},
  "raw_text": "Placa de vídeo RTX 5060 Ti 8GB ... Por R$ 2.789,00 no PIX ...",
  "product": {"name": null, "component_id": "rtx-5060-ti-8gb", "match_level": "high", "match_confidence": 0.93, "conflicts": []},
  "offer": {"store": "KaBuM", "price": "2789.00", "coupon": null, "url": "https://loja.exemplo/produto/1",
            "conditions": {"payment_methods": ["PIX"], "conditions_version": 2},
            "verified": true, "state": "active", "source": "telegram"},
  "status": "parsed", "created_at": "2026-11-04T12:00:05Z" }
```
```json
// product_price_history
{ "component_id": "rtx-5060-ti-8gb", "price": 2789.0, "source": "telegram", "verified": true,
  "match_level": "high", "match_confidence": 0.93, "date": "2026-11-04T12:00:00.000Z",
  "equivalence_key": "sha256…", "telegram": {"chat_id": -1001234567890, "message_id": 4242} }
```
```json
// price_alerts
{ "telegram_user_id": 111111111, "query": "RTX 5070", "normalized_terms": ["rtx","5070"],
  "max_price": "3800.00", "stores": ["kabum"], "enabled": true }
```
Observação: valores monetários são persistidos como `Decimal128` (`repository.bson_values`).

### Números reais (relatórios datados, não consulta ao vivo)
- `reports/commerce-live-validation.json` (2026-11-03): 121 componentes; `mongo_promotions` 1.421; 210 publicadas; 92 ativas; lojas Amazon e Mercado Livre nos exemplos.
- `reports/telegram-final-metrics.json`: 1.484 promoções no Mongo; 160 publicadas; 69 ativas, 91 históricas; lojas: Kabum 44, Mercado Livre 26, Pichau 21, Amazon 11, …
- `reports/promotion-conditions-apply2.json`: 1.685 promoções (o volume cresce; estes números **não** são iguais entre relatórios porque foram gerados em momentos diferentes).
- `reports/post-backfill-quality-audit.json`: 654 promoções auditadas; recalculado low 541 / high 110 / medium 3.

## 2. PostgreSQL (`POSTGRES_*`, padrão `orcapc_db`)

| Tabela | Dono | Colunas | Restrições | Migration |
|---|---|---|---|---|
| `users` | api-usuarios (`models.User`) | `id` PK, `name` varchar(120) idx, `email` varchar(255) **único** idx, `password_hash` varchar(255) (bcrypt/passlib) | — | `api-usuarios/alembic/versions/20260713_0001_initial_users_favorites.py` |
| `favorites` | api-usuarios (`models.Favorite`) | `id`, `user_id` FK→users `ON DELETE CASCADE`, `component_id` varchar(120) idx | único (`user_id`,`component_id`) `uq_favorite_user_component` | idem |
| `budgets` | api-orcamentos (`models.Budget`) | `id`, `user_id` int idx (**referência lógica**, sem FK), `name` varchar(120), `total_price` Numeric(12,2), `performance` JSON, `created_at` | `ck_budget_total_nonnegative` | `api-orcamentos/alembic/versions/20260713_0001_budget_schema.py` |
| `budget_items` | api-orcamentos (`models.BudgetItem`) | `id`, `budget_id` FK→budgets `ON DELETE CASCADE`, `component_id`, `name`, `category`, `quantity`, `best_price`, `store`, `url` | `ck_budget_item_quantity (1..16)`, `ck_budget_item_price_nonnegative` | idem |

- Migrations rodam no start (`api-usuarios/entrypoint.sh`: `alembic upgrade head` com 20 tentativas; `api-orcamentos/entrypoint.py`). A migration de orçamentos contém `UPDATE` de saneamento (`total_price`, `quantity`, `best_price`) — **não executada nesta análise**.
- Queries: SQLAlchemy ORM em `crud.py` e `services.py`; **SQL cru** em `api-orcamentos/services.ensure_user_exists`: `SELECT 1 FROM users WHERE id = :user_id` (lê a tabela de outro serviço no **mesmo banco**).

### Perguntas explícitas
**O PostgreSQL é usado exclusivamente para usuários/login?** **Não.** Ele guarda (1) usuários/senhas, (2) **favoritos** e (3) **orçamentos** (`budgets`, `budget_items`) da API de orçamentos.
**Existe outra funcionalidade dependente do PostgreSQL além de autenticação?** **Sim:** favoritos (`api-usuarios`), orçamentos salvos (`/budgets*`, `/build/finalize`, `/performance/{id}`, página `/budget/:id`) e o health `ready` de `api-orcamentos`. **Não dependem dele:** catálogo, ofertas/promoções, Telegram, Mercado Livre, **análise de PC e upgrades por IA**, nem o wizard `/build` até o passo de salvar.
**Ressalva operacional importante:** as rotas `/ai/*` não usam sessão de banco, mas vivem **dentro do processo `api-orcamentos`**, cujo `entrypoint.py` executa `alembic upgrade head` (exige PostgreSQL) antes de subir o uvicorn, e o compose faz `api-orcamentos` depender de `postgres-db` e `api-usuarios` saudáveis. Logo, **no estado atual, para a IA subir é preciso PostgreSQL** (mesmo que a rota não o consulte). Uma versão de apresentação sem PostgreSQL exigiria separar/ajustar esse boot (análise futura — não feito aqui).
