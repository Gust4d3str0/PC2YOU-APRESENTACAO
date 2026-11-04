# PC2YOU — versão de apresentação

Esta é a cópia independente **PC2YOU-APRESENTACAO**. O projeto original não precisa ser executado nem modificado. As imagens Docker incluem as dependências necessárias.

## Iniciar

Requer Docker com Compose. Na raiz desta cópia:

```powershell
Copy-Item .env.example .env  # somente em uma instalação nova, sem .env existente
# Preencha os valores privados no .env local.
docker compose up -d --build
docker compose ps
```

Acesse [a apresentação](http://localhost:5174/apresentacao) ou [o catálogo](http://localhost:5174). APIs: catálogo em 8012, IA em 8013. Bancos e volumes são exclusivos desta cópia. Para parar: `docker compose down` (preserva os volumes).

## Configuração

Apenas nomes, sem valores privados: `DEMO_MODE`, `AI_ENABLED`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `AI_TIMEOUT_SECONDS`, `AI_CACHE_TTL_SECONDS`, `AI_REQUESTS_PER_MINUTE`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `MONGO_DB`, `CORS_ORIGINS`, `PUBLIC_CATALOG_API_URL`, `PUBLIC_AI_API_URL`, `DEMO_FRONTEND_PORT`, `DEMO_CATALOG_PORT`, `DEMO_AI_PORT`.

Opcional ML: `MERCADO_LIVRE_ACCESS_TOKEN`, `MERCADO_LIVRE_REFRESH_TOKEN`, `MERCADO_LIVRE_CLIENT_ID`, `MERCADO_LIVRE_CLIENT_SECRET`. As chaves ficam no servidor. Alterar URLs públicas exige rebuild do frontend. `VITE_DEMO_MODE=true` é a flag de build da interface; o Compose a deriva de `DEMO_MODE`.

Telegram é opcional: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`, `TELEGRAM_ALLOWED_CHATS`. O profile `telegram` inicia collector e bot; `TELEGRAM_BOT_TOKEN` e `TELEGRAM_ALLOWED_USERS` são necessários para o bot. As sessões ficam no volume separado. A sessão do original não é compartilhada. Sem collector, o catálogo funciona com os dados persistidos.

## Apresentar

São 18 seções. Use o menu, Anterior/Próximo, ←/→ ou o botão Tela cheia. Campos editáveis preservam o uso normal das setas. Clique nos diagramas e em Ver código. Escape fecha o painel e restaura o foco.

Na demonstração de IA, CPU, GPU e orçamento são editáveis; as demais peças vêm do preset. A requisição usa `/ai/analyze-pc`; `/analyze-pc` oferece o formulário completo e os upgrades. Gemini configurado não significa online: somente uma chamada concluída confirma o funcionamento. O contexto mostrado é reconstruído no momento da consulta, não um log da chamada anterior. O resultado JSON é o retorno efetivo da análise.

Se a chamada falhar, o botão de fallback mostra **Resposta de demonstração salva**, obtida com o preset original em 04/11/2026. Não representa uma execução ao vivo nem configurações alteradas. Telegram e ML exibem dados armazenados, com horário e origem. O MongoDB Explorer é somente leitura.

## Verificar

Com a pilha ativa e Python com `requests`:

```powershell
python scripts/validate-demo.py
python scripts/verify-snippets.py
cd frontend
npm ci
npm run lint
npm run build
npm test
```

As suítes Python são independentes por serviço: crie ambientes virtuais próprios e instale os requirements correspondentes; execute `python -m pytest -q api-catalogo/tests`, `python -m pytest -q api-orcamentos/tests` e `python -m pytest -q services/tests` a partir da raiz. Para a suíte services, adicione pytest, mongomock e as dependências IA de api-orcamentos. Não combine requirements conflitantes em produção; as imagens já isolam cada serviço.

Para screenshots automatizadas:

```powershell
npm install --prefix .tools/browser --no-save --package-lock=false playwright
node .tools/browser/node_modules/playwright/cli.js install chromium
node scripts/validate-browser.cjs
```

Resultados, limitações e instruções de deploy: [relatório final](docs/demo/FINAL_DEMO_REPORT.md). Nenhum deploy público foi realizado.
