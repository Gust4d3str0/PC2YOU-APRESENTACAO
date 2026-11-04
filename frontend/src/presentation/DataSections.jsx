import { useContext, useEffect, useState } from 'react';
import { PresentationContext } from './context';
import { demo, errorText, proxiedImage } from './demoApi';
import { MATCHER_EXAMPLES, TELEGRAM_STEPS } from './data';
import Code from './highlight';

export function Json({ value }) { return <Code language="text" code={JSON.stringify(value, null, 2)} />; }

export function MatcherSection() {
  const [text, setText] = useState(MATCHER_EXAMPLES[0]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const { openCode } = useContext(PresentationContext);
  async function run(e) {
    e.preventDefault(); setBusy(true); setError(''); setResult(null);
    try { setResult(await demo.matcher(text)); } catch (err) { setError(errorText(err, 'Matcher indisponível. Verifique a API e o catálogo.')); }
    finally { setBusy(false); }
  }
  return <>
    <p className="pz-lead">Algoritmo determinístico: normalização → features → comparação → score → conflitos. <b>Não usa IA.</b></p>
    <div className="pz-chips">{MATCHER_EXAMPLES.map(t => <button className="pz-chip" key={t} onClick={() => setText(t)}>{t}</button>)}</div>
    <form onSubmit={run} className="pz-card"><label htmlFor="matcher-text">Texto do produto ou anúncio</label><textarea id="matcher-text" maxLength={300} required minLength={3} value={text} onChange={e => setText(e.target.value)} /><button className="pz-btn primary" disabled={busy}>{busy ? 'Comparando…' : 'Executar matcher'}</button> <button type="button" className="pz-btn" onClick={() => openCode('matcher-score')}>Ver algoritmo</button></form>
    <p className="pz-note">High ≥ 0,85 · Medium ≥ 0,65 · Low &lt; 0,65. Score é evidência heurística, não probabilidade estatística.</p>
    {error && <p role="alert" className="pz-callout warn">{error}</p>}
    {result && <><div className="pz-cards"><article className="pz-card"><h3>{result.result.matched ? result.result.component_name : 'Sem associação segura'}</h3><p>Score {result.result.score} · {result.result.level}</p><p>Conflitos: {result.result.conflicts?.join(', ') || 'nenhum'}</p></article><article className="pz-card"><h3>Normalização e features</h3><p>{result.normalized}</p><Json value={result.features} /></article></div><details><summary>Resultado completo e candidatos reais</summary><Json value={result} /></details></>}
  </>;
}

export function TelegramSection() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const { openCode } = useContext(PresentationContext);
  useEffect(() => {
    let active = true;
    const refresh = () => demo.telegramLatest(false).then(r => { if (active) { setData(r); setError(''); } }).catch(() => { if (active) setError('Sem resposta da API. Não foi possível consultar a última promoção.'); });
    refresh(); const timer = setInterval(refresh, 30000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  return <><p className="pz-lead">O Telegram fornece preço, cupom e link comercial. Atualização da consulta a cada 30 segundos.</p>
    <ol className="pz-flow">{TELEGRAM_STEPS.map(([title, detail, snippet]) => <li key={title}><b>{title}</b><span>{detail}</span><button className="pz-link" onClick={() => openCode(snippet)}>ver código</button></li>)}</ol>
    {error && <p className="pz-callout warn" role="alert">{error}</p>}
    {!data && !error && <p role="status">Consultando MongoDB…</p>}
    {data && <article className="pz-card"><h3>Última promoção real armazenada</h3><p className="pz-note">{data.label || 'Nenhuma promoção real disponível.'}</p>{data.available && <><p>Collector: <b>{data.collector}</b> · Recebida em {data.promotion.received_at} · {data.promotion.channel}</p><blockquote className="pz-quote">{data.promotion.text}</blockquote><Json value={{ extraido: data.promotion.extracted, match: data.promotion.match, status: data.promotion.status }} /></>}</article>}
  </>;
}

export function MercadoLivreSection() {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const { openCode } = useContext(PresentationContext);
  useEffect(() => { let active = true; demo.mlComponents().then(r => { if (active) { setItems(r.items); setSelected(r.items[0]?.component_id || ''); } }).catch(() => { if (active) setError('Não foi possível consultar o enriquecimento persistido.'); }); return () => { active = false; }; }, []);
  useEffect(() => { if (!selected) return; let active = true; demo.mlExample(selected).then(r => { if (active) { setData(r); setError(''); } }).catch(() => { if (active) setError('Componente indisponível.'); }); return () => { active = false; }; }, [selected]);
  const imageUrl = data?.image && proxiedImage(typeof data.image === 'string' ? data.image : data.image.url);
  return <><p className="pz-lead">Telegram = fonte comercial. Mercado Livre = enriquecimento técnico e visual.</p><div className="pz-cards"><article className="pz-card"><h3>Product API</h3><p>PRODUCT_ID → nome, marca, modelo, imagens e especificações → MongoDB.</p><button className="pz-btn" onClick={() => openCode('ml-match')}>Ver enriquecimento</button></article><article className="pz-card"><h3>Item / Price API</h3><p>Restrição registrada no projeto: 403 / PolicyAgent para itens de terceiros. Sem scraping ou contorno.</p><button className="pz-btn" onClick={() => openCode('ml-capability')}>Ver tratamento</button></article></div>
    {error && <p className="pz-callout warn" role="alert">{error}</p>}
    <label htmlFor="ml-component">Componente com enriquecimento persistido</label><select id="ml-component" value={selected} onChange={e => { setSelected(e.target.value); setData(null); }}>{!items.length && <option value="">Nenhum componente disponível</option>}{items.map(c => <option key={c.component_id} value={c.component_id}>{c.name}</option>)}</select>
    {data?.available && <div className="pz-card"><p className="pz-note">{data.source} · Consultado em {data.fetched_at || 'data não registrada'}</p>{imageUrl && <img className="pz-product-img" src={imageUrl} alt={data.component_name} />}<h3>{data.name || data.component_name}</h3><p>{data.product_id} · {data.brand} · {data.model} · {data.match_status}</p><Json value={data.specs} /></div>}
  </>;
}

export function DatabaseSection() {
  const [overview, setOverview] = useState(null);
  const [name, setName] = useState('components');
  const [page, setPage] = useState(1);
  const [json, setJson] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { let active = true; demo.database().then(r => { if (active) setOverview(r); }).catch(() => {}); return () => { active = false; }; }, []);
  useEffect(() => { let active = true; demo.collection(name, page).then(r => { if (active) { setData(r); setError(''); } }).catch(() => { if (active) setError('MongoDB Explorer indisponível. Verifique a API e o banco.'); }); return () => { active = false; }; }, [name, page]);
  return <><p className="pz-lead">Documentos reais, acesso somente leitura e coleções permitidas. Sem consulta livre ou operações de escrita.</p>
    <div className="pz-chips">{(overview?.collections || [{ name: 'components' }, { name: 'telegram_promotions' }, { name: 'product_price_history' }, { name: 'external_product_enrichment' }, { name: 'ml_integration_state' }, { name: 'telegram_service_status' }]).map(c => <button key={c.name} className={`pz-chip${name === c.name ? ' on' : ''}`} onClick={() => { setName(c.name); setPage(1); setData(null); }}>{c.name}{c.count != null ? ` (${c.count})` : ''}</button>)}</div>
    {error && <p className="pz-callout warn" role="alert">{error}</p>}
    <div className="pz-toolbar"><button className="pz-btn" onClick={() => setJson(!json)}>{json ? 'Ver tabela' : 'Ver JSON'}</button><button className="pz-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Anterior</button><span>Página {page} · {data?.total ?? '…'} documentos</span><button className="pz-btn" disabled={!data || page * 5 >= data.total || page >= 100} onClick={() => setPage(p => p + 1)}>Próxima</button></div>
    {data && (json ? <Json value={data.documents} /> : <div className="pz-table-wrap"><table><thead><tr>{data.fields.map(f => <th key={f}>{f}</th>)}</tr></thead><tbody>{data.table.map((row, i) => <tr key={i}>{data.fields.map(f => <td key={f}>{typeof row[f] === 'object' ? JSON.stringify(row[f]) : String(row[f] ?? '—')}</td>)}</tr>)}</tbody></table></div>)}
    <p className="pz-note">Paginação de 5 documentos; máximo de 10 por requisição e 100 páginas. Campos sensíveis removidos no backend.</p>
  </>;
}

export function IntegrationStatus() {
  const [status, setStatus] = useState(null);
  const [ai, setAi] = useState(null);
  const [checked, setChecked] = useState(false);
  const { lastAi } = useContext(PresentationContext);
  useEffect(() => {
    let active = true;
    async function refresh() {
      const [catalog, config] = await Promise.allSettled([demo.status(), demo.aiStatus()]);
      if (!active) return;
      setStatus(catalog.status === 'fulfilled' ? catalog.value : null);
      setAi(config.status === 'fulfilled' ? config.value : null); setChecked(true);
    }
    refresh(); const timer = setInterval(refresh, 30000); return () => { active = false; clearInterval(timer); };
  }, []);
  const rows = [['API Catálogo', status ? 'ONLINE' : checked ? 'SEM RESPOSTA' : 'NÃO VERIFICADO'], ['MongoDB', status?.mongodb || 'NÃO VERIFICADO'], ['API IA', ai ? 'ONLINE' : 'NÃO VERIFICADO'], ['Gemini', ai?.ai_enabled && ai?.key_configured ? 'CONFIGURADO' : ai ? 'DESATIVADO' : 'NÃO VERIFICADO'], ['Telegram Collector', status?.telegram || 'NÃO VERIFICADO'], ['ML Product API', status?.mercado_livre_product_api || 'NÃO VERIFICADO'], ['ML Item / Price', status?.mercado_livre_item_api || 'NÃO VERIFICADO']];
  return <div className="pz-integrations"><h3>Integrações <small>consulta a cada 30 s</small></h3><div className="pz-status-grid">{rows.map(([name, state]) => <div key={name}><span>{name}</span><b className={state === 'ONLINE' ? 'ok' : 'pz-muted'}>{state}</b></div>)}</div><p className="pz-note">Configuração de chave não comprova chamada ao Gemini. Última análise nesta sessão: {lastAi ? `${lastAi.ok ? 'sucesso' : 'falha'} em ${lastAi.at}${lastAi.cached ? ' (cache)' : ''}` : 'nenhuma'}. {status?.mercado_livre_product_detail}</p></div>;
}
