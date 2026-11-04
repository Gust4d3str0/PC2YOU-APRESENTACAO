# PC2YOU — Telegram, promoções, condições, status e URLs

Código: `services/telegram_collector/` (coleta), `services/telegram_bot/` (alertas), `services/product_matching/{promotions,offers,quality,destinations}.py`, leitura em `api-catalogo/commerce.py`.

## 1. Componentes

| Parte | Arquivo | Descrição |
|---|---|---|
| **Collector** | `collector.py` | Conta **de usuário** (Telethon, MTProto; recusa bot: `me.bot`). Comandos: `auth` (interativo), `list-chats`, `import-history [--limit]`, `listen [--import-history]` (padrão do Docker). Só lê grupos/canais listados em `TELEGRAM_ALLOWED_CHATS` (`is_allowed_source`), ignora mensagens enviadas pela própria conta e mensagens de serviço. Histórico e eventos passam pela mesma função `process_message`. Heartbeat a cada 30 s em `telegram_service_status`. Sessão persistida em `TELEGRAM_SESSION_PATH` (permissões 0700/0600) |
| **Filtro** | `filters.py: is_possible_promotion` | Texto contém `R$` ou uma palavra-chave (promoção, oferta, cupom, desconto, pix, lojas, categorias de hardware) |
| **Parser** | `parser.py: parse_message` | Preço, preço original, cupom, loja, tipo, URL, validade e condições (§3) |
| **Links** | `links.py` | `extract_urls`, `select_offer_url` (prioriza botão > URL de entidade > texto visível > outras; descarta redes sociais e imagens; prefere URL com caminho/consulta, loja conhecida e padrão de produto), `extract_message_links` (lê botões inline e entidades da mensagem) |
| **Persistência** | `repository.py: PromotionRepository` | `save` (enriquece + `update_one($setOnInsert, upsert)`), `_complete_links`, `resolve_link`, `refresh_quality`, `_save_observation`, `heartbeat`, `summary` |
| **Deduplicação** | índice único + `deduplication.py` | §6 |
| **Bot** | `bot.py`, `handlers.py`, `alerts.py`, `notifier.py` | §7 |

## 2. Pipeline completo de uma promoção

| # | Etapa | Arquivo / função | O que acontece |
|---|---|---|---|
| 1 | Mensagem | `collector.on_message` / `import_history` | evento `NewMessage` (chats permitidos, `incoming=True`) ou `iter_messages(limit)` |
| 2 | Coleta | `collector.process_message` | valida origem, `is_possible_promotion`, monta `sent_at` (UTC) |
| 3 | Parser | `parser.parse_message(text, sent_at, button_urls, entity_urls…)` | devolve `{product:{name:None, component_type}, offer:{store, price, original_price, coupon, url, url_source, valid_until?, conditions?}, links[]}`. **`product.name` fica `None`**: o texto bruto (`raw_text`) é o que o matcher lê |
| 4 | Preço | `parser.extract_prices` | `_PRICE_RE` (R$ ou número com vírgula); ignora parcelas (`12x`), frete, "economize"; rótulos `de/antes` = original, `por/agora/no pix/à vista` = atual; exige **um único** valor atual (ou um único sem rótulo); `original ≤ atual` é descartado |
| 5 | Cupom | `parser.extract_coupon` | `cupom: CODIGO` ou `use CODIGO`; código com dígito ou todo em maiúsculas; ignora palavras comuns; **um único** cupom |
| 6 | Loja | `parser.identify_store` | nome no texto (sem URLs) e/ou domínio dos links (KaBuM, Pichau, Terabyte, Amazon, Mercado Livre); só se **uma única** loja for identificada |
| 7 | URL | `links.select_offer_url` | ver acima; guarda `url_source` (button/entity/text) |
| 8 | Documento | `collector.process_message` | `telegram:{chat_id, chat_name, chat_username, message_id, message_url, sent_at}`, `raw_text`, `status:"parsed"`, `created_at`, `processed_at` |
| 9 | Matcher + qualidade | `repository.save → promotions.enrich_promotion(document, catálogo do Mongo)` | `match_product` → `product.{component_id, normalized_key, match_confidence, match_level, matched_by, conflicts, matcher_version}`; `price_quality` → `offer.{verified, state, source, captured_at, url_valid, store_key…}`; `equivalence_key`; `price_observation` |
| 10 | Persistir | `update_one(identity, {"$setOnInsert": doc}, upsert=True)` em `telegram_promotions` (`status` derivado `evaluation` **não** é gravado) | idempotente por (`chat_id`, `message_id`) |
| 11 | Histórico | `_save_observation` | só se High e verificado: `product_price_history` (uma por mensagem; ofertas idênticas no mesmo dia não duplicam); se perdeu a verificação, marca `verified:false, invalidated_by:"current_product_match"` |
| 12 | Resolver de links | `collector._resolve_in_background → repository.resolve_link → destinations.resolve_redirects + link_fields` | segue redirects HTTP em *thread*, grava `offer.resolved_url, url_kind, resolved_kind, resolved_store, link_status, link_hops, link_checked_at`; **nunca substitui `offer.url`** |
| 13 | API | `commerce.build_snapshot` (cache 30 s) → `/promotions`, `/components/{id}/offers`, `/commerce/catalog` | re-executa `enrich_promotion` **no momento da leitura** (status envelhece com o relógio) |
| 14 | Frontend | `PromotionSection.jsx`, `OfferComparison.jsx`, `Home.jsx`, `OfferValidation.jsx` | cartões, ofertas atuais x histórico, rótulos honestos (`utils/commerce.js: offerLabel`) |
| 15 | Alertas | `NotificationWorker.run_once` | promoção nova → alertas ativos → `matches_alert` → `send_message` |

