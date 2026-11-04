import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Flame, ArrowUpRight, RefreshCw, History, Copy, Check } from 'lucide-react';
import { catalogApi, formatCurrency } from '../api';
import HardwareImage from './HardwareImage';
import OfferTable from './OfferTable';
import OfferValidation from './OfferValidation';
import { offerLabel, isCurrent, isConfirmed, announcedAgo, conditionLabels, safeLink, currentOffers, copyText, destinationLabel } from '../utils/commerce';

const WARNING = { search: 'Leva à busca da loja, não ao produto.', homepage: 'Leva à página inicial da loja.' };

function OfferComparePanel({ componentId, onChanged }) {
  const [rows, setRows] = useState(null);
  const [bestId, setBestId] = useState(null);
  useEffect(() => {
    let stopped = false;
    catalogApi.get(`/components/${componentId}/offers`).then(r => { if (!stopped) { setRows(currentOffers(r.data.offers)); setBestId(r.data.best_offer?.id); } }).catch(() => { if (!stopped) setRows([]); });
    return () => { stopped = true; };
  }, [componentId]);
  return <div className="deal-compare">{rows ? (rows.length ? <OfferTable offers={rows} bestId={bestId} onChanged={onChanged}/> : <small>Sem ofertas vigentes para comparar.</small>) : <small>Carregando ofertas...</small>}</div>;
}

export function PromotionCard({ offer, onChanged }) {
  const label = offerLabel(offer);
  const active = isCurrent(offer);
  const conditions = conditionLabels(offer);
  const url = safeLink(offer.url);
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(false);
  const copy = async () => { if (await copyText(offer.coupon)) { setCopied(true); setTimeout(() => setCopied(false), 2000); } };
  return <article className={`deal-card ${active ? '' : 'deal-historical'}`}>
    <Link className="deal-image" data-category={offer.category} to={`/components/${offer.component_id}`}><HardwareImage component={{...offer, id: offer.component_id}}/>
      <span className={`deal-status ${active ? 'live' : ''}`}>{label}</span></Link>
    <div className="deal-body"><div className="deal-meta"><span>{offer.store || 'Loja não identificada'}</span><span>Telegram</span></div>
      <Link className="deal-title" to={`/components/${offer.component_id}`}>{offer.name}</Link>
      <span className="deal-brand">{[offer.brand, offer.category].filter(Boolean).join(' · ')}</span>
      {offer.original_price && <del>{formatCurrency(offer.original_price)}</del>}
      <div className="deal-price"><strong>{formatCurrency(offer.price)}</strong>{offer.discount_percent && <span>−{offer.discount_percent}% anunciado</span>}</div>
      {offer.coupon && active && <small>com cupom <b>{offer.coupon}</b></small>}
      <small>{active ? (offer.coupon ? 'Preço condicionado ao cupom' : 'Preço anunciado') : 'Preço histórico · não é oferta atual'}</small>
      {offer.coupon ? <div className="coupon"><span>Cupom anunciado: <strong>{offer.coupon}</strong></span>
        <button type="button" className="coupon-copy" onClick={copy}>{copied ? <Check size={13}/> : <Copy size={13}/>} Copiar cupom</button>
        {copied && <em role="status">Cupom copiado</em>}</div> : <small>Sem cupom anunciado</small>}
      {conditions.length > 0 && <small className="deal-conditions">Condição: {conditions.join(' · ')}</small>}
      {offer.coupon && conditions.length === 0 && <small className="deal-conditions-unknown">Condições não informadas no anúncio.</small>}
      {offer.conditions_text && conditions.length > 0 && <small className="deal-conditions-text">“{offer.conditions_text}”</small>}
      {offer.valid_until ? <small>Prazo anunciado: {new Date(offer.valid_until).toLocaleString('pt-BR')}</small> : <small>Validade não informada</small>}
      <small title={offer.captured_at ? new Date(offer.captured_at).toLocaleString('pt-BR') : undefined}>{announcedAgo(offer.captured_at)}</small>
      {active && (isConfirmed(offer) ? <small className="deal-trust is-confirmed">✓ Oferta confirmada recentemente</small>
        : <small className="deal-trust">Preço anunciado no Telegram. Confirme na loja antes da compra.</small>)}
      {active && url ? <><a className="btn-primary" href={url} target="_blank" rel="noopener noreferrer">Ver oferta <ArrowUpRight size={16}/></a>
        <small className={`dest dest-${offer.url_kind}`}>Destino: {destinationLabel(offer.url_kind)}{WARNING[offer.url_kind] && ` · ${WARNING[offer.url_kind]}`}</small></>
        : <Link className="secondary-button" to={`/components/${offer.component_id}`}>Ver hardware e histórico</Link>}
      {active && offer.offers_count > 1 && <><button type="button" className="deal-compare-toggle" aria-expanded={open} onClick={() => setOpen(o => !o)}>{offer.offers_count} ofertas disponíveis</button>
        {open && <OfferComparePanel componentId={offer.component_id} onChanged={onChanged}/>}</>}
      {active && <OfferValidation offer={offer} onChanged={onChanged}/>}
    </div></article>;
}

