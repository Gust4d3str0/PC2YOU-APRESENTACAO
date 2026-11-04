# PC2YOU — Autenticação, usuários e dependências de login

## 1. Visão geral

JWT **HS256** emitido por `api-usuarios` e **validado localmente** por cada API com o mesmo `JWT_SECRET`. Não há sessão de servidor, nem refresh token, nem papéis (roles). O estado de login no frontend é `localStorage` (`token`, `user`).

## 2. Cadastro e login

| Etapa | Arquivo / função | Comportamento |
|---|---|---|
| Cadastro | `frontend/pages/Register.jsx` → `POST /auth/register` → `api-usuarios/main.py: register` → `crud.create_user` | `schemas.UserCreate` (name, e-mail validado por `pydantic[email]`, password); duplicidade → 400 "Email ja cadastrado" (checa antes e captura `IntegrityError`); senha vira hash **bcrypt** (`passlib CryptContext`, `crud.hash_password`); depois o frontend chama `/auth/login` automaticamente |
| Login | `Login.jsx` → `POST /auth/login` → `main.login` | `crud.verify_password`; erro → 401 "Email ou senha incorretos"; sucesso: `{user, access_token, token_type:"bearer"}` |
| Token | `auth.create_access_token(user_id)` | claims `sub` (id como string), `iat`, `exp` (`ACCESS_TOKEN_EXPIRE_MINUTES`, padrão 60); `jwt.encode(HS256 por padrão)` |
| Guardar | `Login.jsx` | `localStorage.setItem('token'/'user')` |
| Enviar | `frontend/src/api.js` | interceptor de request adiciona `Authorization: Bearer <token>` nos **três** clientes axios (usersApi, catalogApi, budgetsApi) |
| Logout | `Header.jsx` | remove `user` e `token` do `localStorage` e navega para `/login` |
| Estado no frontend | `getStoredUser()` (lê `user`), `Header.jsx` (mostra "Entre/Criar conta" ou menu) | **não há Context, rota protegida nem refresh**: cada tela/ação verifica o usuário por conta própria |

## 3. Middleware / dependências por serviço

| Serviço | Dependência FastAPI | O que valida | Consulta banco? |
|---|---|---|---|
| api-usuarios | `auth.get_current_user` (`OAuth2PasswordBearer(tokenUrl="/auth/login")`) | assinatura, `exp`, `sub` inteiro > 0; carrega o usuário (401 se não existe) | **Sim** (PostgreSQL `users`) |
| api-usuarios | `auth.require_owner(user_id, current_user)` | 403 se `user_id` ≠ usuário do token | — |
| api-catalogo | `dependencies.get_current_user` | assinatura/`exp`/`sub` (retorna o *payload*); 401/503 se sem `JWT_SECRET` | **Não** |
| api-catalogo | `dependencies.require_admin` | header `X-Admin-Key` == `ADMIN_API_KEY` (`hmac.compare_digest`); 503 se não configurada; 403 se inválida | Não |
| api-orcamentos | `auth.get_current_user` (`HTTPBearer`) | assinatura/`exp`/`sub` inteiro > 0, audience opcional (`JWT_AUDIENCE`) → `AuthenticatedUser(user_id)` | Não (mas as rotas chamam `ensure_user_exists` → `SELECT 1 FROM users`) |
| api-orcamentos | `require_payload_owner` | `payload.user_id == token.user_id` | — |

Rotas **protegidas** em uso real: ver §5. Rotas de IA **não** são protegidas.

## 4. Banco
PostgreSQL: `users(id, name, email único, password_hash)` e `favorites(user_id FK cascade, component_id; único por par)`. `budgets.user_id` é referência **lógica** (sem FK) ao `users.id` do outro serviço. Ver [DATABASE_MAP.md](DATABASE_MAP.md).

## 5. Funcionalidades que dependem de login (lista explícita)