Exemplo real (executado): mensagem `Processador AMD Ryzen 7 7800X3D / Por R$ 2.399,90 / KaBuM / https://www.kabum.com.br/produto/12345` com 3 h de idade → match `ryzen-7-7800x3d` High 0.93, `status=announced`, `eligible=True`, `verified=True`. Com 30 h → `stale (needs_confirmation)`, ainda elegível; com 80 h → `stale (beyond_freshness_limit)`, **não elegível**, `verified=False`.

## 3. Conditions (`product_matching/offers.py: extract_conditions`, `CONDITIONS_VERSION = 2`)

Totalmente determinístico (regex sobre o texto sem URLs, sem acentos, minúsculo). **Desconhecido permanece `None`** (nunca `False`). Campos reais:

| Campo | Como é detectado |
|---|---|
| `coupon_code` / `requires_coupon` | cupom já extraído pelo parser (`True` se houver, senão `None`) |
| `first_purchase_only` | `primeira compra | primeiro pedido | 1ª compra | first purchase` |
| `new_customer_only` | `novo(s) cliente(s) | cliente novo | usuário novo | novo cadastro` |
| `app_only` | `somente/apenas/exclusivo (pelo|no|via) app/aplicativo`, `app exclusivo`, `compra(s) pelo/no app`, `primeira compra pelo/no/via app` (ex.: "primeira compra**,** pelo app" com vírgula **não** casa — limitação observada) |
| `payment_methods` | `PIX`, `NuPay`, `Nubank`, `Cartão da loja` (kabum/magalu/casas bahia/pichau/mercado pago/amazon) |
| `membership_required` | `Prime`, `Meli+`, `Clube (kabum/magalu/do)` unidos por " / " |
| `minimum_order` | `pedido/valor mínimo`, `compras acima de`, `min.` + `R$ valor` |
| `max_uses_per_customer` | `1 uso por CPF/cliente/usuário/conta`, `uso único por…`, `limitado a 1 por…` → `1` |
| `valid_until` | `_deadline`: `válido até DD/MM[/AAAA] [HH:MM]`, `expira em`…; sem ano usa o ano do anúncio (o próximo se já passou); `hoje/último dia` → 23:59 BRT; `até HHh` do dia do anúncio; fuso BRT (−03:00); o parser da coleta aceita apenas data completa `DD/MM/AAAA` |
| `conditions_text` | trechos originais que carregam condição (≤300 caracteres, URLs removidas) |
| `conditions_version` | `2` — documentos com outra versão são reextraídos em `enrich_promotion` |

`is_conditional(conditions)` = há método de pagamento **ou** qualquer flag de `requires_coupon, first_purchase_only, new_customer_only, app_only, membership_required, minimum_order`. `condition_labels` gera os rótulos em português ("Exige cupom", "Somente primeira compra", "Pagamento via PIX"…). Backfill: `scripts/backfill_promotion_conditions.py` (`--dry-run` padrão; `--apply` escreve `offer.conditions`). Dado de campo (relatório `reports/promotion-conditions-apply2.json`): 1.685 promoções; 762 com cupom, 256 PIX, 56 assinatura, 39 pedido mínimo, 23 só-app; 919 condicionais.

## 4. Status comercial (`offers.py: evaluate_offer`)

