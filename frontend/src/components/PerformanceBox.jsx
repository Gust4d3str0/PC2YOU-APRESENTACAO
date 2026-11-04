import { Activity } from 'lucide-react';

export default function PerformanceBox({ performance }) {
  if (!performance) return null;

  const score = performance.estimated_score ?? 0;
  const tier = performance.tier || (score >= 88 ? 'Alto desempenho' : score >= 65 ? 'Intermediário' : 'Básico');
  const summary = performance.summary || performance.gaming || 'Estimativa de desempenho gerada a partir das peças selecionadas.';
  const details = [
    ['Jogos', performance.gaming],
    ['Trabalho', performance.workstation],
    ['IA', performance.ai],
  ].filter(([, value]) => value);

  return (
    <section className="summary-panel performance-panel">
      <div className="section-title">
        <Activity size={20} />
        <h2>Desempenho estimado</h2>
      </div>
      <div className="score-line">
        <strong>{score}</strong>
        <span>/100</span>
      </div>
      <span className="tier-pill">{tier}</span>
      <p className="performance-summary">{summary}</p>
      <div className="performance-metrics">
        {details.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <p>{value}</p>
          </div>
        ))}
      </div>
      {performance.recommendation && (
        <p className="recommendation-note">{performance.recommendation}</p>
      )}
    </section>
  );
}
