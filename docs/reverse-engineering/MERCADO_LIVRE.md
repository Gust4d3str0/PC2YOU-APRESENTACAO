# PC2YOU — Integração Mercado Livre (estado real)

Código: `api-catalogo/ml_products.py` (Product API, tokens, enriquecimento, capacidade de preço), `ml_commerce.py` (cliente OAuth legado + `MercadoLivrePriceService`), `ml_service.py` (busca/ofertas via API — caminho antigo de `refresh-real-prices`), `services/product_matching/ml_ids.py`, `scripts/enrich_mercado_livre_products.py`, `scripts/check_mercado_livre_price_capability.py`. Nenhum valor de credencial foi lido ou registrado.

## 1. Resumo honesto (o que funciona e o que não)

| Capacidade | Estado | Evidência no código |
|---|---|---|
| OAuth: usar `access_token` e renovar com `refresh_token` | **ativo** (se as variáveis/arquivo existirem) | `MercadoLivreTokenManager.access_token/refresh` |
| **Product API** `GET /products/{PRODUCT_ID}` (imagens, specs, identidade) | **ativa** — alimenta o enriquecimento (via script) | `MercadoLivreApi.get_product`, `MercadoLivreProductEnrichment` |
| Enriquecimento automático dentro das APIs HTTP | **não**: executado por script manual (`--dry-run` padrão, `--apply`) | `scripts/enrich_mercado_livre_products.py` |
| **Item API** `GET /items/{ITEM_ID}` / **Price API** `/items/{id}/sale_price` | **preparada, mas restrita**: terceiros recebem **403** (`PolicyAgent`/`access_denied`) | `MercadoLivreApi._policy_reason`, `MercadoLivrePriceCapability.probe`, `MercadoLivrePriceValidator` |
| Validação de preço de oferta pelo ML | **inativa na prática** (`unavailable`, nada é escrito nem invalidado) | `MercadoLivrePriceValidator.validate` |
| Busca/ofertas do ML para preço (caminho legado) | existe e é acionável por `POST /components/{id}/refresh-real-prices` (JWT) e `/components/sync-ml-prices` (admin); depende de a API aceitar os endpoints | `ml_service.refresh_component_real_prices` |

> Não apresentar a Price API como funcionalidade ativa em demonstração: o próprio sistema a trata como capacidade restrita.

## 2. OAuth e tokens

- **Variáveis** (nomes): `MERCADO_LIVRE_ACCESS_TOKEN`, `MERCADO_LIVRE_REFRESH_TOKEN`, `MERCADO_LIVRE_CLIENT_ID`, `MERCADO_LIVRE_CLIENT_SECRET`, `MERCADO_LIVRE_TOKEN_FILE` (compose: `/data/ml/tokens.json`, volume `ml_tokens`). `ml_products._env` aceita também o prefixo `ML_`.
- `MercadoLivreTokenManager` (`ml_products.py:48`):
  - lê tokens do ambiente e, se existir, do arquivo — **o arquivo só vale se o `env_fingerprint` (SHA-256 truncado do refresh token do `.env`) coincidir**; assim re-autorizar o `.env` invalida um arquivo antigo.
  - `access_token()`: renova se `expires_at ≤ agora + 30 s`.
  - `refresh(stale_token)`: `POST https://api.mercadolibre.com/oauth/token` (`grant_type=refresh_token`); se outra thread já trocou o token, não repete; **um refresh por vez** (`RLock`); **rotação**: o novo refresh token substitui o antigo e é **persistido** em arquivo (escrita atômica `.tmp` → rename, `chmod 600`); falha → bloqueio de 60 s (`REFRESH_COOLDOWN`), `last_error='refresh_failed'`; sem arquivo configurado a renovação é **recusada** (`refresh_unavailable`) para não perder o token rotacionado; `persist_failed` registrado.
  - `can_refresh` exige refresh token + client id + client secret + arquivo.
  - `state()` expõe só `configured, refresh_available, expires_at, last_error`.
- `MercadoLivreApi.get`: apenas GET; caminho validado (`/…`, sem `..`); um **401** dispara um refresh e uma repetição; mapeia respostas em `ApiResult(kind)`: `ok, not_found, forbidden, unauthorized, rate_limited (Retry-After, teto 300 s), server_error, timeout, auth_unavailable, invalid, error`. Nunca lança.
- Existe um **segundo cliente** (`ml_commerce.MercadoLivreClient`) com refresh e cache próprios (usado por `ml_service._request_json` e por `/integrations/mercado-livre/status`) — duplicação a conhecer. Nenhum token é logado ou retornado por endpoint.

## 3. Product API

