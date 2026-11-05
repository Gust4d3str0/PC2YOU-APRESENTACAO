import { useContext, useEffect, useRef, useState } from 'react';
import { PresentationContext } from './context';
import { PRESET } from './data';
import { demo, errorText } from './demoApi';
import Code from './highlight';
import savedAnalysis from './savedAnalysis.json';

const STAGE_HINT = ['Entrada validada', 'Peças identificadas', 'Compatibilidade calculada', 'Contexto preparado',
  'Gemini consultado', 'Resposta recebida', 'Resposta validada'];

function Flow({ steps, accent }) {
  return (
    <ol className={`pz-flow ${accent || ''}`}>
      {steps.map(([title, detail, snippet]) => <FlowStep key={title} title={title} detail={detail} snippet={snippet} />)}
    </ol>
  );
}

function FlowStep({ title, detail, snippet }) {
  const { openCode } = useContext(PresentationContext);
  return (
    <li>
      <b>{title}</b>
      <span>{detail}</span>
      {snippet && <button type="button" className="pz-link" onClick={() => openCode(snippet)}>ver código</button>}
    </li>
  );
}

export function AiOverviewSection() {
  return (
    <>
      <p className="pz-lead">Decisão de arquitetura: <b>a IA não controla a lógica crítica.</b> O backend define compatibilidade, preços, IDs e candidatos;
        o Gemini analisa, prioriza e explica <i>dentro</i> das opções fornecidas.</p>
      <div className="pz-cards">
        <div className="pz-card"><h4>Backend decide</h4><p>Regras de compatibilidade, preços reais, IDs e a lista de candidatos permitidos.</p></div>
        <div className="pz-card"><h4>Gemini explica</h4><p>Prioriza tipos de upgrade e escolhe <code>candidate_id</code> somente entre os candidatos recebidos, em JSON Schema.</p></div>
        <div className="pz-card"><h4>Backend valida</h4><p>Pydantic, tipo/ID/orçamento e uma barreira que rejeita números, preços e modelos que o modelo inventar.</p></div>
      </div>
      <div className="pz-cards">
        <div className="pz-card"><h4>POST /ai/analyze-pc</h4><p>Diagnóstico do PC atual e prioridades de upgrade. Identificação determinística por nome normalizado.</p></div>
        <div className="pz-card"><h4>POST /ai/recommend-upgrades</h4><p>Substituições concretas com ofertas do Telegram, histórico e compatibilidade combinada. Usa o Product Matcher.</p></div>
      </div>
      <p className="pz-note">Padrões do código: temperatura 0,2, structured output (JSON Schema), timeout 45 s, cache 300 s, 10 chamadas/min. Modelo e limites podem ser configurados; a resposta real informa o modelo utilizado.</p>
    </>
  );
}

export function AiAnalyzeSection() {
  return (
    <>
      <div className="pz-callout">A identificação em <code>ai_context.enrich</code> é <b>determinística, sem IA</b>: normaliza nomes com utilitários do Product Matcher e aceita só <b>uma</b> identidade na categoria. Diferenças de acentos, pontuação, espaços e posição da marca são toleradas; variantes e ambiguidades permanecem não verificadas.</div>
      <Flow steps={[
        ['Usuário', 'preenche o formulário em AnalyzePC.jsx', 'react-analyze'],
        ['Pydantic / sanitização', 'AnalyzePCRequest (extra=forbid) + technical_text bloqueia URLs, e-mails, chaves e instruções', 'api-analyze-route'],
        ['ai_context.enrich', 'cada peça → catálogo (1 identidade normalizada) ou “dado do usuário”', 'ai-enrich'],
        ['Compatibilidade por regras', 'socket, memória, slots, potência, gabinete; regra sem dado = não verificada', 'ai-context'],
        ['Candidatos', 'só se todas as regras foram verificadas; até 3 por categoria dentro do orçamento', 'ai-context'],
        ['Prompt estruturado', 'system prompt + trusted_context + user_context (dado, nunca instrução)', 'ai-prompt'],
        ['Gemini', 'structured output com candidate_id restrito por enum', 'ai-gemini'],
        ['Validação', 'Pydantic + semântica (tipo, ID, orçamento) + prosa sem números/modelos', 'ai-validate'],
        ['Resposta', 'PCAnalysisResult.jsx mostra o veredito de compatibilidade calculado pelo backend', 'ai-prose'],
      ]} />
    </>
  );
}