**Quem calcula:** `evaluate_offer` (puro; chamado em `enrich_promotion` e portanto a cada leitura de `commerce.build_snapshot`). **Não é persistido** (`document.pop('evaluation')` em `repository.save`): o status "envelhece" com o relógio.

Limiares (`quality.py`, configuráveis por env): `RECENT_HOURS=6`, `REDUCED_HOURS=24`, `STALE_LIMIT_HOURS=72`, `CONFIRMATION_TTL_HOURS=6`, `EXPLICIT_VALIDITY_MAX_DAYS=7`.

Ordem de decisão:
1. Checagem manual/fonte mais recente (posterior ao anúncio) **negativa** → `invalid`.
2. Alguma validade (`valid_until`, cupom) já passou → `expired` (`validity_ended`).
3. Sem data de captura → `announced` (não elegível).
4. Checagem **positiva** nas últimas 6 h → `confirmed` (elegível).
5. Há validade explícita ainda aberta: se idade ≤ 7 dias → `conditional` (se condicional) ou `announced`, elegível; senão `stale` (`announcement_too_old`).
6. Sem validade: idade > 72 h → `stale` não elegível; > 24 h → `stale` **elegível** (`needs_confirmation`); senão `conditional`/`announced`, elegível.

| Status | Significado | Efeito no frontend (`utils/commerce.js`) | Ranking |
|---|---|---|---|
| `announced` | anunciado no Telegram, sem verificação | "Anunciada recentemente" | compete |
| `conditional` | anunciado com condição(ões) | "Oferta com condição" | só entra em `best_conditional_offer` |
| `confirmed` | pessoa/fonte confirmou nas últimas 6 h | "Confirmada recentemente" | desempata a favor |
| `stale` | velho (>24 h sem confirmação) ou além de 72 h | "Oferta desatualizada"/"Histórico" | perde no desempate; não elegível após 72 h |
| `expired` | validade/cupom vencidos | "Expirada" (histórico) | fora |
| `invalid` | marcada "não funciona mais" | "Não funciona mais" | fora |

Telegram **sozinho nunca gera `confirmed`**; só a validação manual (`POST /promotions/{id}/validation`, exige JWT) ou verificação de fonte.

## 5. Melhor oferta (`api-catalogo/commerce.py`)

- `best_candidates(rows)`: só ofertas `eligible`, com `url` utilizável, preço > 0 e `source != 'seed'`.
- `best_offer(rows)`: menor **preço efetivo** = `price × (1 + 0.05)` se o destino **não** for produto (`NON_PRODUCT_PENALTY = 0.05`: busca/homepage/desconhecido); desempates: `status == 'stale'` perde, `status != 'confirmed'` perde, maior `kind_rank` (product 3 > search 2 > homepage 1 > unknown 0), `id`.
- `best_general_offer(rows)` = `best_offer` entre ofertas **sem** condição relevante (`not is_conditional`). → "melhor preço geral".
- `best_conditional_offer(rows)` = `best_offer` entre ofertas **com** condição. → "melhor preço se cumprir a condição" (cupom, primeira compra, app, PIX, assinatura, pedido mínimo). Sempre exibida com as condições.
- `best_offer` geral (`data['best']`) = melhor entre todas as candidatas. Exemplo da regra: link de produto a R$ 2.750 vence busca a R$ 2.700, mas não busca a R$ 2.300.
- Serviço `services.best_price` (usado por orçamentos): "ofertas incondicionais primeiro; condicional só se não houver outra".
- IA v2 (`ai_upgrade_context.prices` → `quality.best_known_price`): camadas `tier` 0 (verificado High) < 1 (Medium, só `allow_medium`) < 2 (seed) < 3 (referência High) < 4 (expirada/descartada).

## 6. Deduplicação

