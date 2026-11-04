import { formatCurrency } from '../api';
import OfferValidation from './OfferValidation';
import { safeLink, destinationLabel, offerLabel, announcedAgo, conditionLabels } from '../utils/commerce';

const HISTORICAL_KEEP = ['Expirada', 'Não funciona mais'];

export default function OfferTable({ offers, historical = false, bestId, bestConditionalId, onChanged }) {
  return <div className="offer-table-wrap"><table className="offer-table"><thead><tr><th>Loja</th><th>Preço</th><th>Cupom</th><th>Condições</th><th>Status</th><th>Destino</th></tr></thead>
    <tbody>{offers.map((o, i) => {
      const label = offerLabel(o);
      const conditions = conditionLabels(o);
      return <tr key={`${o.id}-${i}`} className={o.id === bestId || o.id === bestConditionalId ? 'is-best' : ''}>
        <td>{o.store || 'Loja não identificada'}<small>{o.source === 'telegram' ? 'Telegram' : o.source}</small></td>
        <td>{formatCurrency(o.price)}<small>{o.coupon ? 'Com cupom' : 'Preço anunciado'}</small></td>
        <td>{o.coupon ? `Cupom anunciado: ${o.coupon}` : '—'}</td>
        <td>{conditions.length ? conditions.join(' · ') : (o.coupon ? 'Condições não informadas' : '—')}</td>
        <td>{historical ? (HISTORICAL_KEEP.includes(label) ? label : 'Histórico') : label}
          {o.id === bestId && <small>Melhor oferta</small>}{o.id === bestConditionalId && o.id !== bestId && <small>Melhor com condição</small>}
          <small>{announcedAgo(o.captured_at)}</small>
          {!historical && <OfferValidation offer={o} onChanged={onChanged}/>}</td>
        <td>{destinationLabel(o.url_kind)}{!historical && safeLink(o.url) ? <small><a href={o.url} target="_blank" rel="noopener noreferrer">Ver oferta ↗</a></small> : null}</td>
      </tr>;
    })}</tbody></table></div>;
}
