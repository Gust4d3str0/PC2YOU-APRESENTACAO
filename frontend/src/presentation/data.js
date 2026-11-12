// Static content of /apresentacao. Everything that changes (counts, status, promotions) comes from the live APIs.
// Numbers below are SNAPSHOTS and are shown with their date (see QUALITY).

export const SECTIONS = [
  ['pc2you', 'PC2YOU'], ['problema', 'Problema'], ['solucao', 'Solução'], ['ux', 'Experiência do usuário'],
  ['arquitetura', 'Arquitetura'], ['fluxo', 'Fluxo completo'], ['ia', 'Inteligência Artificial'],
  ['ia-analise', 'IA de análise'], ['ia-upgrades', 'IA de upgrades'], ['matcher', 'Product Matcher'],
  ['telegram', 'Telegram'], ['mercadolivre', 'Mercado Livre'], ['mongodb', 'MongoDB'], ['codigo', 'Código real'],
  ['demo', 'Demonstração ao vivo'], ['qualidade', 'Testes e qualidade'], ['conclusao', 'Conclusão'],
].map(([id, title], index) => ({ id, title, number: String(index + 1).padStart(2, '0') }));

// ---- architecture graph (viewBox 1060 x 580) ---------------------------------------------------------
export const NODES = [
  { id: 'user', label: 'Usuário', x: 455, y: 14, group: 'user', sub: 'navegador',
    role: 'Quem usa o site: pesquisa componentes, abre ofertas e executa a análise do PC.',
    file: '—', port: '—', input: 'Cliques e formulários', process: 'Interage com a interface React.', output: 'Requisições HTTP via React', deps: ['React'] },
  { id: 'react', label: 'React / Vite', x: 455, y: 98, group: 'frontend', sub: 'frontend', snippet: 'react-analyze',
    role: 'Interface (SPA). Três clientes axios (catálogo, IA, usuários*) e rotas Home, Detalhes, Analisar PC, Montar PC.',
    file: 'frontend/src/App.jsx · api.js · pages/AnalyzePC.jsx', port: '5174 (demo) / 5173', input: 'Ações do usuário',
    process: 'Monta payloads, cancela requisições antigas (AbortController), renderiza respostas.', output: 'Chamadas HTTP JSON às APIs', deps: ['API Catálogo', 'API IA'] },
  { id: 'api_cat', label: 'API Catálogo', x: 150, y: 214, group: 'api', sub: 'FastAPI · :8012', snippet: 'api-catalog-route',
    role: 'Catálogo técnico e leitura comercial: componentes, promoções, ofertas, melhor oferta, imagens, endpoints /demo.',
    file: 'api-catalogo/main.py · commerce.py · services.py', port: '8012 → 8000', input: 'GET /commerce/catalog, /promotions, /components/{id}…',
    process: 'commerce.snapshot (cache 30 s): reavalia promoções com o matcher e calcula status e melhor oferta.', output: 'JSON com ofertas vigentes e histórico', deps: ['MongoDB', 'Product Matcher'] },
  { id: 'api_ia', label: 'API IA', x: 700, y: 214, group: 'api', sub: 'FastAPI · :8013', snippet: 'api-analyze-route',
    role: 'Hospeda /ai/analyze-pc, /ai/recommend-upgrades (serviço api-orcamentos).',
    file: 'api-orcamentos/ai_routes.py · ai_context.py · ai_upgrade_context.py', port: '8013 → 8000', input: 'AnalyzePCRequest',
    process: 'Valida, identifica peças no catálogo, calcula compatibilidade, chama o AIService.', output: 'AnalyzePCResponse / RecommendUpgradesResponse', deps: ['API Catálogo', 'Compatibilidade', 'Gemini', 'PostgreSQL (boot)'] },
  { id: 'postgres', label: 'PostgreSQL', x: 890, y: 214, group: 'db', sub: 'users · favorites · budgets',
    role: 'No projeto completo guarda usuários, favoritos e orçamentos. Aqui só é exigido no boot da API IA (Alembic).',
    file: 'api-orcamentos/alembic · models.py', port: 'interno', input: 'Migrations', process: 'Tabelas relacionais (linhas).', output: '—', deps: [] },
  { id: 'compat', label: 'Compatibilidade + contexto', x: 700, y: 312, group: 'logic', sub: 'ai_context · compatibility', snippet: 'ai-context',
    role: 'Identifica peças (ai_context.enrich), roda as regras (socket, memória, potência, tamanho) e escolhe candidatos antes da IA.',
    file: 'api-orcamentos/ai_context.py · compatibility.py', port: '—', input: 'Nomes das peças + catálogo',
    process: 'Regras determinísticas; regra sem dado fica “não verificada”.', output: 'trusted_context (build, compatibilidade, candidatos)', deps: ['API Catálogo'] },
  { id: 'gemini', label: 'Gemini', x: 700, y: 410, group: 'external', sub: 'IA generativa', snippet: 'ai-gemini',
    role: 'Analisa, prioriza e explica dentro das opções fornecidas pelo backend. Não define compatibilidade, preços nem IDs.',
    file: 'services/ai/provider.py (GeminiProvider)', port: '—', input: 'system prompt + contexto + JSON Schema',
    process: 'Structured output (temperatura 0,2).', output: 'JSON validado depois (Pydantic + regras)', deps: ['GEMINI_API_KEY (servidor)'] },
  { id: 'mongo', label: 'MongoDB', x: 150, y: 330, group: 'db', sub: 'collections · documentos', snippet: 'mongo-indexes',
    role: 'Catálogo, promoções, histórico de preço, enriquecimento do Mercado Livre e estado dos serviços.',
    file: 'api-catalogo/database.py', port: 'interno', input: 'Documentos', process: 'Collections e documentos (não tabelas/linhas).', output: 'Documentos JSON', deps: [] },
  { id: 'matcher', label: 'Product Matcher', x: 425, y: 330, group: 'logic', sub: 'determinístico · não é IA', snippet: 'matcher-score',
    role: 'Liga texto de anúncio a um componente do catálogo: normalização, features, conflitos e score heurístico.',
    file: 'services/product_matching/matcher.py', port: '—', input: 'Texto do anúncio + catálogo',
    process: 'High ≥ 0,85 · Medium ≥ 0,65 · Low < 0,65.', output: 'MatchResult (score, nível, conflitos)', deps: [] },
  { id: 'collector', label: 'Collector + Parser', x: 425, y: 428, group: 'telegram', sub: 'Telethon', snippet: 'tg-process',
    role: 'Lê canais autorizados, filtra, extrai preço/cupom/loja/URL, associa ao catálogo e grava no MongoDB.',
    file: 'services/telegram_collector/collector.py · parser.py · repository.py', port: '—', input: 'Mensagens do Telegram',
    process: 'process_message → parse_message → PromotionRepository.save (upsert idempotente).', output: 'Documento em telegram_promotions', deps: ['Product Matcher', 'MongoDB'] },
  { id: 'telegram', label: 'Telegram', x: 425, y: 510, group: 'external', sub: 'canais de ofertas',
    role: 'Fonte comercial: preços, cupons e links anunciados por canais.', file: '—', port: '—', input: '—', process: 'Mensagens públicas.', output: 'Texto das ofertas', deps: [] },
  { id: 'enrich', label: 'Enrichment ML', x: 150, y: 428, group: 'ml', sub: 'external_product_enrichment', snippet: 'ml-match',
    role: 'Aceita (ou rejeita) o produto do Mercado Livre para um componente, usando o mesmo matcher.',
    file: 'api-catalogo/ml_products.py', port: '—', input: 'Produto normalizado da Product API', process: 'evaluate_match + domínio.', output: 'components.external_enrichment.mercado_livre', deps: ['Product Matcher'] },
  { id: 'ml', label: 'Mercado Livre', x: 150, y: 510, group: 'external', sub: 'Product API · Item/Price restrita', snippet: 'ml-capability',
    role: 'Product API: nome, marca, modelo, imagens e specs; verificar disponibilidade no painel. Item/Price API: 403 PolicyAgent para terceiros (restrita).',
    file: 'api-catalogo/ml_products.py', port: '—', input: 'PRODUCT_ID', process: 'OAuth com refresh rotativo.', output: 'JSON do produto', deps: [] },
];
export const NODE_W = 150;
export const NODE_H = 54;