- **PC2YOU não expõe `GET /products/{PRODUCT_ID}`.** Essa é a rota **do Mercado Livre**, consumida por `MercadoLivreApi.get_product(product_id)` (valida `^MLB\d{5,}$`).
- **Extração do PRODUCT_ID:** `ml_ids.extract_product_id(*urls)` — só URLs de domínios ML (`mercadolivre.com.br/.com`, `mercadolibre.com`, `meli.la`), padrão `/p/MLB\d{5,}`; retorna o id **somente se for exatamente um**. `ml_ids_from_offer(offer)` usa `resolved_url` e depois `url`. Também há o mapa curado `api-catalogo/ml_product_map.json` (`component_id → [PRODUCT_ID]`), ex.: `rtx-5060-ti-8gb → MLB78085963`, `rtx-5060-ti-16gb → MLB70362477`, `rtx-5060-8gb → MLB69967663`.
- **Normalização:** `MercadoLivreProductNormalizer.normalize(raw)` → `{product_id, catalog_product_id, name, family_name, status, domain_id, brand, manufacturer, model, detailed_model, images[≤8], attributes{id:{name,value}}, specs{chave amigável via SPEC_ALIASES}, specs_struct, short_description[≤600], last_updated, source:"mercado_livre_product_api"}`. Campo ausente = `None`; nada é inventado.
- **Imagens:** só `https` em `*.mlstatic.com`, sem duplicatas, máx. `MAX_IMAGES = 8` (`secure_url` preferida).
- **Cache:** coleção `external_product_enrichment` (`_id` = PRODUCT_ID, `fetched_at`); `MercadoLivreProductEnrichment.fetch` usa cache se `now − fetched_at ≤ ttl` (`PC2YOU_ML_PRODUCT_CACHE_TTL_HOURS`, padrão **24 h**) salvo `--force`; se a API falha e há cache antigo devolve `stale_cache`.
- **Persistência:** `external_product_enrichment` (documento do produto + `matches.<component_id>` + `component_ids`), contadores e estado em `ml_integration_state` (`_id:"state"`: `metrics.*`, `product_api`, `item_api`, `last_error`…), e — se aprovado — `components.external_enrichment.mercado_livre`.

## 4. PRODUCT_ID × ITEM_ID

| | PRODUCT_ID | ITEM_ID |
|---|---|---|
| O que é | produto de catálogo/PDP (página `/p/MLB…`) | anúncio de **um** vendedor |
| Exemplo no URL | `https://…mercadolivre.com.br/…/p/MLB78085963` | `…?wid=MLB7833387058`, `item_id=`, `pdp_filters=item_id:MLB…`, ou `/MLB-123456789-título` (formato do docstring de `ml_ids.py`) |
| API | `GET /products/{PRODUCT_ID}` (funciona) | `GET /items/{ITEM_ID}` (403 para terceiros) |
| Regex | `^MLB\d{5,}$` (`PRODUCT_ID_RE`) | `^MLB\d{6,}$` (`ITEM_ID_RE`) |
| Extração | `extract_product_id` | `extract_item_id` (`/p/MLB…` **nunca** é ITEM_ID; ambíguo → `None`) |
| Nunca intercambiáveis | — | `/up/MLBU…` (user products) não conta |

Exposição ao frontend: `commerce.projection` devolve `ml_product_id` e `ml_item_id` por oferta.

## 5. Enriquecimento externo (`external_product_enrichment`)

1. **Descoberta:** `scripts/enrich_mercado_livre_products.collect` junta (a) PRODUCT_IDs extraídos de promoções com match High e (b) `ml_product_map.json`; `basis` = `manual_mapping` ou `promotion_high_match`. `--suggest` apenas **sugere** candidatos (relatório) — uma pessoa decide o mapa.
2. **Match** (`evaluate_match`): usa o **mesmo** `compare_product` do matcher (título = nome + modelo; marca; atributos ML em minúsculas) + `domain_fits` (`domain_id` do ML deve conter `PROCESSORS`, `MOTHERBOARDS`, `GRAPHICS_CARDS`, `HARD_DRIVES/SSD`, `MEMORY`, `POWER_SUPPL`, `CASES/CABINETS`, … conforme a categoria; senão `domain_mismatch`).
   - Estados: `matched` (sem conflito e domínio ok e (`brand_variant` ou `matched` com confiança ≥ High)), `conflict`, `ambiguous` (domínio desconhecido ou score insuficiente).
   - Exceção `brand_variant`: único conflito `brand_conflict` com componente genérico de chip (marca nvidia/amd/intel) — aceito e marcado.
