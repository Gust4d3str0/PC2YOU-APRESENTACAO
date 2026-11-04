# PC2YOU — Relatório final da engenharia reversa

Data: 2026-11-04. Escopo: **análise e documentação apenas.** Nenhum arquivo do projeto foi modificado, copiado ou removido; nenhum dado real foi lido ou escrito (MongoDB/PostgreSQL não foram consultados; só código e relatórios já existentes em `reports/`); o Gemini, o Telegram e o Mercado Livre **não** foram chamados. A única escrita foi criar `docs/reverse-engineering/*.md`. `dist/` do frontend não foi tocado (o build foi enviado a uma pasta temporária). **`PC2YOU-APRESENTACAO` não foi criado.**

Documentos: [ARCHITECTURE](ARCHITECTURE.md) · [FUNCTIONAL_MAP](FUNCTIONAL_MAP.md) · [API_MAP](API_MAP.md) · [AI_FLOW](AI_FLOW.md) · [TELEGRAM_FLOW](TELEGRAM_FLOW.md) · [PRODUCT_MATCHER](PRODUCT_MATCHER.md) · [MERCADO_LIVRE](MERCADO_LIVRE.md) · [DATABASE_MAP](DATABASE_MAP.md) · [AUTH_MAP](AUTH_MAP.md) · [CODE_STUDY_GUIDE](CODE_STUDY_GUIDE.md) · [PRESENTATION_PREP](PRESENTATION_PREP.md).

## Respostas diretas

**O que o PC2YOU faz?** Catálogo de 121 componentes + ofertas reais coletadas do Telegram (associadas ao catálogo por um matcher determinístico) + wizard de montagem com compatibilidade + análise/upgrades por IA (Gemini), com login opcional para favoritos, orçamentos salvos e validação manual de ofertas.

**Quantas funcionalidades relevantes existem?** **31** (ver FUNCTIONAL_MAP): 8 rotas de frontend, 49 endpoints HTTP, 2 processos Telegram, scripts de manutenção.

**Principais:** Home/catálogo, detalhes + ofertas (melhor geral × condicional), **Analisar meu PC (IA)**, **upgrades (IA v2)**, promoções Telegram, wizard `/build`, orçamento.

**Serviços obrigatórios:** MongoDB + `api-catalogo` (núcleo); `api-orcamentos` (IA/wizard); frontend. PostgreSQL e `api-usuarios` são obrigatórios **no estado atual** do compose/boot, embora as funcionalidades de produto (catálogo, ofertas, IA) não os usem. Telegram, Gemini e Mercado Livre são opcionais.

**Bancos:** MongoDB 7 (10 collections) e PostgreSQL 15 (4 tabelas).

**Como a IA funciona:** o backend valida/sanitiza a entrada, identifica as peças no catálogo (1 match exato), calcula compatibilidade por regras, escolhe candidatos de upgrade e **só então** chama o Gemini (`gemini-2.5-flash`, temperatura 0,2, structured output com `candidate_id` em `enum`). A resposta passa por Pydantic, validação semântica (tipo, orçamento, IDs) e validação de prosa (sem números/modelos/"compatível"); nomes e preços vêm do backend. Cache 300 s, 1 chamada simultânea, 10/min; sem retry/fallback. Detalhes: AI_FLOW.

**Como o Telegram funciona:** coletor Telethon (conta de usuário) lê canais permitidos → filtro → parser (preço, cupom, loja, URL, condições) → `enrich_promotion` (matcher + status) → upsert idempotente em `telegram_promotions` + histórico verificado → resolver de links em background. A API recalcula status em cada leitura. Um bot separado envia alertas pessoais. Detalhes: TELEGRAM_FLOW.

**Como o matcher funciona:** normaliza texto, extrai modelo/marca/capacidade/tipo/socket/potência, aplica conflitos duros (score 0,20), soma pesos (modelo 0,80 + sinais), aplica tetos; **High ≥ 0,85, Medium ≥ 0,65**; ambiguidade entre variantes → sem match. Só High vira preço verificado. Detalhes: PRODUCT_MATCHER.

**Como o Mercado Livre funciona:** OAuth com refresh rotativo persistido em arquivo; **Product API** `/products/{PRODUCT_ID}` alimenta imagens/specs oficiais (cache 24 h, via script, só se o matcher aceitar); **Item/Price API retorna 403** para terceiros → capacidade restrita, nunca veredito sobre a oferta. Detalhes: MERCADO_LIVRE.

**O que depende de login?** Favoritos, salvar/ver orçamento (`/build/finalize`, `/budgets*`, `/budget/:id`, `/performance/{id}`), validação manual de oferta, atualizar preços reais, `/users*`. **IA, catálogo, ofertas, matcher, wizard (até finalizar) não dependem.** (AUTH_MAP §5–6.)

**O PostgreSQL é necessário fora da autenticação?** **Sim**: favoritos e orçamentos. E, operacionalmente, `api-orcamentos` (que hospeda a IA) executa Alembic no boot e lê `users` por SQL; sem PostgreSQL o serviço não sobe.

**Arquivos mais importantes:** ver "PRIORIDADE 1" em CODE_STUDY_GUIDE (`services/ai/*`, `ai_context.py`, `ai_upgrade_context.py`, `product_matching/matcher.py|offers.py`, `api-catalogo/commerce.py`, `telegram_collector/parser.py|repository.py`).

**Limitações atuais:** preços anunciados, não validados oficialmente; frescor de 72 h; rotas de IA sem autenticação; matcher conservador; dependência do Telegram; duplicação de clientes ML; ver PRESENTATION_PREP §6.

