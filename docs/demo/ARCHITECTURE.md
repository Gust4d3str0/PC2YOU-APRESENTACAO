# Arquitetura da demo

React/Vite (5174) → FastAPI Catálogo (8012) → MongoDB; React → FastAPI IA (8013) → Catálogo → contexto/compatibilidade → Gemini → validação → React.

O fluxo analyze-pc não usa Product Matcher. `ai_context.enrich` resolve peças pela categoria e correspondência exata. Upgrades usam o matcher para relacionar promoções e catálogo. A lógica crítica permanece no backend: socket, memória, potência, dimensão, preços, IDs e candidatos. Gemini prioriza e explica; Pydantic e validação semântica conferem a resposta.

Telegram → Telethon → filtro → parser → matcher → MongoDB → commerce.snapshot → frontend. Collector e bot são opcionais. A apresentação consulta a promoção armazenada a cada 30 s; não afirma que ela acaba de chegar.

Mercado Livre Product API → normalização → aceitação conservadora → external_product_enrichment/components. Preço vem de ofertas comerciais do Telegram. Item/Price API tem restrição externa registrada. A tela ML usa o cache persistido sem disparar atualizações ou escritas.

PostgreSQL foi mantido para o boot do api-orcamentos (Alembic). api-usuarios foi removida da cópia preexistente; autenticação, favoritos e orçamento salvo não fazem parte da UI demo. Docker Compose tem nomes, volumes e portas exclusivos.

Segurança: `/demo/*` só aceita GET. Coleções explícitas, projeção de campos permitidos, paginação limitada e sanitização recursiva. O guard bloqueia mutações, exceto POSTs exatos de IA, cálculos do wizard/compatibilidade e leitura batch de componentes. Não há queries Mongo arbitrárias. .env é ignorado pelo Git e pelos builds Docker.
