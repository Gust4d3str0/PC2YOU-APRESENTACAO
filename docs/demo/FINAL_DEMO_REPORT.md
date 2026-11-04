# Relatório final — PC2YOU-APRESENTACAO

Execução em 04/11/2026, fuso America/Sao_Paulo.

## Resultado

A pasta PC2YOU-APRESENTACAO já existia parcialmente implementada. Foi completada sem modificar os arquivos do projeto original PC2YOU. A cópia sobe de forma independente por Docker Compose, com frontend Nginx na porta 5174, catálogo na 8012, IA na 8013, PostgreSQL e MongoDB em volumes separados. Não depende de node_modules ou ambiente Python do original em execução. Não houve deploy público.

Acesso local: http://localhost:5174/apresentacao. Home: http://localhost:5174.

## O que foi entregue

- Rota /apresentacao com 18 seções, menu, navegação por teclado e botões, hash de seção, fullscreen e conteúdo rolável.
- Arquitetura e ações do usuário com nós clicáveis, destaque de caminho e painel de responsabilidade, código, entradas, processamento, saídas e dependências.
- Code Explorer com 29 snippets reais, abas por área e syntax highlighting; igualdade conferida com os arquivos e linhas da cópia.
- IA: fluxos analyze-pc e recommend-upgrades explicados separadamente. A análise não usa matcher. Formulário reduzido com CPU, GPU e orçamento editáveis, resultado JSON e leitura de contexto reconstruído.
- Fallback explicitamente rotulado “Resposta de demonstração salva”, obtido de uma execução Gemini real com o preset original. Nenhuma resposta fictícia foi criada.
- Matcher determinístico real, normalização/features, score, níveis, conflitos e candidatos.
- Telegram: última promoção real armazenada, campos extraídos, associação e status; consulta a cada 30 s e collector sem heartbeat recente identificado como offline.
- Mercado Livre: seleção de componente com enriquecimento persistido, PRODUCT_ID, data, imagem e specs; distinção entre fonte comercial e enriquecimento.
- MongoDB Explorer: whitelist de seis coleções, Tabela/JSON, paginação limitada, projeção de campos e sanitização.
- Painel de integrações sem status ONLINE hardcodado; Gemini configurado é distinguido de uma chamada efetivamente concluída.
- UI sem login, conta, favoritos, persistência de orçamento, validação manual ou refresh manual de preço. Catálogo, busca, detalhes, promoções, comparação, histórico e montagem preservados.

## Ajustes necessários para estabilidade

Corrigido conflito de import entre services.py e pacote services na imagem do catálogo; parser compartilhado usa import compatível com os dois layouts. Corrigido carregamento do snapshot em execução local. Interface estática é servida por Nginx, com fallback SPA e cache por tipo de recurso.

Corrigido history_stats dos upgrades: o catálogo fornece observations como contagem em agregados diários; esses agregados não podem ser iterados como observações verificadas. A cópia ignora a contagem e mantém as observações detalhadas verificadas como evidência. Teste de regressão incluído.

Guards usam conjuntos exatos de rotas e métodos. /demo só aceita GET; exceções de POST são IA, cálculos e batch de leitura, fora desse namespace. Testes conferem bloqueio de POST/PUT/PATCH/DELETE, limites, whitelist, sanitização e associação conservadora.

A adaptação opcional de linguagem foi testada e NÃO foi exposta: mesmo com validações de formato/números, o modelo exagerou conclusões de uma análise parcial. Não há rota nem botão dessa feature; helper experimental isolado permanece sem uso pelo produto. O resultado técnico original é preservado.

## Dados e integrações reais

O snapshot comercial preexistente em demo-data é carregado em banco vazio e claramente identificado como armazenado. Não foi fabricada chegada de mensagem Telegram nem compartilhada sessão do collector original.

POST /ai/analyze-pc retornou HTTP 200, Gemini real, modelo gemini-3.5-flash-lite, cached=false. Identificou seis peças do catálogo e retornou compatibilidade parcial — essa limitação foi preservada. Evidência: ai-validation.json.

POST /ai/recommend-upgrades retornou HTTP 200 após a correção do histórico, com resposta estruturada e candidato permitido. Evidência: upgrades-validation.json. Preço ausente continua ausente; nenhuma promoção foi inventada.

GET externo da Product API para MLB28087623 retornou HTTP 200 usando o cliente existente. A tela permanece read-only e usa enrichment persistido. A restrição Item/Price é um estado registrado do projeto, não um novo teste forjado de 403.

## Validação

| Suíte da cópia | Passaram | Outros |
|---|---:|---|
| api-catalogo | 397 | 1 skipped |
| api-orcamentos | 232 | — |
| services | 488 | — |
| frontend | 28 | — |
| Total | 1145 | 1 skipped |

O total histórico 1131 do original inclui 11 testes de api-usuarios, serviço ausente nesta cópia. A demo inclui 25 testes adicionais. Não foram copiadas contagens de execução como se fossem atuais sem rodar as suítes.

- npm run lint: passou.
- npm run build: passou, inclusive na imagem Docker com DEMO_MODE.
- scripts/validate-demo.py: 41 smoke checks passaram (rotas de página, catálogo, promoções, detalhes, ofertas, histórico, matcher, parser, banco, status, contexto e bloqueio de escrita).
- scripts/verify-snippets.py: 29 trechos conferidos com fontes reais.
- scripts/validate-browser.cjs: Chromium headless, 1920×1080 e 1366×768, navegação, abertura/fechamento do código, teclado, matcher e telas do produto; sem erros JS ou overflow horizontal nos painéis verificados.
- 16 screenshots em screenshots/: arquitetura, fluxo usuário-sistema, IA, matcher, Telegram, Mercado Livre, MongoDB e código, nas duas resoluções.
- Depreciações das dependências aparecem nos testes; não impedem execução.

## Operação e limites

Configuração privada local preparada no .env da cópia, ignorado pelo Git/build. Nenhum segredo foi incluído nos documentos. Telegram opcional segue offline nesta demo; para mensagens novas é necessária sessão independente. Ofertas armazenadas envelhecem e não são apresentadas como verificadas agora. Gemini pode falhar por rede/cota/validação; o fallback é identificado. PostgreSQL permanece necessário no boot. APIs IA públicas têm rate limit por worker. Publicação em domínio externo requer URLs públicas, CORS e HTTPS conforme DEPLOY.md.

Documentos: README-DEMO.md, ARCHITECTURE.md, FEATURES.md, PRESENTATION_ROUTE.md, DEPLOY.md e KNOWN_LIMITATIONS.md.
