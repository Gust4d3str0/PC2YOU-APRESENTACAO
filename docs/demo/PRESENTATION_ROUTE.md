# Rota /apresentacao

Disponível apenas no build com VITE_DEMO_MODE=true. App carrega a apresentação por lazy import. `Presentation.jsx` controla seções, hash, teclado, tela cheia e drawer; `Architecture.jsx` implementa o grafo; `AiSections.jsx` demonstra IA; `DataSections.jsx` reúne matcher, Telegram, ML, banco e status.

Seções: PC2YOU, Problema, Solução, Experiência do usuário, Arquitetura, Fluxo completo, Inteligência Artificial, IA de análise, IA de upgrades, Product Matcher, Telegram, Mercado Livre, MongoDB, Código real, Demonstração ao vivo, Testes e qualidade, Limitações, Conclusão.

Links diretos usam hash, por exemplo `/apresentacao#arquitetura`. O drawer prende o foco, Escape fecha e devolve foco ao controle anterior. A navegação não intercepta setas de campos ou botões.

Demo catálogo: GET /demo/status, /metrics, /database, /database/{name}, /matcher?text=, /telegram-samples, /telegram-parse?text=, /telegram-latest, /ml-components e /ml-example?component_id=.

Demo IA: GET /demo/ai-status; GET /demo/ai-context?configuration=JSON validado e limitado. A análise real continua POST /ai/analyze-pc. Upgrades: POST /ai/recommend-upgrades. Esses endpoints de IA não pertencem ao namespace read-only /demo.

Code Explorer: snippets.json contém arquivo, intervalo, linguagem, trecho, explicação, entrada e saída. `scripts/verify-snippets.py` confere igualdade com o código da cópia. Não lê arquivos por caminho fornecido pelo navegador.

Os estados da IA são confirmados somente após resposta. Cache é identificado, sem alegar nova chamada ao Gemini. O contexto é reconstruído por uma leitura separada; pode diferir de uma análise anterior se o catálogo mudar.


## Leitura guiada do código

O explorador oferece Exibir comentários e Ocultar comentários, tanto na seção Código real quanto no painel aberto pelos diagramas. A escolha é mantida ao trocar de trecho ou reabrir o painel durante a apresentação. O modo original continua como padrão.

Cada um dos 29 trechos tem resumo em O que faz, Por que existe e Na prática. Com comentários ativos, uma explicação em português aparece abaixo de cada linha não vazia, preservando o código e sua numeração original. Linhas em branco continuam como separação visual. Há explicações cadastradas para todas as 588 linhas, incluindo separadores.

As anotações ficam em snippetGuides.json, separadas dos arquivos executáveis do sistema. Cada guia é vinculado ao conteúdo exato do snippet; se ele mudar, um guia antigo não é exibido. Testes conferem cobertura de todas as linhas, correspondência com o código, ausência de anotações no modo original e escape de HTML.

Validação desta melhoria: 61 testes de frontend passaram; lint e build aprovados. Os serviços backend não foram alterados.
