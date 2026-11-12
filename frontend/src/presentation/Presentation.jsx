import { useContext, useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { PresentationContext } from './context';
import { SECTIONS, QUALITY } from './data';
import snippets from './snippets.json';
import verification from './verification.json';
import Code from './highlight';
import { getSnippetGuide } from './snippetGuides';
import { ArchitectureSection, FlowSection } from './Architecture';
import { AiOverviewSection, AiAnalyzeSection, AiUpgradesSection, LiveAi } from './AiSections';
import { MatcherSection, TelegramSection, MercadoLivreSection, DatabaseSection, IntegrationStatus } from './DataSections';
import './presentation.css';

function CodeExplorer({ selectedId, onSelect }) {
  const selected = snippets.find(s => s.id === selectedId) || snippets[0];
  const { showCodeComments, setShowCodeComments } = useContext(PresentationContext);
  const codeId = useId();
  const guide = getSnippetGuide(selected);
  const currentTab = selected.tab;
  return (
    <div className="pz-explorer">
      <div className="pz-chips" aria-label="Áreas do código">
        {[...new Set(snippets.map(s => s.tab))].map(t => <button key={t} className={`pz-chip${currentTab === t ? ' on' : ''}`} onClick={() => { onSelect(snippets.find(s => s.tab === t).id); }}>{t === 'React' ? 'Frontend' : t}</button>)}
      </div>
      <div className="pz-chips" aria-label="Trechos disponíveis">
        {snippets.filter(s => s.tab === currentTab).map(s => <button key={s.id} className={`pz-chip${selected.id === s.id ? ' on' : ''}`} onClick={() => { onSelect(s.id); }}>{s.title}</button>)}
      </div>
      <h3>{selected.title}</h3>
      <div className="pz-code-intro">
        <p><strong>O que faz</strong>{guide?.summary || selected.explanation}</p>
        {guide && <><p><strong>Por que existe</strong>{guide.purpose}</p><p className="pz-code-example"><strong>Na prática</strong>{guide.example}</p></>}
      </div>
      <div className="pz-code-toolbar">
        <div><p className="pz-file">{selected.file}:{selected.start}–{selected.end}</p><span className="pz-code-caption">{showCodeComments ? 'Leitura guiada · explicação abaixo de cada linha' : 'Código original · numeração do arquivo'}</span></div>
        <button type="button" className={`pz-btn pz-comment-toggle${showCodeComments ? ' enabled' : ''}`} aria-pressed={showCodeComments} aria-controls={codeId} disabled={!guide} onClick={() => setShowCodeComments(value => !value)}>
          <span aria-hidden="true">{showCodeComments ? '◉' : '◎'}</span>{showCodeComments ? 'Ocultar comentários' : 'Exibir comentários'}
        </button>
      </div>
      <Code id={codeId} code={selected.code} start={selected.start} language={selected.language} annotations={showCodeComments ? guide?.lines : undefined} />
      <dl className="pz-code-contract"><div><dt>O que recebe</dt><dd>{selected.input}</dd></div><div><dt>O que entrega</dt><dd>{selected.output}</dd></div></dl>
    </div>
  );
}

function Intro() {
  const { goTo } = useContext(PresentationContext);
  return <div className="pz-intro"><div className="pz-eyebrow">ENGENHARIA DE SOFTWARE · DEMONSTRAÇÃO ACADÊMICA</div><h2>O seu próximo upgrade<br /><em>começa com informação.</em></h2><p className="pz-lead">Do anúncio à recomendação: explore como o PC2YOU conecta catálogo, ofertas reais e inteligência artificial para ajudar a escolher peças de computador.</p><div className="pz-toolbar"><button className="pz-btn primary" onClick={() => goTo('arquitetura')}>Explorar arquitetura →</button><button className="pz-btn" onClick={() => goTo('demo')}>Executar IA real</button></div><div className="pz-principles"><span>01 <b>Regras verificáveis</b></span><span>02 <b>Ofertas rastreáveis</b></span><span>03 <b>IA com limites</b></span></div><IntegrationStatus /></div>;
}

function SectionContent({ id, selectedCode, selectCode }) {
  const cards = items => <div className="pz-cards">{items.map(([title, text]) => <article className="pz-card" key={title}><h3>{title}</h3><p>{text}</p></article>)}</div>;
  switch (id) {
    case 'pc2you': return <Intro />;
    case 'problema': return <><p className="pz-lead">Escolher um computador exige juntar informações espalhadas — e distinguir uma boa oferta de uma peça incompatível.</p>{cards([['Compatibilidade', 'Socket, memória, potência e dimensões precisam fazer sentido juntos.'], ['Preço com contexto', 'Cupom, PIX, assinatura e validade mudam o valor real da oferta.'], ['Orientação compreensível', 'O usuário precisa entender o motivo de uma recomendação e suas incertezas.']])}</>;
    case 'solucao': return <><p className="pz-lead">Evidências comerciais, regras técnicas e explicações acessíveis.</p>{cards([['Catálogo técnico', 'IDs estáveis e especificações estruturadas.'], ['Ofertas reais', 'Pipeline Telegram, associação conservadora e histórico.'], ['IA orientada por regras', 'O backend fornece candidatos e valida o Gemini.']])}<ArchitectureSection /></>;
    case 'ux': return <><p className="pz-lead">As telas do produto continuam disponíveis, sem login.</p><div className="pz-cards">{[['/', 'Catálogo e promoções'], ['/analyze-pc', 'Analisar meu PC'], ['/build', 'Montar PC']].map(([url, title]) => <Link className="pz-card" to={url} key={url}><h3>{title} ↗</h3><code>{url}</code></Link>)}</div><FlowSection /></>;
    case 'arquitetura': return <ArchitectureSection />;
    case 'fluxo': return <FlowSection />;
    case 'ia': return <AiOverviewSection />;
    case 'ia-analise': return <AiAnalyzeSection />;
    case 'ia-upgrades': return <AiUpgradesSection />;
    case 'matcher': return <MatcherSection />;
    case 'telegram': return <TelegramSection />;
    case 'mercadolivre': return <MercadoLivreSection />;
    case 'mongodb': return <DatabaseSection />;
    case 'codigo': return <><p className="pz-lead">Trechos dos arquivos reais, ligados aos diagramas e às demonstrações.</p><CodeExplorer selectedId={selectedCode} onSelect={selectCode} /></>;
    case 'demo': return <><p className="pz-lead">Execute o fluxo real. Os estados são exibidos depois da resposta do backend; chamadas externas podem falhar ou retornar cache.</p><LiveAi /><IntegrationStatus /></>;
    case 'qualidade': return <><p className="pz-lead">Evidências da cópia: <code>docs/demo/FINAL_DEMO_REPORT.md</code>.</p><article className="pz-card"><h3>Execução verificada da cópia · {verification.date}</h3><p><b>{verification.passed} testes passaram · {verification.skipped} skipped</b></p><p>{Object.entries(verification.suites).map(([suite, count]) => `${suite}: ${count}`).join(" · ")}</p><p>Lint: {verification.lint} · Build: {verification.build}</p><p className="pz-note">Registro desta execução. Não é um monitor de testes em tempo real.</p></article><article className="pz-card"><h3>Referência histórica: projeto original</h3><p>{QUALITY.date} · docs/reverse-engineering/FINAL_REPORT.md. Estes números não representam uma execução atual da demo.</p><table><thead><tr><th>Suíte</th><th>Passaram</th><th>Observação</th></tr></thead><tbody>{QUALITY.suites.map(s => <tr key={s.name}><td>{s.name}</td><td>{s.count}</td><td>{s.note}</td></tr>)}</tbody></table><p>Total histórico: {QUALITY.total}. Resultado atual no relatório desta cópia.</p></article></>;
    case 'conclusao': return <><div className="pz-eyebrow">DO USUÁRIO AO CÓDIGO</div><h2>O sistema também<br /><em>explica como funciona.</em></h2><p className="pz-lead">Regras definem o que é possível. Dados comerciais mostram o que foi anunciado. A IA organiza e explica as opções. Cada etapa pode ser inspecionada.</p><FlowSection /><Link className="pz-btn primary" to="/">Voltar ao PC2YOU</Link></>;
    default: return null;
  }
}

export default function Presentation() {
  const [index, setIndex] = useState(() => Math.max(0, SECTIONS.findIndex(s => s.id === window.location.hash.slice(1))));
  const [selectedCode, selectCode] = useState(snippets[0].id);
  const [drawer, setDrawer] = useState(false);
  const [showCodeComments, setShowCodeComments] = useState(false);
  const [lastAi, setLastAi] = useState(null);
  const [fullscreenError, setFullscreenError] = useState('');
  const main = useRef(null), closeButton = useRef(null), restoreFocus = useRef(null);
  const section = SECTIONS[index];
  function goTo(id) { const next = SECTIONS.findIndex(s => s.id === id); if (next >= 0) setIndex(next); }
  function openCode(id) { selectCode(id); restoreFocus.current = document.activeElement; setDrawer(true); }
  function closeDrawer() { setDrawer(false); restoreFocus.current?.focus(); }
  useEffect(() => { const sync = () => { const i = SECTIONS.findIndex(s => s.id === window.location.hash.slice(1)); if (i >= 0) setIndex(i); }; window.addEventListener('hashchange', sync); return () => window.removeEventListener('hashchange', sync); }, []);
  useEffect(() => { window.history.replaceState(null, '', `#${section.id}`); main.current?.scrollTo(0, 0); }, [section.id]);
  useEffect(() => {
    function key(e) {
      if (e.key === 'Escape' && drawer) { setDrawer(false); restoreFocus.current?.focus(); return; }
      if (drawer || e.altKey || e.ctrlKey || e.metaKey || /INPUT|TEXTAREA|SELECT|BUTTON/.test(e.target.tagName) || e.target.isContentEditable) return;
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); setIndex(i => Math.max(0, Math.min(SECTIONS.length - 1, i + (e.key === 'ArrowRight' ? 1 : -1)))); }
    }
    window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key);
  }, [drawer]);
  useEffect(() => { if (drawer) closeButton.current?.focus(); }, [drawer]);
  async function fullscreen() { try { if (document.fullscreenElement) await document.exitFullscreen(); else await document.documentElement.requestFullscreen(); } catch { setFullscreenError('Tela cheia indisponível. Use F11.'); } }
  function trapFocus(e) {
    if (e.key !== 'Tab') return;
    const targets = [...e.currentTarget.querySelectorAll('button, a, [tabindex="0"]')];
    const first = targets[0], last = targets.at(-1);
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
    if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
  }
  return <PresentationContext.Provider value={{ openCode, lastAi, setLastAi, goTo, showCodeComments, setShowCodeComments }}><div className="pz-app">
    <aside className="pz-sidebar" inert={drawer ? '' : undefined}><Link className="pz-brand" to="/">▣ PC<span>2</span>YOU<small>POR DENTRO DO SISTEMA</small></Link><div className="pz-sidebar-label">ROTEIRO DA APRESENTAÇÃO</div><nav aria-label="Seções da apresentação">{SECTIONS.map((s, i) => <button key={s.id} className={i === index ? 'active' : ''} aria-current={i === index ? 'step' : undefined} onClick={() => setIndex(i)}><span>{s.number}</span>{s.title}</button>)}</nav><Link className="pz-home" to="/">↗ Abrir o catálogo</Link></aside>
    <div className="pz-workspace" inert={drawer ? '' : undefined}><header className="pz-topbar"><span><span className="pz-dot" /> MODO APRESENTAÇÃO</span><div><button className="pz-btn" onClick={() => openCode(selectedCode)}>&lt;/&gt; Código real</button><button className="pz-btn" onClick={fullscreen}>⛶ Tela cheia</button></div></header>{fullscreenError && <p role="status">{fullscreenError}</p>}
    <main ref={main} className="pz-main"><div className="pz-section-label">PC2YOU / {section.number} — {SECTIONS.length}</div><h1>{section.title}</h1><SectionContent key={section.id} id={section.id} selectedCode={selectedCode} selectCode={selectCode} /></main>
    <footer className="pz-footer"><button className="pz-btn" disabled={index === 0} onClick={() => setIndex(i => i - 1)}>← Anterior</button><div className="pz-progress" aria-label={`Seção ${index + 1} de ${SECTIONS.length}`}><span style={{ width: `${(index + 1) / SECTIONS.length * 100}%` }} /></div><span>{section.number} / {SECTIONS.length}</span><button className="pz-btn primary" disabled={index === SECTIONS.length - 1} onClick={() => setIndex(i => i + 1)}>Próximo →</button></footer></div>
    {drawer && <div className="pz-overlay" onClick={closeDrawer}><section className="pz-drawer" role="dialog" aria-modal="true" aria-label="Código real" onClick={e => e.stopPropagation()} onKeyDown={trapFocus}><div className="pz-toolbar"><h2>Código real</h2><button ref={closeButton} className="pz-btn" onClick={closeDrawer} aria-label="Fechar código">✕ Fechar</button></div><CodeExplorer key={selectedCode} selectedId={selectedCode} onSelect={selectCode} /></section></div>}
  </div></PresentationContext.Provider>;
}
