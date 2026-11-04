# Deploy

Build e inicialização locais foram realizados por Docker Compose. Não houve publicação em provedor externo.

1. Copie apenas esta pasta para o servidor, sem .env, .tools, node_modules ou caches; configure credenciais pelo ambiente privado do servidor.
2. Defina DEMO_MODE=true, AI_ENABLED=true, GEMINI_API_KEY e GEMINI_MODEL válido para a conta.
3. Ajuste PUBLIC_CATALOG_API_URL e PUBLIC_AI_API_URL para URLs HTTPS acessíveis pelo navegador; configure CORS_ORIGINS com a origem exata do frontend.
4. Execute docker compose up -d --build e verifique healthchecks e /apresentacao.
5. Para um domínio público, coloque reverse proxy/TLS na frente das APIs e sirva frontend/dist em servidor estático com fallback de SPA para index.html. O container frontend já serve os arquivos estáticos por Nginx, com fallback SPA. TLS e domínio são responsabilidade do ambiente de publicação.
6. Mantenha MongoDB/PostgreSQL internos. Persista volumes da demo. Não conecte os serviços ao banco do projeto original.
7. Execute validate-demo.py com as URLs adaptadas e teste Gemini imediatamente antes da banca.

O seed e o snapshot comercial inicial permitem subir sem Telegram e ML ao vivo. Ofertas envelhecem: o fallback não as torna atuais. O loader só importa o snapshot se telegram_promotions estiver vazia; não sobrescreve promoções existentes.

Telegram é profile opcional. Inicialização da sessão requer uma conta autorizada; não compartilhe sessões em repositórios. Credenciais ML são opcionais para a tela, que funciona com enrichment persistido. Nunca publique .env nem os arquivos privados de tokens.

A IA pública pode consumir cota; existe rate limit por worker, não distribuído. Para exposição ampla, configure controle de acesso/cota no gateway do deploy.