export const EDGES = [
  ['user', 'react'], ['react', 'api_cat'], ['react', 'api_ia'], ['api_cat', 'mongo'], ['api_ia', 'api_cat'],
  ['api_ia', 'compat'], ['compat', 'gemini'], ['api_ia', 'postgres'], ['api_ia', 'matcher'], ['matcher', 'mongo'],
  ['api_cat', 'matcher'], ['collector', 'matcher'], ['telegram', 'collector'], ['ml', 'enrich'], ['enrich', 'mongo'],
];

// "O que acontece quando o usuário clica?" — path = nodes in order; steps tie each hop to real files/functions.
export const FLOWS = [
  { id: 'analyze', label: 'Analisar PC',
    path: ['user', 'react', 'api_ia', 'api_cat', 'api_ia', 'compat', 'gemini', 'compat', 'api_ia', 'react', 'user'],
    steps: [
      ['AnalyzePC.jsx · submit', 'POST /ai/analyze-pc com o formulário', 'react-analyze'],
      ['ai_routes.analyze_pc', 'valida (Pydantic + technical_text) e checa AI_ENABLED/chave', 'api-analyze-route'],
      ['ai_context.enrich', 'busca cada peça no catálogo (GET /components) — SEM Product Matcher', 'ai-enrich'],
      ['ai_context.check_compatibility', 'regras por socket, memória, potência e tamanho', 'ai-context'],
      ['AIService.run_cached', 'cache SHA-256, 1 chamada por vez, limite por minuto', 'ai-cache'],
      ['GeminiProvider.generate', 'structured output com JSON Schema', 'ai-gemini'],
      ['_validate_analysis + validate_prose', 'candidatos, orçamento e texto sem números inventados', 'ai-validate'],
      ['PCAnalysisResult.jsx', 'exibe análise; veredito de compatibilidade é do backend', 'react-analyze'],
    ] },
  { id: 'upgrades', label: 'Receber upgrade',
    path: ['user', 'react', 'api_ia', 'api_cat', 'api_ia', 'matcher', 'mongo', 'matcher', 'api_ia', 'compat', 'gemini', 'compat', 'api_ia', 'react', 'user'],
    steps: [
      ['UpgradeRecommendations.jsx', 'POST /ai/recommend-upgrades (include_promotions)', 'react-analyze'],
      ['build_upgrade_bundle', 'catálogo por categoria + promoções Telegram das últimas 72 h (Mongo, só leitura)', 'ai-context'],
      ['normalized_promotions', 'enrich_promotion → Product Matcher: só High sem conflito', 'matcher-select'],
      ['history_stats / prices', 'histórico verificado e menor preço real', 'mongo-best'],
      ['replacement_compatibility', 'troca a peça atual e reexecuta as regras', 'ai-context'],
      ['upgrade_schema', 'candidate_id restrito por enum aos candidatos do backend', 'ai-gemini'],
      ['validate_choices', 'tipo, orçamento, combinação e oportunidade elegível', 'ai-validate'],
    ] },
  { id: 'search', label: 'Pesquisar componente',
    path: ['user', 'react', 'api_cat', 'mongo', 'api_cat', 'react', 'user'],
    steps: [
      ['Home.jsx', 'GET /commerce/catalog?q=', 'api-catalog-route'],
      ['main.commerce_catalog', 'filtra componentes e anexa ofertas vigentes', 'api-catalog-route'],
      ['commerce.build_snapshot', 'promoções → matcher → status → melhor oferta (cache 30 s)', 'mongo-best'],
      ['ComponentCard.jsx', 'cartão com melhor oferta e imagem (prioridade de imagem)', 'react-images'],
    ] },
  { id: 'offer', label: 'Abrir oferta / histórico',
    path: ['user', 'react', 'api_cat', 'mongo', 'api_cat', 'react', 'user'],
    steps: [
      ['ComponentDetails.jsx', 'GET /components/{id} e /components/{id}/offers', 'api-catalog-route'],
      ['commerce.best_offer', 'melhor geral × melhor condicional; destino produto vence busca', 'mongo-best'],
      ['offerLabel', 'rótulo honesto: “anunciada”, “condicional”, “confirmada”, “expirada”', 'react-offer-label'],
    ] },
  { id: 'promotion', label: 'Promoção do Telegram',
    path: ['telegram', 'collector', 'matcher', 'mongo', 'api_cat', 'react', 'user'],
    steps: [
      ['process_message', 'valida o canal, filtra, parseia e salva', 'tg-process'],
      ['extract_prices / parse_message', 'preço, cupom, loja, URL e condições', 'tg-parse'],
      ['PromotionRepository.save', 'enrich_promotion + upsert idempotente', 'mongo-save'],
      ['commerce.build_snapshot', 'status recalculado a cada leitura', 'tg-status'],
    ] },
  { id: 'ml', label: 'Enriquecimento Mercado Livre',
    path: ['ml', 'enrich', 'mongo', 'api_cat', 'react', 'user'],
    steps: [
      ['extract_product_id', 'PRODUCT_ID a partir de /p/MLB…', 'ml-ids'],
      ['MercadoLivreTokenManager.refresh', 'OAuth com refresh rotativo', 'ml-refresh'],
      ['evaluate_match', 'só “matched” sem conflito enriquece', 'ml-match'],
      ['resolve_image', 'imagem oficial entra na prioridade de imagem', 'react-images'],
    ] },
];

