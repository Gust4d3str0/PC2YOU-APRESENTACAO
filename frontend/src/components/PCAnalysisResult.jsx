import { formatCurrency } from '../api';

const labels = { cpu: 'Processador', gpu: 'Placa de vídeo', motherboard: 'Placa-mãe', ram: 'Memória RAM',
  storage: 'Armazenamento', psu: 'Fonte', case: 'Gabinete', unknown: 'Dados insuficientes' };
const confidence = { low: 'Baixa', medium: 'Média', high: 'Alta' };
const balance = { balanced: 'Bom equilíbrio', attention: 'Pontos de atenção', insufficient_data: 'Dados insuficientes' };
const verdict = { compatible: 'Sem incompatibilidades nas regras verificadas', incompatible: 'Incompatibilidade detectada', partial: 'Verificação parcial' };
const budgetLabels = { within_budget: 'Dentro do orçamento informado', no_budget: 'Sem orçamento definido',
  price_unavailable: 'Preço não disponível', save_budget: 'Considere reservar o orçamento' };
const ruleLabels = { cpu_socket: 'Socket do processador', ram_type: 'Tipo de memória', ram_slots: 'Slots de RAM',
  ram_capacity: 'Capacidade de RAM', gpu_power: 'Potência da fonte', board_case: 'Formato do gabinete', gpu_case: 'Espaço para a GPU' };

function TextList({ title, items }) {
  return <section className="summary-panel analysis-card"><h3>{title}</h3>{items.length
    ? <ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul> : <p>Nenhum ponto adicional informado.</p>}</section>;
}

export default function PCAnalysisResult({ result }) {
  const a = result.analysis;
  return <section className="analysis-result" aria-label="Análise do seu PC" aria-live="polite">
    <div className="section-title"><div><span className="eyebrow">Análise do seu PC</span><h2>Seu cenário, com mais clareza</h2></div>
      {result.metadata.cached && <span className="compat-note">Análise recente reutilizada</span>}</div>
    <div className="summary-panel analysis-overview"><span className="eyebrow">Visão geral</span>
      <h3>{balance[a.balance.status]}</h3><p>{a.summary}</p><p>{a.balance.explanation}</p>
      <div className="analysis-highlight"><strong>Principal limitante provável: {labels[a.primary_limit.component]}</strong>
        <span>Confiança: {confidence[a.primary_limit.confidence]}</span><p>{a.primary_limit.explanation}</p></div>
      <p>Orçamento informado: <strong>{result.upgrade_budget === null ? 'Não informado' : formatCurrency(result.upgrade_budget)}</strong></p>
    </div>
    <div className="analysis-grid"><TextList title="Pontos fortes" items={a.strengths} /><TextList title="O que pode melhorar" items={a.weaknesses} /></div>
    <section className="summary-panel analysis-card"><h3>Prioridade de upgrade</h3>
      {a.upgrade_priorities.length === 0 && <p>Confirme os dados antes de decidir uma troca.</p>}
      <ol className="analysis-priorities">{a.upgrade_priorities.map((p) => {
        const candidate = result.recommended_candidates.find((item) => item.component_id === p.candidate_id);
        return <li key={p.component_type}><h4>{labels[p.component_type]}</h4><p>{p.reason}</p>
          <p><strong>Benefício esperado:</strong> {p.expected_benefit}</p><small>{budgetLabels[p.budget_relevance]}</small>
          {candidate && <p className="analysis-candidate">Opção do catálogo: <strong>{candidate.name}</strong> · {candidate.price === null
            ? 'Preço não disponível' : formatCurrency(candidate.price)}<br /><small>Confirme as especificações antes da compra.</small></p>}</li>;
      })}</ol>
    </section>
    <section className={`summary-panel analysis-card analysis-compatibility ${result.compatibility.status}`}>
      <span className="eyebrow">Verificação do backend</span><h3>Compatibilidade: {verdict[result.compatibility.status]}</h3>
      {result.compatibility_notes.length > 0 && <ul>{result.compatibility_notes.map((note, i) => <li key={i}>{note}</li>)}</ul>}
      <p>Regras verificadas: {result.compatibility.checked_rules.map((rule) => ruleLabels[rule]).join(', ') || 'Nenhuma; faltam dados confiáveis.'}</p>
      {result.compatibility.unchecked_rules.length > 0 && <p>Não verificadas: {result.compatibility.unchecked_rules.map((rule) => ruleLabels[rule]).join(', ')}.</p>}
      <details><summary>Identificação dos componentes ({result.metadata.catalog_matches} no catálogo)</summary>
        <ul>{result.components.map((c, i) => <li key={i}>{labels[c.category]}: {c.name} — {c.source === 'catalog' ? 'Catálogo' : 'Informado por você; especificações não verificadas'}</li>)}</ul>
      </details>
    </section>
    <div className="analysis-grid"><TextList title="Alertas" items={a.warnings} /><TextList title="Informações a confirmar" items={a.missing_information} /></div>
    <section className="summary-panel analysis-card analysis-final"><h3>Recomendação final</h3><p>{a.final_recommendation}</p></section>
  </section>;
}