3. **Ligação ao componente:** `enrich` grava `matches.<id>` e `component_ids` no documento do produto e, se `matched` e (sem produto prévio **ou** mesmo produto **ou** `--force`), grava `components.external_enrichment.mercado_livre` com `match_status`, `match_basis`, `brand_variant`, `external_conflict`. **Nunca** toca preços, cupons, dados do Telegram nem `component_id`.
4. **Proteção contra conflito:** conflito bloqueia a aplicação; um produto prévio diferente também (a menos de `--force`). Leitores re-checam: `commerce.official_image` e `utils/commerce.js: imageCandidates` só usam imagens se `match_status == 'matched'` e `!external_conflict`.
5. **Prioridade sobre imagens:** ver §6. **Sobre specs:** o bloco é exibido como "especificações externas" (`ExternalSpecs.jsx`) **ao lado** das specs do catálogo; não sobrescreve `technical_specs` (o motor de compatibilidade e a IA continuam usando só `technical_specs`/`compatibility`).

## 6. Prioridade de imagem (código real)

**Backend** — `api-catalogo/commerce.resolve_image(offer, component)`:
`promoção (offer.image|image_url|thumbnail)` → `mercado_livre_product_api (external_enrichment matched, 1ª imagem https)` → `component_real (component.real_image)` → `component (images[0] ou image)` → `local` (`/images/{id}.png` apenas para `rtx-5060-8gb`, `rtx-5060-ti-8gb`, `rtx-5060-ti-16gb`) → `fallback` (`url None`: o frontend usa imagem padrão por categoria). `_usable_image` descarta `default-` e `placehold.co`.

**Frontend** — `frontend/src/utils/commerce.js: imageCandidates(component)` (usada por `getComponentImage`/`HardwareImage`, que tenta o próximo candidato ao falhar): `thumbnail/image da oferta atual (promoção)` → imagens oficiais ML (matched, sem conflito) → `real_image` → `images[]` → `thumbnail` → imagens de ofertas não-promoção → imagens de preços ML → `image` → `local` → `/components/default-{categoria}.png` → `/components/default-component.png`. Imagens `mlstatic.com` passam por `/images/proxy` (`api.js: proxiedImageUrl`). A ordem **bate com a esperada** (promoção → ML → real_image → images[] → local → fallback), com a ressalva de `thumbnail`/`image` do componente entre `images[]` e `local`.

## 7. Price API restrita (403)

- `MercadoLivrePriceCapability.probe(item_id)` chama `get_item`: `ok→available`, `forbidden→forbidden`, `not_found→not_found`, senão `error`. Em `forbidden`: `record_state` incrementa `ml_item_api_forbidden` e grava `item_api:"restricted"`, `price_validation:"unavailable"`, `ml_price_validation_capability:"forbidden"`.
- `ApiResult.kind="forbidden"` com `reason="policy_denied"` quando o corpo contém `PolicyAgent`, `access_denied` ou `PA_UNAUTHORIZED_RESULT_FROM_POLICIES`.
- **Regra de ouro:** 403 é uma **capacidade**, nunca veredito sobre a oferta (a oferta **não** é invalidada; nenhum campo é gravado).
- `MercadoLivrePriceValidator.validate(offer, item_id)` (se um dia autorizado): `not_found→expired`; status do item `closed/paused/inactive→expired`; compara com `sale_price` (fallback `price`) com tolerância `max(1,00; 0,5%)`; cupom com divergência → `coupon_not_verifiable` (não `price_changed`); `confirmed` gera `verified_price/verified_at` (que alimentam `evaluate_offer` → `confirmed`). `record_official_price` gravaria `product_price_history` (uma por item/dia/preço).
- Em `offers.py`, `MercadoLivreOfferValidator` é inerte sem `price_lookup` injetado.
- `GET /integrations/mercado-livre/status` mostra `item_api: restricted` / `price_validation: unavailable` quando a sonda registrou 403.

## 8. Limitações para explicar
- Enriquecimento depende de execução manual de script e de curadoria (`ml_product_map.json`).
- Preços não são validados oficialmente (Item API restrita): o preço exibido vem do Telegram (anunciado) — por isso os rótulos "anunciada", "condicional", "confirmada".
- Dois clientes ML coexistem (`ml_products` e `ml_commerce`), com caches/refresh separados; ambos escrevem em `MERCADO_LIVRE_TOKEN_FILE`, mas em formatos diferentes (o de `ml_products` inclui `env_fingerprint`; o de `ml_commerce._refresh` não, então `ml_products` **ignora** um arquivo gravado por `ml_commerce`). Como o refresh token rotaciona, um refresh feito por um cliente pode deixar o outro com token antigo até reiniciar/recarregar. Inferência a partir do código — não testado com credenciais reais.
