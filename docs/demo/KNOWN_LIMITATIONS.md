# Limitações conhecidas

- Telegram collector da demo está offline/sem sessão recente. A leitura usa promoções reais armazenadas e informa isso na UI; nenhum evento novo foi encenado.
- Promoções são anúncios e podem estar expiradas. O recorte comercial não representa todo o banco original.
- Product API ML foi consultada com sucesso durante a validação. A tela usa enriquecimento persistido. Item/Price tem restrição externa; não houve scraping nem contorno.
- Product Matcher é conservador e o score não é probabilidade. Links afiliados podem esconder PRODUCT_ID.
- Componentes sem enriquecimento podem mostrar imagem por categoria. Imagens remotas dependem de rede.
- Gemini é externo: timeout, cota, indisponibilidade ou rejeição semântica são falhas possíveis. Somente configuração não comprova disponibilidade.
- O preset resultou em compatibilidade parcial: há peças e regras sem dados suficientes. O resultado não foi alterado para parecer completo.
- Adaptação opcional de linguagem não foi exposta: o teste real mostrou exagero de conclusões. O helper experimental permanece isolado, sem rota ou botão.
- Contexto exibido é reconstruído em nova leitura, não captura exata da chamada anterior.
- As rotas IA são públicas e o limite é por worker. PostgreSQL ainda é necessário no boot.
- Testes emitem avisos de depreciação das dependências. Um teste do catálogo é skipped pela própria suíte.
- Interface foi verificada em Chromium headless nas duas resoluções solicitadas. Fullscreen pode ser negado pelo navegador; há mensagem de fallback para F11.
- Deploy público não executado. O container frontend serve por Nginx; produção pública requer domínio e HTTPS conforme DEPLOY.md.