| Nível | Critério | Onde |
|---|---|---|
| Mensagem | índice único `uq_telegram_chat_message` em (`telegram.chat_id`, `telegram.message_id`); `identity` via `message_identity` (só IDs de grupo/canal negativos) | `repository.ensure_indexes/save` |
| Reimport | `$setOnInsert`: documento existente não é sobrescrito; apenas `_complete_links` (`$addToSet links`, compare-and-set de `offer.url`) e `refresh_quality` | `repository.py` |
| Histórico de preço | uma observação por mensagem; oferta com mesma `equivalence_key` já vista no mesmo dia (verificada) não duplica | `_save_observation/_seen_same_day` |
| Oferta equivalente (leitura/API) | `commerce._dedupe_key` = (`component_id`, `price`, `coupon` em maiúsculas, `store`, destino `(host, path)` **se** `url_kind == 'product'`); mantém a mais recente e conta `also_seen`/`merged_ids` | `commerce.dedupe` |
| Equivalência (hash) | `quality.equivalence_key` = SHA-256 de [component_id, price, store normalizada, cupom, URL sem fragmento] (mantém query de afiliado) | `quality.py` |
| IA v2 | mesma `equivalence_key`; ≤3 por componente | `ai_upgrade_context.normalized_promotions` |
| Alertas | `notification_history` único (usuário, alerta, promoção); `notification_dedup` (TTL) por `equivalent_offer_key(produto, preço, loja, cupom)` por `TELEGRAM_ALERT_DEDUP_HOURS` (6) | `notifier.py`, `deduplication.py` |

## 7. Bot de alertas

- `bot.py`: `Application` com `/start`, `/status` (promoções armazenadas, coletor online se heartbeat < 120 s) e `AlertHandlers.register` (`/acompanhar`, `/alertas`, `/remover`, `/pausar`, `/ofertas`, `/cancelar`, `/ajuda`, `/meuid`, callbacks `pc2:*`, texto de conversa). `TELEGRAM_ALLOWED_USERS` vazio = qualquer usuário em conversa privada.
- `alerts.AlertRepository` (`price_alerts`): `validate_alert` (consulta ≤120 chars, preço máx 0–999.999.999,99, tipo de componente, ≤20 filtros de marca/loja, desconto mínimo 0–100).
- `collector.matcher.matches_alert`: termos normalizados do alerta ⊆ termos da promoção; modelo GPU deve coincidir; preço ≤ máximo; tipo; marcas/lojas incluídas/ignoradas; desconto mínimo (só se original e atual existem). **Não usa o catálogo nem o Product Matcher.**
- `notifier.NotificationWorker`: ciclo `run_once` (a cada `TELEGRAM_NOTIFICATION_POLL_SECONDS`=10) busca promoções com `created_at ≥ started_at` e sem `notifications_processed_at`; para cada alerta correspondente `deliver` (lease de 2 min em `notification_history`, estados `sending/sent/failed/rejected/uncertain/skipped_equivalent/cancelled`; `RetryAfter` agenda reenvio; entrega incerta **não** é reenviada). Oferta `expired` não notifica.

## 8. Resolução de URLs (`destinations.py`)

- `store_from_url(url)`: loja pelo **domínio** (`STORE_DOMAINS`: Kabum, Pichau, Terabyte, Amazon, Mercado Livre, Magazine Luiza, Shopee, AliExpress); `None` para encurtadores (`SHORTENER_DOMAINS`: meli.la, amzn.to, bit.ly, s.click.aliexpress.com, awin1.com, …) e domínios desconhecidos.
- `classify_url(url)` → `product | search | homepage | unknown`: `unknown` se `offer_url` rejeita (rede social, imagem, homepage ML) ou é encurtador; `search` por caminho (`/search|busca|s|…`) ou query (`q,k,keyword,…` sem `/dp|produto|item|p/`); `homepage` se caminho vazio; `product` por padrão por loja (`/produto/\d+`, `/dp/…`, `/MLB-…|/p/MLB…`, `/p/xxx/`, Shopee, AliExpress; Pichau por *slug* de 4+ palavras); senão `unknown`.
- `choose_url(original, resolved)`: mantém o original, salvo se o resolvido tem `kind_rank` maior, ou igual com original encurtador e resolvido não.
- `resolve_redirects(url)`: nunca lança; apenas HTTP(S); GET sem ler corpo (`allow_redirects=False`, `stream=True`), segue **manualmente** até `MAX_REDIRECTS=6`; **proteção SSRF**: só segue host cujos IPs sejam todos globais (`_public_host`: `ip_address(...).is_global`); `User-Agent: PC2YOU-LinkResolver/1.0 (+redirect-only)`; timeout (3, 5) s; cache em memória 6 h (limpo acima de 4096 entradas). Sem JavaScript, formulário, login, checkout ou chamada de cupom.
- `link_fields(...)` gera os campos gravados em `offer.*`. `offer_url` (quality.py) valida URL, remove `t.me`, redes sociais, imagens, usuário@host e homepage do Mercado Livre.
- Imagens do Mercado Livre usam proxy próprio (`/images/proxy`) com as mesmas ideias (https, host público, `*.mlstatic.com`, limite de bytes).