export const PRESET = {
  label: 'Ryzen 5 5600 + RTX 3060 12 GB + 16 GB DDR4 + SSD + fonte 650 W',
  payload: {
    components: {
      cpu: 'AMD Ryzen 5 5600', gpu: 'GeForce RTX 3060 12 GB', motherboard: 'Placa-mãe B550M AM4 DDR4',
      ram: 'Kingston Fury Beast 16GB DDR4 3200MHz', storage: ['Kingston NV3 1TB NVMe M.2'],
      psu: 'Fonte 650W 80 Plus Bronze', case: 'Gabinete Gamer Rise Mode Glass',
    },
    usage: ['gaming'], resolution: '1080p', refresh_rate: 144, monitor: null, games: [], upgrade_budget: null,
  },
};

export const MATCHER_EXAMPLES = [
  'Placa de Vídeo RTX 5060 Ti 8GB Gigabyte Windforce OC por R$ 2.789,00',
  'Processador AMD Ryzen 7 7800X3D 4.2GHz AM5',
  'Placa de vídeo RTX 5060 Ti',
  'Ryzen 7 7800X3D por R$ 2.399',
  'Kit Upgrade Ryzen 5 5600 + B550M',
  'Memória RAM DDR5 16GB 6000MHz',
];

export const TELEGRAM_STEPS = [
  ['Canal Telegram', 'Mensagens de canais autorizados (TELEGRAM_ALLOWED_CHATS).', 'tg-process'],
  ['Telethon', 'Conta de usuário (não bot) ouve eventos e importa histórico.', 'tg-process'],
  ['Filtro', 'is_possible_promotion: contém R$ ou palavra-chave.', 'tg-process'],
  ['Parser', 'parse_message: preço, cupom, loja, URL, condições.', 'tg-parse'],
  ['Preço / Cupom / Loja / URL', 'extract_prices, extract_coupon, identify_store, select_offer_url.', 'tg-prices'],
  ['Product Matcher', 'enrich_promotion liga o texto a um componente (High/Medium/Low).', 'matcher-score'],
  ['MongoDB', 'upsert $setOnInsert por (chat_id, message_id): idempotente.', 'mongo-save'],
  ['Commerce API', 'build_snapshot calcula status e melhor oferta na leitura.', 'tg-status'],
  ['Frontend', 'PromotionSection / OfferComparison com rótulos honestos.', 'react-offer-label'],
];

export const QUALITY = {
  date: '2026-11-04',
  note: 'Snapshot da engenharia reversa do projeto completo (PC2YOU) e da cópia de apresentação.',
  suites: [
    { name: 'api-usuarios', count: 11, note: 'projeto completo (fora da demo)' },
    { name: 'api-orcamentos', count: 230, note: 'IA, wizard, orçamentos' },
    { name: 'api-catalogo', count: 377, note: '+ 1 skipped' },
    { name: 'services', count: 485, note: 'IA, matcher, Telegram' },
    { name: 'frontend', count: 28, note: 'vitest' },
  ],
  total: 1131,
  checks: [['Lint (eslint)', 'OK'], ['Build (vite)', 'OK']],
  demoSuites: [],
};