export function AiUpgradesSection() {
  return (
    <>
      <p className="pz-lead">A IA <b>não inventa livremente o produto</b>: os candidatos são fornecidos pelo backend e o schema só aceita esses IDs.</p>
      <Flow accent="violet" steps={[
        ['Build atual', 'mesma identificação e compatibilidade da análise', 'ai-context'],
        ['Catálogo', 'gpu, cpu, ram/kit-ram e psu; melhoria potencial por benchmark/capacidade', 'ai-context'],
        ['Promoções Telegram', 'MongoDB, últimas 72 h, somente leitura', 'tg-process'],
        ['Product Matcher', 'só ofertas com match High e sem conflito entram', 'matcher-select'],
        ['Histórico de preço', '≥ 3 dias de observações verificadas → média e mínimo', 'mongo-best'],
        ['Compatibilidade', 'troca a peça e reexecuta as regras; combinação final também', 'ai-context'],
        ['Candidatos permitidos', 'até 5 por categoria, com preço verificado e evidência da oportunidade', 'ai-cache'],
        ['Gemini', 'escolhe entre candidatos; sem candidatos a chamada é evitada', 'ai-gemini'],
        ['Validação', 'tipo, orçamento, combinação, promoção elegível, prosa sem loja/cupom', 'ai-validate'],
      ]} />
    </>
  );
}

