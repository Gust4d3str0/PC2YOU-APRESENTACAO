import { useCallback, useEffect, useState } from 'react';
import { catalogApi, formatCurrency } from '../api';
import { currentOffers, destinationLabel, conditionLabels } from '../utils/commerce';
import OfferTable from './OfferTable';

export default function OfferComparison({ componentId, onLoad }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const load = useCallback(async () => {
    try { const r = await catalogApi.get(`/components/${componentId}/offers`);setData(r.data);setError(false);onLoad?.(r.data); }
    catch { setError(true); }
  }, [componentId, onLoad]);
  useEffect(() => {load(); const timer = setInterval(load,45000);return () => clearInterval(timer);},[load]);
  const rows = currentOffers(data?.offers);
  const general = data?.best_general_offer;
  const conditional = data?.best_conditional_offer;
  const line = o => `${o.store || 'Loja não identificada'} · ${destinationLabel(o.url_kind)}`;
  return <section id="ofertas" className="summary-panel market-comparison"><h2>Comparação de ofertas</h2>{error ? <p role="alert">Erro ao carregar ofertas. <button onClick={load}>Tentar novamente</button></p> : !data ? <p>Carregando ofertas...</p> : <>
    <div className="best-pair">
      <div><span>Melhor preço geral</span>{general ? <><strong>{formatCurrency(general.price)}</strong><small>{line(general)}</small></> : <strong>Sem oferta geral</strong>}</div>
      <div><span>Melhor preço com condição</span>{conditional ? <><strong>{formatCurrency(conditional.price)}</strong>
        <small>{line(conditional)}</small>
        {conditional.coupon && <small>Cupom anunciado: {conditional.coupon}</small>}
        {conditionLabels(conditional).map(l => <small key={l}>{l}</small>)}</> : <strong>Sem oferta com condição</strong>}</div>
    </div>
    <p>{rows.length ? `${rows.length} ${rows.length === 1 ? 'oferta disponível' : 'ofertas disponíveis'} · preços anunciados no Telegram, confirme na loja antes da compra.` : 'Sem oferta atual'}</p>
    {!!rows.length && <OfferTable offers={rows} bestId={general?.id} bestConditionalId={conditional?.id} onChanged={load}/>}<h3>Ofertas anteriores · histórico</h3>{data.history.length ? <OfferTable offers={data.history} historical/> : <p>Nenhuma oferta histórica para este hardware.</p>}</>}</section>;
}
