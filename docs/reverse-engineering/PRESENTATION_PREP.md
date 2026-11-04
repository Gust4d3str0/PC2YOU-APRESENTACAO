# PC2YOU — Material disponível para a apresentação (somente levantamento)

Não cria apresentação nem rota `/apresentacao`. Reúne o que já existe no código para uma **segunda etapa**.

## 1. O que uma versão acadêmica simplificada precisaria (sem criar nada agora)

| Demonstrar | Módulos aparentemente necessários |
|---|---|
| Catálogo | `api-catalogo` (`main.py`, `services.py`, `seed.py`, `database.py`, `config.py`, `schemas.py`, `commerce.py`), MongoDB, `services/product_matching` (copiado em `product_matching/`), frontend `Home`/`ComponentDetails`/`Header` |
| Análise de PC + IA | `api-orcamentos/ai_routes.py`, `ai_context.py`, `catalog_client.py`, `compatibility.py`, `settings.py`; `services/ai`; chave Gemini; catálogo no ar |
| Ofertas | `commerce.py` + coleção `telegram_promotions` (dados já coletados ou o simulador `scripts/telegram_demo.py --enqueue`), `PromotionSection`, `OfferComparison` |
| Upgrades (IA v2) | `ai_upgrade_context.py`, `promotion_source.py`, `services/ai/upgrades.py`, `upgrade_schemas.py`, `product_matching` |
| Telegram | `services/telegram_collector` (+ conta Telegram) e/ou `services/telegram_bot`; sem conta: simulador offline |
| Matcher | `services/product_matching` (puro, sem rede: demonstrável com os exemplos de [PRODUCT_MATCHER.md](PRODUCT_MATCHER.md)) |
| MongoDB | contêiner `mongo-db` + `components`, `telegram_promotions`, `product_price_history` |
| Mercado Livre | `ml_products.py` (+ credenciais); sem credenciais: mostrar `ml_product_map.json`, `external_product_enrichment` já gravado e o status |

Respostas:
- **`api-usuarios` seria necessária?** Não para nenhuma das demonstrações acima (catálogo, análise, IA, ofertas, matcher, Telegram, ML). Seria necessária só para login, favoritos e orçamentos salvos. Observação: hoje `api-orcamentos` **espera** `api-usuarios` no `depends_on` do compose e a tabela `users` para `ensure_user_exists` (rotas de orçamento); as rotas `/ai/*` não usam isso.
- **PostgreSQL seria necessário?** Para os recursos de produto, não (IA, catálogo e ofertas usam Mongo). **Mas** o processo `api-orcamentos` roda `alembic upgrade head` ao subir (`entrypoint.py`), então, sem alterar o boot, ele ainda exige PostgreSQL. Decisão da etapa 2: manter só o Postgres (sem `api-usuarios`) ou isolar a IA.
- **Rotas de login que poderiam ser ignoradas:** `POST /auth/register`, `POST /auth/login`, `GET/PUT/DELETE /users*`, `POST/GET/DELETE /favorites*`, `POST /build/finalize`, `/budgets*`, `/performance/{id}` e, no catálogo, `POST /promotions/{id}/validation`, `POST /components/{id}/sync-ml-price|refresh-real-prices`.

## 2. Features mais demonstráveis (ao vivo)

1. **Analisar meu PC** (sugestão de entrada: `Ryzen 5 5600` + `RTX 3060 12 GB`, ambos existem no seed; **não executado nesta análise**, pois a IA não foi chamada) → mostra compatibilidade calculada **antes** da IA, análise estruturada e candidatos do catálogo. Requer `AI_ENABLED=true` e chave.
2. **Matcher ao vivo**: colar um texto de promoção e mostrar score/nível/conflitos (executável offline; ver exemplos reais na tabela abaixo).
3. **Pipeline Telegram offline**: `scripts/telegram_demo.py` (sem rede nem banco por padrão) e `parse_message` com a fixture `services/tests/fixtures/messages.json`.
4. **Melhor oferta geral × condicional** em `/components/:id` (se houver ofertas no Mongo).
5. **Wizard `/build`**: só escolhe peças compatíveis (sem login até finalizar).
6. **Status honesto de ofertas**: "Anunciada recentemente / Oferta com condição / Confirmada / Expirada".

## 3. Diagramas já prontos

`ARCHITECTURE.md` §5 (arquitetura geral) e §6.1–6.4 (análise de PC, Telegram→frontend, Mercado Livre, login) estão em Mermaid.

## 4. Dados e números reais disponíveis