| Funcionalidade | Por que depende | Sem login | Pode sair da demo? |
|---|---|---|---|
| Criar conta / entrar (`/register`, `/login`) | é o próprio login | n/a | **Sim** (se tudo o mais ficar aberto) |
| Favoritos (`FavoriteButton`, `/favorites`, `GET/POST/DELETE /favorites…`) | `get_current_user` + `require_owner`; dados em `favorites` por `user_id`; sem token o botão redireciona a `/login` | botão leva a `/login`; página Favoritos mostra vazio | **Sim** |
| Salvar orçamento do wizard (`/build` → "Finalizar", `POST /build/finalize`) | JWT + `payload.user_id == token` + `budgets.user_id` + `ensure_user_exists` | `Build.jsx` (linha ~110) manda para `/login`; nada é gravado | **Sim**, mas perde "Meu orçamento" (`/budget/:id`) — alternativa futura: resultado sem persistência |
| Ver orçamento (`/budget/:id`, `GET /budgets/{id}`, `/budgets/user/{id}`, `/performance/{id}`) | JWT + dono | 401/403 | Sim (junto com o anterior) |
| Editar/excluir orçamentos (`PUT/DELETE /budgets/{id}`, `POST /budgets`) | JWT + dono | 401 | Sim (não usadas pelo frontend atual) |
| **Validação manual de oferta** (`POST /promotions/{id}/validation`; botões em `OfferValidation.jsx`) | JWT; grava `offer.manual_validated_by = sub`, altera status (→ `confirmed`/`invalid`) e invalida histórico | botões **não aparecem** (`loggedIn()` falso); a API devolve 401 | **Sim** — mas sem ele nenhuma oferta pode virar `confirmed` |
| Atualizar preços reais de um componente (`POST /components/{id}/refresh-real-prices`, `sync-ml-price`) | `get_current_user` (qualquer token válido) para evitar abuso/chamadas ao ML | 401 (botão em `ComponentDetails.jsx`) | Sim (ou desabilitar o botão) |
| Rotas `/users*` | JWT + dono | 401 | Sim (frontend não usa) |

### Por que a validação manual precisa de usuário/autenticação
`validate_promotion` registra **quem** validou (`manual_validated_by`) e muda o estado comercial de uma oferta pública para todos os visitantes (`confirmed` dura 6 h; `invalid` remove a oferta das ofertas vigentes e marca o histórico como não verificado). Sem autenticação qualquer visitante poderia invalidar/confirmar ofertas (adulteração do ranking). O código não cria "papel de revisor": **qualquer** usuário logado pode validar (limitação).

## 6. Funcionalidades que NÃO dependem de login

| Funcionalidade | Observação |
|---|---|
| Home (`/`), busca, filtros e catálogo (`GET /commerce/catalog`, `/components*`) | públicos |
| Detalhes do componente (`/components/:id`), ofertas, histórico, gráfico | públicos (só favoritar/atualizar preços exigem token) |
| Promoções (`/promotions`) e `OfferComparison` | públicos |
| **Analisar meu PC** (`/analyze-pc`, `POST /ai/analyze-pc`) | **sem autenticação** (confirmado em `ai_routes.py` e em `docs/AI.md`) |
| **Recomendar upgrades** (`POST /ai/recommend-upgrades`) | **sem autenticação** |
| Wizard de montagem até escolher peças (`POST /build/next-options`, `/compatibility/check`) | públicos |
| Telegram collector e bot | independentes de `api-usuarios`; bot usa IDs do Telegram (`TELEGRAM_ALLOWED_USERS`) |
| Integração Mercado Livre (status e enriquecimento) | status público; enriquecimento por script |
| Proxy de imagens | público |

## 7. Pontos a tratar numa futura versão sem login (sem fazer agora)
1. **Frontend:** `Header.jsx` (botões Entre/Criar conta/Sair), `FavoriteButton.jsx`, `Favorites.jsx`, rotas `/login`, `/register`, `/favorites`; `Build.jsx` (finalização redireciona a `/login`), `OfferValidation.jsx` (`loggedIn()`), `api.js` (interceptor), `getStoredUser()` espalhado (Home, ComponentDetails, Favorites, Build).
2. **api-orcamentos:** `auth.get_current_user`/`ensure_user_exists` em todas as rotas `/budgets*`, `/build/finalize`, `/performance`; o serviço **não sobe** sem PostgreSQL (alembic no entrypoint) e a tabela `users` precisa existir para `ensure_user_exists`.
3. **api-catalogo:** `get_current_user` em `validate_promotion`, `sync_ml_price`, `refresh_real_prices`.
4. **Compose:** `api-orcamentos` e `frontend` dependem de `api-usuarios` saudável.
5. **Segurança compartilhada:** `JWT_SECRET` único para os 3 serviços.
6. Observações de risco já presentes: rotas `/ai/*` abertas consomem cota do Gemini; `/components/{id}/refresh-real-prices` aceita qualquer JWT válido sem checar existência do usuário.