const MODES = {
  active: { status: 'active', id: 'promocoes', title: '🔥 Promoções ativas', icon: Flame, empty: 'Nenhuma promoção ativa no momento.',
    total: 'promoções ativas' },
  history: { status: 'recent', id: 'historico', title: 'Ofertas recentes · histórico', icon: History, empty: 'Nenhuma oferta recente encontrada.',
    total: 'anúncios no histórico' },
};

export default function PromotionSection({ category = '', mode = 'active' }) {
  const cfg = MODES[mode];
  const [page, setPage] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const request = useRef(null);
  const load = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    try {
      const response = await catalogApi.get('/promotions', {params:{status:cfg.status, category, limit:4, skip:page*4}, signal:controller.signal});
      if (!controller.signal.aborted) {setData(response.data);setError(false);}
    } catch { if (!controller.signal.aborted) setError(true); }
  }, [cfg.status, category, page]);
  useEffect(() => { let stopped = false; const run = () => { if (!stopped) load(); }; run();
    const timer = setInterval(run, 45000); return () => { stopped = true; clearInterval(timer);request.current?.abort(); }; }, [load]);
  const Icon = cfg.icon;
  return <section id={cfg.id} className="market-section">
    <div className="market-heading"><div><h2>{cfg.title}</h2></div>
      <span className="refresh-note"><RefreshCw size={13}/> Atualização a cada 45 segundos</span></div>
    {error ? <div className="market-empty" role="alert"><p>Erro ao carregar ofertas.</p><button className="secondary-button" onClick={load}>Tentar novamente</button></div>
      : !data ? <div className="deal-grid" aria-label="Carregando promoções..."><div className="deal-skeleton"/><div className="deal-skeleton"/><div className="deal-skeleton"/><div className="deal-skeleton"/></div>
      : data.items.length ? <div className="deal-grid">{data.items.map(o => <PromotionCard key={o.id} offer={o} onChanged={load}/>)}</div>
      : <div className="market-empty"><Icon size={28}/><h3>{cfg.empty}</h3>
        <p>Novas ofertas aparecem aqui automaticamente.</p></div>}
    {data && <div className="deal-pagination"><p className="market-footnote">{data.total ? `${page*4+1}–${Math.min(page*4+4,data.total)} de ` : ''}{data.total} {cfg.total} com identidade associada ao catálogo. Cupons anunciados, sem validação de checkout.</p>
      {data.total > 4 && <div><button className="secondary-button" disabled={page===0} onClick={() => {setPage(p => p-1);setData(null);}}>Anteriores</button><button className="secondary-button" disabled={(page+1)*4>=data.total} onClick={() => {setPage(p => p+1);setData(null);}}>Próximas ofertas</button></div>}</div>}
  </section>;
}
