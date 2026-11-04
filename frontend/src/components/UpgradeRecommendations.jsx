import { useEffect, useRef, useState } from 'react';
import { LoaderCircle, Sparkles } from 'lucide-react';
import HardwareImage from './HardwareImage';
import { budgetsApi, formatCurrency, getApiErrorMessage } from '../api';

const sourceLabels = { telegram: 'Oferta coletada no Telegram', catalog_real: 'Preço real no catálogo',
  catalog_reference: 'Referência do catálogo sem atualização recente', unavailable: 'Preço não disponível' };
const confidenceLabels = { low: 'Baixa', medium: 'Média', high: 'Alta' };
const budgetLabels = { within_budget: 'Preço conhecido dentro do orçamento', no_budget: 'Sem orçamento informado',
  price_unavailable: 'Sem preço real verificado para confirmar o orçamento', save_budget: 'Considere reservar o orçamento' };

function safeOfferUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? value : null;
  } catch { return null; }
}

export default function UpgradeRecommendations({ payload }) {
  const [includePromotions, setIncludePromotions] = useState(true);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(null);
  useEffect(() => () => request.current?.abort(), []);

  const recommend = async () => {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true); setError(''); setResult(null);
    try {
      const { data } = await budgetsApi.post('/ai/recommend-upgrades', {
        ...payload, include_promotions: includePromotions,
      }, { signal: controller.signal, timeout: 130000 });
      if (!controller.signal.aborted) setResult(data);
    } catch (err) {
      if (!controller.signal.aborted) setError(getApiErrorMessage(err, 'Não foi possível buscar upgrades. Tente novamente.'));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
      request.current = null;
    }
  };

  return <section className="analysis-result" aria-label="Upgrades recomendados">
    <div className="summary-panel analysis-card">
      <span className="eyebrow">AI v2 · Upgrades recomendados</span>
      <h2>Opções para o seu próximo upgrade</h2>
      <p>Para a configuração analisada acima, consulte opções do catálogo e preços conhecidos.
        A recomendação depende dos dados técnicos disponíveis.</p>
      <label className="upgrade-promotion-toggle"><input type="checkbox" checked={includePromotions} disabled={loading}
        onChange={(e) => setIncludePromotions(e.target.checked)} /> Incluir ofertas já coletadas pelo Telegram</label>
      <div className="analyze-submit"><button type="button" className="btn-primary" disabled={loading} onClick={recommend}>
        {loading ? <LoaderCircle size={18} className="analysis-spinner" /> : <Sparkles size={18} />}
        {loading ? 'Buscando upgrades recomendados...' : 'Buscar upgrades recomendados'}
      </button><span role="status">{loading ? 'Verificando opções, preços e recomendações...' : 'Nenhuma peça será alterada ou comprada automaticamente.'}</span></div>
    </div>
    {error && <div className="error-msg" role="alert">{error}</div>}
    {result && <div className="upgrade-results" aria-live="polite">
      <section className="summary-panel analysis-card"><h3>Upgrades recomendados</h3><p>{result.analysis.summary}</p>
        {result.metadata.cached && <small>Análise recente reutilizada.</small>}
        {!result.recommendations.length && <p>Nenhum modelo foi selecionado. Confirme os nomes completos das peças e os dados de compatibilidade.</p>}
      </section>
      {result.recommendations.map((item) => {
        const choice = result.analysis.recommended_upgrades.find((c) => c.candidate_id === item.candidate_id);
        const offer = item.promotion;
        const url = offer ? safeOfferUrl(offer.url) : null;
        const opportunity = result.analysis.buy_now_opportunities.some((o) => o.candidate_id === item.candidate_id);
        return <article className="summary-panel analysis-card" key={item.candidate_id}>
          <span className="eyebrow">Prioridade {choice.priority} · Confiança {confidenceLabels[choice.confidence]}</span>
          <HardwareImage component={{...item.component, id: item.candidate_id}} className="upgrade-hardware-image"/><h3>{item.component.name}</h3><p>{choice.reason}</p>
          <p><strong>{!item.price.verified ? 'Sem oferta atual' : formatCurrency(item.price.value)}</strong><br />
            <small>{item.price.verified ? sourceLabels[item.price.source] : 'Sem preço vigente confiável'}{item.price.store ? ` · ${item.price.store}` : ''}</small>
            {item.price.verified && item.price.conditional && <><br /><small>Preço com condição anunciada: {(item.price.conditions || []).join(' · ') || 'condição não detalhada'}</small></>}</p>
          <p>{budgetLabels[choice.budget_relevance]}</p>
          {!offer && item.price.source === 'catalog_real' && <p>Preço disponível no catálogo.</p>}
          {!item.price.verified && item.price.value !== null && <p>Preço de referência: não confirma o custo atual nem que a opção cabe no orçamento.</p>}
          {offer && <div className="analysis-candidate"><strong>Oferta encontrada</strong>
            <p>{formatCurrency(offer.price)} · {offer.store || 'Loja não identificada'}</p>
            {offer.coupon && <p>Cupom anunciado: <strong>{offer.coupon}</strong></p>}
            {offer.is_conditional && (offer.conditions || []).length > 0 && <p>Condição: {offer.conditions.join(' · ')}</p>}
            {opportunity && <p>Preço competitivo em comparação com os dados fornecidos. Avalie a oportunidade.</p>}
            {url ? <a className="secondary-button" href={url} target="_blank" rel="noopener noreferrer">Ver oferta</a>
              : <p>URL da oferta não disponível.</p>}
            <small>Oferta observada, sem confirmação de estoque. Confira preço, cupom e destino na loja.</small>
          </div>}
          <p><strong>Compatibilidade:</strong> {item.compatibility.valid === true
            ? 'Verificada nas regras aplicáveis à substituição.' : 'Verificação parcial; confirme os dados pendentes antes de comprar.'}</p>
          {item.compatibility.warnings.length > 0 && <ul>{item.compatibility.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
          {item.history && <p>Histórico real: mínimo {formatCurrency(item.history.historical_min)};
            média dos mínimos diários {formatCurrency(item.history.historical_average)} ({item.history.samples} dias).</p>}
        </article>;
      })}
      {(result.warnings.length > 0 || result.analysis.warnings.length > 0) && <section className="summary-panel analysis-card">
        <h3>Antes de decidir</h3><ul>{[...result.warnings, ...result.analysis.warnings].map((w, i) => <li key={i}>{w}</li>)}</ul>
      </section>}
      <section className="summary-panel analysis-card analysis-final"><h3>Orientação final</h3><p>{result.analysis.final_recommendation}</p></section>
    </div>}
  </section>;
}