## Testes, lint e build (executados, seguros)

| Verificação | Resultado |
|---|---|
| `pytest api-usuarios` | 11 passed |
| `pytest api-orcamentos` | 230 passed |
| `pytest api-catalogo` | 377 passed, 1 skipped |
| `pytest services/tests` | 485 passed |
| `vitest run` (frontend) | 28 passed |
| `npm run lint` | sem problemas |
| `vite build` (saída fora do projeto) | ok |

Todas as suítes usam SQLite em memória / mongomock / mocks; nenhuma tocou bancos reais.

## Premissas do pedido × código real

| Premissa | Código real |
|---|---|
| "Product Matcher faz parte do fluxo de IA (analyze-pc)" | **Não** em `analyze-pc`: usa `ai_context.enrich` (1 match exato por nome). O matcher entra na IA **v2** (upgrades) para ligar promoções ao catálogo |
| "collection `price_history`" | Não existe collection com esse nome: `product_price_history` (e campo embutido `components.price_history`) |
| "`GET /products/{PRODUCT_ID}`" | É rota **do Mercado Livre**; o PC2YOU não a expõe |
| "Gemini com retry/fallback/timeout" | Timeout sim (45 s); retry **não** (`attempts=1`); fallback de modelo **não** |
| "validação manual precisa de usuário" | Confirmado (`get_current_user`), mas **qualquer** usuário logado pode validar |
| "PostgreSQL só para login" | **Falso**: também favoritos e orçamentos |
| "Imagem: promoção → ML → real_image → images[] → local → fallback" | Backend confirma exatamente; frontend acrescenta `thumbnail`/`image` do componente (ver MERCADO_LIVRE §6) |
| Status `announced/conditional/confirmed/stale/expired/invalid` | Confirmados em `offers.py: STATUSES`; **não são persistidos**, calculados na leitura |
| `status` da promoção no Mongo | O coletor só grava `parsed`; `matched/verified/published/ignored` existem no enum, mas **nenhum código inspecionado os grava** |

## DOCUMENTAÇÃO DESATUALIZADA (docs antigos × código)

1. **`docs/FINAL_COMMERCE_FRONTEND.md` (§imagens)** — *dizia:* resolvedor usa "imagem real, lista de imagens, imagem da oferta, imagem ML persistida, local e fallback". *Código atual:* backend `commerce.resolve_image` = promoção → ML (`mercado_livre_product_api`) → `real_image` → `images[0]/image` → local → fallback; frontend `imageCandidates` = promoção → ML → `real_image` → `images[]` → … (a imagem **da promoção vem primeiro** e a do ML antes de `real_image`).
2. **`docs/CATALOG_ENRICHMENT_V1.md`** — *dizia:* "MongoDB permanece com 94 componentes" (base auditada de 94 vs 121 enriquecida). *Código atual:* `seed.py` tem **121**; os relatórios mais recentes (`commerce-live-validation.json`) listam `catalog_count: 121`. O texto é histórico, não "errado", mas pode confundir.
3. **`docs/POST_BACKFILL_QUALITY_AUDIT.md` (`deployed_seed_evidence`)** — *dizia:* o container implantado tinha nomes antigos (`ryzen-5-7600` = "AMD Ryzen 5 8600G", `ryzen-7-7800x3d` = "AMD Ryzen 7 7700", `ryzen-9-7950x` = "AMD Ryzen 9 7900"). *Código atual:* `seed.py` tem `ryzen-7-7800x3d` = "AMD Ryzen 7 7800X3D". Como `seed_components` só faz `$setOnInsert` (não corrige documentos existentes), **o Mongo real pode divergir do seed do código** até rodar `scripts/sync_catalog_identity.py` — não verificado (sem consulta ao banco).
4. **Contagens de promoções entre relatórios** (654 / 1.421 / 1.484 / 1.685): são fotografias de momentos diferentes; nenhum número é "o atual".

## FUNCIONALIDADES DESCOBERTAS
Resumidas em FUNCTIONAL_MAP §4: wizard `/build` + compatibilidade + desempenho; bot de alertas; proxy de imagens; resolver de redirects com proteção SSRF; arquitetura de validadores; `catalog_audit`/`catalog_enrichment`; `X-Request-ID`; scripts de demonstração/auditoria.

## Riscos/observações encontrados (sem corrigir)
- `/ai/*` abertas (custo/abuso); rate limit global por worker.
- `refresh-real-prices` e `sync-ml-price` aceitam qualquer JWT válido sem checar existência do usuário no catálogo.
- Arquivo `.env` real existe na raiz do projeto (ignorado pelo `.gitignore`; **não foi lido**).
- Dois clientes ML com formatos de arquivo de token diferentes (MERCADO_LIVRE §2).
- `api-orcamentos` lê a tabela `users` do outro serviço no mesmo banco (acoplamento por SQL).
- `git status` não funcionou na raiz (`not a git repository`), embora exista `.git`; não investigado.

## Critério de conclusão
Rastreio **funcionalidade → frontend → endpoint → função → banco/serviço → resposta** documentado para todas as funcionalidades principais (FUNCTIONAL_MAP §1, API_MAP §5, AI_FLOW §2–3, TELEGRAM_FLOW §2). **Não verificado:** comportamento real do Gemini (nenhuma chamada feita), do Telegram/ML (sem credenciais usadas) e do conteúdo vivo dos bancos.

Parei aqui, conforme o pedido. A criação de `PC2YOU-APRESENTACAO` fica para a segunda etapa.