| Dado | Valor | Fonte |
|---|---|---|
| Componentes no catálogo | **121** (gpu 26, cpu 36, mobo 14, ram 7, kit-ram 6, storage 10, psu 7, cooler 9, case 6) | `api-catalogo/seed.py` (executado) |
| Endpoints | **49** (12 usuários + 23 catálogo + 14 orçamentos/IA) | `API_MAP.md` |
| Testes | **1.131** (11 + 230 + 377[+1 skip] + 485 + 28) | execução de 2026-11-04 |
| Matcher: níveis | High ≥ 0,85 / Medium ≥ 0,65; versão `product-match-v1.0` | `matcher.py` |
| Promoções coletadas (snapshots) | 654 auditadas em 2026-11-01 (high 110 / medium 3 / low 541 recalculado); 1.421 → 1.484 → 1.685 documentos em relatórios sucessivos | `reports/post-backfill-quality-audit.json`, `commerce-live-validation.json`, `telegram-final-metrics.json`, `promotion-conditions-apply2.json` |
| Condições detectadas (1.685 promoções) | 762 cupom, 256 PIX, 56 assinatura, 39 pedido mínimo, 23 só-app, 919 condicionais | `reports/promotion-conditions-apply2.json` |
| Lojas nas promoções publicadas | Kabum 44, Mercado Livre 26, Pichau 21, Amazon 11, Shopee 6, AliExpress 3, Terabyte 1, não identificada 48 | `reports/telegram-final-metrics.json` |
| Links | 75 de 160 com destino "produto" | idem |
| Exemplos de melhor preço (2026-11-03) | RTX 5070: 13 ofertas, R$ 4.369; RTX 5060 Ti 8 GB: 11 ofertas, R$ 2.789 | `reports/commerce-live-validation.json` |
| IA | `gemini-2.5-flash`, temp 0,2, ≤ 8192 tokens, cache 300 s, 10 req/min | `services/ai/*` |

Observação: números dos relatórios são **fotografias datadas** (o banco muda); antes de apresentar, reconsultar via API/MongoDB.

## 5. Exemplos reais do matcher (executados)

| Texto | Resultado |
|---|---|
| Placa de Vídeo RTX 5060 Ti 8GB Gigabyte Windforce OC | `rtx-5060-ti-8gb`, 0,93, High |
| Processador AMD Ryzen 7 7800X3D 4.2GHz AM5 | `ryzen-7-7800x3d`, 0,97, High |
| Placa de vídeo RTX 5060 Ti (sem VRAM) | sem match, `variant_ambiguous` |
| Kit Upgrade Ryzen 5 5600 + B550M | sem match, `multiple_products` |
| Memória Kingston Fury Beast 16GB DDR5 5600MHz | `ram-16gb-ddr5`, 0,74, Medium |
| Ryzen 7 7800X3D sem "AMD" (oferta Telegram) | 0,80 Medium (não publicada); com "AMD" 0,93 High |

## 6. Limitações que devem ser explicadas

1. Preços exibidos são **anunciados** (Telegram), não validados pelo marketplace: a Price/Item API do ML retorna 403 → "restrito".
2. Ofertas envelhecem: após 72 h deixam de ser elegíveis; só validação manual (6 h) gera "confirmada".
3. Matcher é heurístico e conservador (pode deixar de casar ofertas válidas).
4. IA exige `AI_ENABLED` e chave; sem retry/fallback; só recomenda peças de candidatos calculados; candidatos de upgrade só aparecem se todas as regras de compatibilidade foram verificáveis.
5. `/ai/*` sem autenticação (custo/abuso), rate limit apenas global por worker.
6. Dependência do Telegram para dados novos; sem coletor, o catálogo permanece mas ofertas vão ficando históricas.
7. `api-orcamentos` exige PostgreSQL para subir mesmo para a IA.
8. Frontend sem rotas protegidas; validação manual aceita qualquer usuário logado.
9. Seed não traz preços (por design); catálogo de 121 itens não cobre todo o mercado.
10. Dois clientes ML coexistem (duplicação).

## 7. Ideias para uma futura rota `/apresentacao` (documentando fontes de dados existentes)

| Item | Fonte já existente |
|---|---|
| Arquitetura | `ARCHITECTURE.md` (Mermaid) ou lista estática do `docker-compose.yml` |
| Status das APIs | `GET /health/ready` (3 APIs); `GET /integrations/mercado-livre/status`; no bot, `summary()` (coletor online) |
| Exemplos de código | arquivos/linhas listados em `CODE_STUDY_GUIDE.md` (leitura estática) |
| IA ao vivo | `POST /ai/analyze-pc` e `/ai/recommend-upgrades`; `metadata` (modelo, `cached`, `prompt_version`) |
| MongoDB | `GET /commerce/catalog` (121 componentes), `counts` de `GET /promotions` (`mongo_promotions`, `published_promotions`, `active`, `historical`, `by_status`) |
| Pipeline Telegram | `scripts/telegram_demo.py` (simulação), `parse_message`, `enrich_promotion` sobre `messages.json` |
| Product Matcher | `product_matching.match_product` + catálogo do seed (nenhuma rede) |
| Mercado Livre | `/integrations/mercado-livre/status` (métricas e `item_api: restricted`), `ml_product_map.json`, `external_enrichment` dos componentes |
| Testes | saída de `pytest`/`vitest` (ver contagens) |
| Métricas | `reports/*.json` (fotografias) e `counts` das APIs |