// ---- live demo ---------------------------------------------------------------------------------------
export function LiveAi() {
  const { setLastAi, openCode } = useContext(PresentationContext);
  const [configuration, setConfiguration] = useState(PRESET.payload);
  const [submitted, setSubmitted] = useState(PRESET.payload);
  const [showSaved, setShowSaved] = useState(false);
  const [state, setState] = useState('idle'); // idle | running | done | error
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [context, setContext] = useState(null);
  const [view, setView] = useState('summary');
  const request = useRef(null);
  useEffect(() => () => request.current?.abort(), []);

  const run = async () => {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setShowSaved(false);
    setSubmitted(configuration);
    setState('running'); setError(''); setResult(null); setContext(null); setView('summary');
    try {
      const data = await demo.analyze(configuration, controller.signal);
      setResult(data); setState('done');
      setLastAi({ ok: true, at: new Date().toISOString(), cached: data.metadata.cached, model: data.metadata.model });
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(errorText(err, 'Não foi possível concluir a análise (sem resposta da API de IA).'));
        setState('error');
        setLastAi({ ok: false, at: new Date().toISOString() });
      }
    } finally {
      request.current = null;
    }
  };

  const showContext = async () => {
    setView('context');
    if (!context) {
      try { setContext(await demo.aiContext(submitted)); } catch (err) { setContext({ error: errorText(err, 'Contexto indisponível.') }); }
    }
  };

  const analysis = result?.analysis;
  return (
    <div className="pz-live">
      <div className="pz-cards">
        <label>CPU<input maxLength={120} disabled={state === 'running'} value={configuration.components.cpu} onChange={e => setConfiguration(c => ({...c, components: {...c.components, cpu: e.target.value}}))} /></label>
        <label>GPU<input maxLength={120} disabled={state === 'running'} value={configuration.components.gpu} onChange={e => setConfiguration(c => ({...c, components: {...c.components, gpu: e.target.value}}))} /></label>
        <label>Orçamento de upgrade (R$)<input type="number" min="0" max="1000000" disabled={state === 'running'} value={configuration.upgrade_budget ?? ''} onChange={e => setConfiguration(c => ({...c, upgrade_budget: e.target.value === '' ? null : Number(e.target.value)}))} /></label>
      </div>
      <div className="pz-live-head">
        <div><b>Base do formulário:</b> {PRESET.label}</div>
        <button type="button" className="pz-btn primary" disabled={state === 'running'} onClick={run}>
          {state === 'running' ? 'Executando…' : '▶ Executar análise real'}
        </button>
      </div>
      <details className="pz-details"><summary>Ver entrada enviada</summary><Code language="text" code={JSON.stringify(configuration, null, 2)} /></details>

      {state === 'running' && <p className="pz-status" role="status">Consultando a API de IA… o backend executa validação, catálogo, compatibilidade e Gemini em uma única requisição (até ~45 s).</p>}
      {state === 'error' && (
        <div className="pz-callout warn" role="alert">
          <b>Falha ao vivo:</b> {error}
          <button className="pz-btn" onClick={() => setShowSaved(true)}>Mostrar resposta de demonstração salva</button>
        </div>
      )}
      {showSaved && <div className="pz-callout saved"><b>Resposta de demonstração salva em {savedAnalysis.recorded_at}</b><p>Obtida com o preset original. Não é uma resposta ao vivo e não representa alterações feitas no formulário.</p><AnalysisBody analysis={savedAnalysis.response.analysis} compatibility={savedAnalysis.response.compatibility} /></div>}
      {state === 'done' && result && (
        <div className="pz-result">
          <ul className="pz-checks">
            {STAGE_HINT.map((label, index) => {
              const detail = [
                'HTTP 200 (Pydantic aceitou)', `${result.metadata.catalog_matches} peça(s) do catálogo`,
                `status: ${result.compatibility.status}`, `${result.recommended_candidates.length} candidato(s)`,
                result.metadata.cached ? 'resposta em cache (nenhuma chamada nova)' : `${result.metadata.provider} · ${result.metadata.model}`,
                'JSON recebido', `prompt ${result.metadata.prompt_version}`,
              ][index];
              return <li key={label}><span className="ok">✓</span> {index === 4 && result.metadata.cached ? 'Resposta recuperada do cache' : label} <small>{detail}</small></li>;
            })}
          </ul>
          <div className="pz-chips">
            {[['summary', 'Resultado'], ['json', 'Resultado estruturado (JSON)']].map(([id, label]) => (
              <button key={id} type="button" className={`pz-chip${view === id ? ' on' : ''}`} onClick={() => setView(id)}>{label}</button>
            ))}
            <button type="button" className={`pz-chip${view === 'context' ? ' on' : ''}`} onClick={showContext}>Reconstruir contexto atual (sanitizado)</button>
            <button type="button" className="pz-chip" onClick={() => openCode('ai-context')}>Ver código</button>
          </div>
          {view === 'summary' && <AnalysisBody analysis={analysis} compatibility={result.compatibility} />}
          {view === 'json' && <Code language="text" code={JSON.stringify(result, null, 2)} />}
          {view === 'context' && (context ? <Code language="text" code={JSON.stringify(context, null, 2)} /> : <p className="pz-muted">Carregando contexto…</p>)}


        </div>
      )}
    </div>
  );
}

function AnalysisBody({ analysis, compatibility }) {
  const verdict = { compatible: 'Compatível (verificado pelas regras do sistema)', partial: 'Parcial: faltam dados para algumas regras', incompatible: 'Incompatibilidade encontrada' }[compatibility.status];
  return (
    <div className="pz-analysis">
      <p className={`pz-verdict ${compatibility.status}`}>Compatibilidade (backend): {verdict}</p>
      <h4>Resumo</h4><p>{analysis.summary}</p>
      <h4>Limitante provável</h4><p>{analysis.primary_limit.component} · confiança {analysis.primary_limit.confidence} — {analysis.primary_limit.explanation}</p>
      <h4>Prioridades</h4>
      <ul>{analysis.upgrade_priorities.map((p) => <li key={p.priority}><b>{p.priority}. {p.component_type}</b> — {p.reason}</li>)}</ul>
      <h4>Recomendação final</h4><p>{analysis.final_recommendation}</p>
    </div>
  );
}
