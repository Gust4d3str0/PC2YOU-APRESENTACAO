"""Extract the REAL code shown in /apresentacao (Code Explorer) from the repository files.

    python scripts/build_snippets.py        # rewrites frontend/src/presentation/snippets.json

Every snippet is a contiguous range of real lines (no rewriting). The unit test
api-catalogo/tests/test_demo_presentation.py re-reads the files and fails if a snippet drifted or if a
secret-looking string slipped in.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend/src/presentation/snippets.json"
SECRET = re.compile(r"AIza[\w-]{10,}|sk-[\w-]{10,}|eyJ[\w-]+\.[\w-]+\.[\w-]+|[\w.+-]+@[\w-]+\.[a-z]{2,}|\bpassword\s*=\s*['\"][^'\"]+", re.I)

# tab, id, title, file, first line, last line, language, explanation, input, output
S = [
    ("React", "react-analyze", "Envio da análise", "frontend/src/pages/AnalyzePC.jsx", 45, 58, "jsx",
     "Monta o payload (storage separado por ';'), cancela chamadas antigas com AbortController e chama a API de IA com timeout de 130 s.",
     "Campos do formulário (CPU, GPU, RAM…), usos em ordem de prioridade, resolução, orçamento.",
     "`data` = AnalyzePCResponse, exibido por PCAnalysisResult.jsx."),
    ("React", "react-offer-label", "Rótulos honestos de oferta", "frontend/src/utils/commerce.js", 16, 27, "js",
     "Traduz status/estado da oferta em texto. Um anúncio nunca é chamado de 'ativo': só 'anunciada', 'condicional' ou 'confirmada'.",
     "Oferta projetada por api-catalogo/commerce.py (status, state, valid_until, fresh_until).",
     "Rótulo em português mostrado nos cartões."),
    ("React", "react-images", "Prioridade de imagem", "frontend/src/utils/commerce.js", 47, 58, "js",
     "Ordem de candidatos: promoção → imagem oficial do Mercado Livre (se o matcher aceitou) → real_image → images[] → local → fallback por categoria.",
     "Componente com external_enrichment, real_image, images, current_offers.",
     "Lista ordenada de URLs; HardwareImage tenta a próxima se uma falhar."),
    ("FastAPI", "api-analyze-route", "Rota POST /ai/analyze-pc", "api-orcamentos/ai_routes.py", 62, 75, "python",
     "Valida (Pydantic), verifica disponibilidade da IA ANTES de tocar o catálogo, monta contexto e delega ao AIService. Erros viram HTTP com código estável.",
     "AnalyzePCRequest (JSON).", "AnalyzePCResponse ou HTTPException {code, message}."),
    ("FastAPI", "api-catalog-route", "Rota GET /commerce/catalog", "api-catalogo/main.py", 472, 488, "python",
     "Lê o snapshot comercial em cache (30 s) e devolve cada componente com ofertas vigentes e melhor oferta geral/condicional.",
     "q, category.", "{items: [componente + current_offers + best_*_offer], total}."),
    ("IA", "ai-enrich", "Identificação determinística da peça", "api-orcamentos/ai_context.py", 91, 117, "python",
     "Busca literal mais snapshot da categoria; normaliza acentos, pontuação, espaços e posição da marca com utilitários do Product Matcher. Só aceita uma identidade; ambíguo → dado do usuário.",
     "Nome digitado + categoria.", "Componente do catálogo (specs/compatibilidade) ou entrada 'user' sem specs."),
    ("IA", "ai-context", "Contexto confiável × não confiável", "api-orcamentos/ai_context.py", 183, 201, "python",
     "Percorre os componentes informados, identifica cada um e registra o que faltou (missing_information) antes de calcular compatibilidade.",
     "AnalyzePCRequest + cliente do catálogo.", "trusted_context (build, compatibility, candidatos) e user_context."),
    ("IA", "ai-cache", "Cache, trava e limite de taxa", "services/ai/service.py", 33, 63, "python",
     "Uma chamada por vez (429 'busy'), cache SHA-256 do contexto, janela de 60 s com limite por minuto. Hit de cache não gasta chamada ao Gemini.",
     "contexto + versão do prompt + operação.", "Resposta (possivelmente cacheada, metadata.cached=true)."),
    ("IA", "ai-validate", "Validação semântica pós-LLM", "services/ai/service.py", 104, 119, "python",
     "O candidate_id precisa existir na lista do backend e ter o mesmo tipo; budget_relevance e soma dos preços são conferidos.",
     "PCAnalysis do modelo + contexto.", "Candidatos selecionados ou ContractViolation → HTTP 502."),
    ("IA", "ai-prompt", "Regras de segurança do prompt", "services/ai/prompts.py", 19, 30, "text",
     "Trecho do prompt de sistema: user_context é dado, não instrução; só trusted_context tem verdade calculada; não contradizer compatibilidade.",
     "—", "Instrução de sistema enviada ao Gemini."),
    ("IA", "ai-gemini", "Chamada ao Gemini com structured output", "services/ai/provider.py", 34, 50, "python",
     "temperature 0,2, JSON Schema como contrato, function-calling desativado, timeout configurável e uma única tentativa.",
     "system prompt + contexto + schema.", "dict JSON (ou AIError com código estável)."),
    ("IA", "ai-prose", "Barreira contra invenção no texto", "services/ai/prose.py", 23, 39, "python",
     "Rejeita preços, FPS, porcentagens e nomes de peças que não estejam no contexto; o veredito 'compatível' é do backend.",
     "Texto livre do modelo + contexto.", "OK ou ContractViolation."),
    ("Matcher", "matcher-normalize", "Normalização de texto", "services/product_matching/normalization.py", 13, 22, "python",
     "ASCII minúsculo, remove URLs, cola unidades (16 gb → 16gb), junta sufixos de modelo (7800 x3d → 7800x3d). Nunca descarta sufixos que identificam o produto.",
     "Texto livre de anúncio.", "Texto normalizado."),
    ("Matcher", "matcher-thresholds", "Limiares e regex de modelo", "services/product_matching/matcher.py", 8, 15, "python",
     "Versão do algoritmo, limiares High ≥ 0,85 e Medium ≥ 0,65 e regex de GPU/CPU.", "—", "Constantes usadas em toda a pontuação."),
    ("Matcher", "matcher-score", "Pontuação e níveis", "services/product_matching/matcher.py", 121, 155, "python",
     "Conflito → 0,20. Senão: 0,05 categoria + 0,80 se o modelo bate (0,35 se não) + pesos de sinais, com tetos por falta de informação.",
     "Features de produto e componente.", "MatchResult(score, nível, sinais, conflitos)."),
    ("Matcher", "matcher-select", "Escolha no catálogo", "services/product_matching/matcher.py", 169, 189, "python",
     "Mais de um candidato aceitável → 'variant_ambiguous' sem id. Sem candidato → devolve só diagnóstico.",
     "Produto + catálogo.", "MatchResult com ou sem component_id."),
    ("Telegram", "tg-process", "process_message", "services/telegram_collector/collector.py", 37, 71, "python",
     "Valida a origem permitida, filtra, parseia, monta o documento (status 'parsed') e salva; resolve links em background.",
     "Mensagem Telethon + entidade do canal.", "True se uma promoção nova foi salva."),
    ("Telegram", "tg-prices", "extract_prices", "services/telegram_collector/parser.py", 48, 76, "python",
     "Ignora parcelas e frete; rótulos 'de/antes' = preço original, 'por/pix/à vista' = atual. Só aceita um único preço atual.",
     "Texto da mensagem.", "(preço, preço original) ou (None, None)."),
    ("Telegram", "tg-parse", "parse_message", "services/telegram_collector/parser.py", 110, 137, "python",
     "Preço, loja, cupom, URL escolhida, validade e condições; informação ambígua permanece None.",
     "Texto + URLs de botões/entidades + data.", "Dict {product, offer, links}."),
    ("Telegram", "tg-url", "select_offer_url", "services/telegram_collector/links.py", 48, 62, "python",
     "Prefere URL de botão com caminho de produto em loja conhecida; descarta redes sociais e imagens.",
     "URLs por origem.", "Melhor URL ou None."),
    ("Telegram", "tg-conditions", "extract_conditions", "services/product_matching/offers.py", 110, 130, "python",
     "Condições (cupom, primeira compra, app, PIX, assinatura, pedido mínimo, validade) por regex; desconhecido fica None, nunca False.",
     "Texto, cupom, data do anúncio.", "Dict conditions (versão 2)."),
    ("Telegram", "tg-status", "evaluate_offer (núcleo)", "services/product_matching/offers.py", 214, 235, "python",
     "Status comercial calculado na leitura: expired, announced/conditional, confirmed (checagem recente), stale (idade).",
     "Oferta + relógio.", "{status, reason, eligible, freshness}."),
    ("MongoDB", "mongo-indexes", "Índices do catálogo", "api-catalogo/database.py", 16, 46, "python",
     "Cria índice único em `id` (recusa duplicatas existentes) e índices de category/brand/name.",
     "Collection components.", "Índices uq_components_id, ix_components_*."),
    ("MongoDB", "mongo-save", "Gravação idempotente da promoção", "services/telegram_collector/repository.py", 36, 52, "python",
     "Enriquece com o matcher e faz upsert com $setOnInsert pela chave (chat_id, message_id): reimportar não duplica nem sobrescreve.",
     "Documento da promoção.", "True se inseriu; False se já existia."),
    ("MongoDB", "mongo-best", "Melhor oferta geral × condicional", "api-catalogo/commerce.py", 110, 132, "python",
     "Preço efetivo com penalidade de 5% para destino que não é produto; best_general sem condição, best_conditional com condição.",
     "Linhas de oferta elegíveis.", "Uma oferta ou None."),
    ("Mercado Livre", "ml-ids", "PRODUCT_ID × ITEM_ID", "services/product_matching/ml_ids.py", 31, 38, "python",
     "Só devolve o PRODUCT_ID se for exatamente um em URLs do Mercado Livre (/p/MLB…). ITEM_ID é outra função.",
     "URLs da oferta.", "'MLB…' ou None."),
    ("Mercado Livre", "ml-refresh", "Refresh rotativo do token", "api-catalogo/ml_products.py", 106, 135, "python",
     "Um refresh por vez, novo refresh_token persistido em arquivo, bloqueio de 60 s após falha. Nenhum token é registrado em log.",
     "Token expirado.", "True/False; tokens atualizados em disco."),
    ("Mercado Livre", "ml-match", "Aceite do enriquecimento", "api-catalogo/ml_products.py", 316, 343, "python",
     "Reaproveita o matcher do PC2YOU + domínio do produto; só 'matched' sem conflito enriquece o componente.",
     "Produto normalizado do ML + componente.", "{status, confidence, conflicts}."),
    ("Mercado Livre", "ml-capability", "Price API restrita (403)", "api-catalogo/ml_products.py", 413, 433, "python",
     "403 é uma CAPACIDADE negada, não um veredito sobre a oferta: registra 'restricted' e nada é invalidado.",
     "ITEM_ID.", "{status: available|forbidden|…} e estado persistido."),
]


def build():
    snippets = []
    for tab, sid, title, rel, a, b, lang, explanation, entry, output in S:
        lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        chunk = lines[a - 1:b]
        assert 8 <= len(chunk) <= 36, f"{sid}: {len(chunk)} lines"
        code = "\n".join(chunk)
        assert not SECRET.search(code), f"{sid}: secret-looking text"
        snippets.append({"id": sid, "tab": tab, "title": title, "file": rel, "start": a, "end": b, "language": lang,
                         "code": code, "explanation": explanation, "input": entry, "output": output})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snippets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(snippets)} snippets -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
