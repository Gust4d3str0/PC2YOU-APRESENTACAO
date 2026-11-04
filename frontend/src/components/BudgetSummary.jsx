import { ExternalLink } from 'lucide-react';
import { formatCurrency } from '../api';
import { getCategoryBadge, getCategoryLabel } from '../utils/formatters';
import PerformanceBox from './PerformanceBox';

function buildProfile(budget) {
  const score = budget.performance?.estimated_score || 0;
  const names = budget.items.map((item) => item.name.toLowerCase()).join(' ');

  if (score >= 95 || names.includes('rtx 5090')) {
    return {
      label: 'Entusiasta / 4K / Workstation',
      text: 'Indicada para jogos 4K, edição de vídeo, IA local e multitarefa pesada.',
    };
  }

  if (score >= 88) {
    return {
      label: 'Alto desempenho / 1440p / Produtividade',
      text: 'Indicada para jogos modernos, programação pesada, edição e uso profissional.',
    };
  }

  if (score >= 78) {
    return {
      label: 'Avançada / 1080p-1440p / Estudos',
      text: 'Indicada para jogos, estudos, desenvolvimento e produtividade diária.',
    };
  }

  return {
    label: 'Essencial / Uso diário',
    text: 'Indicada para navegação, estudos, tarefas leves e jogos com ajustes.',
  };
}

export default function BudgetSummary({ budget }) {
  if (!budget) return null;
  const itemCount = budget.items.length;
  const topStores = [...new Set(budget.items.map((item) => item.store))].slice(0, 3).join(' · ');
  const profile = buildProfile(budget);
  const highlights = budget.performance?.highlights || [];

  return (
    <div className="budget-report">
      <section className="report-hero">
        <div>
          <span className="eyebrow">Relatório PC2YOU</span>
          <h2>{profile.label}</h2>
          <p>{profile.text}</p>
        </div>
        <div className="report-total">
          <span>Total estimado</span>
          <strong>{formatCurrency(budget.total_price)}</strong>
          <small>#{budget.budget_id}</small>
        </div>
      </section>

      <section className="report-kpis">
        <div>
          <span>Total estimado</span>
          <strong>{formatCurrency(budget.total_price)}</strong>
        </div>
        <div>
          <span>Peças</span>
          <strong>{itemCount}</strong>
        </div>
        <div>
          <span>Score</span>
          <strong>{budget.performance?.estimated_score || 0}/100</strong>
        </div>
        <div>
          <span>Lojas recomendadas</span>
          <strong>{topStores || 'Sem loja'}</strong>
        </div>
      </section>

      <div className="budget-layout">
        <section className="summary-panel">
          <div className="section-title">
            <h2>Peças selecionadas</h2>
            <span>{itemCount} itens</span>
          </div>

          <div className="budget-items">
            {budget.items.map((item) => {
              const qty = item.quantity || 1;
              const unitPrice = qty > 1 ? item.best_price / qty : item.best_price;
              return (
                <article className="budget-item" key={item.component_id}>
                  <div className="budget-item-main">
                    <span className="category-badge">{getCategoryBadge(item.category)}</span>
                    <div>
                      <span className="muted">{getCategoryLabel(item.category)}</span>
                      <strong>{qty > 1 ? `${qty}× ` : ''}{item.name}</strong>
                      <small>
                        Loja: {item.store}
                        {qty > 1 && ` · ${qty}× ${formatCurrency(unitPrice)}`}
                      </small>
                    </div>
                  </div>
                  <div className="budget-price">
                    <span>{formatCurrency(item.best_price)}</span>
                    <a href={item.url} target="_blank" rel="noreferrer" title="Abrir loja">
                      Abrir loja
                      <ExternalLink size={16} />
                    </a>
                  </div>
                </article>
              );
            })}
          </div>

          <div className="total-line">
            <span>Total</span>
            <strong>{formatCurrency(budget.total_price)}</strong>
          </div>
        </section>

        <aside className="budget-side">
          <PerformanceBox performance={budget.performance} />

          {highlights.length > 0 && (
            <section className="summary-panel highlights-panel">
              <h2>Destaques técnicos</h2>
              <ul>
                {highlights.map((highlight) => (
                  <li key={highlight}>{highlight}</li>
                ))}
              </ul>
            </section>
          )}

          <p className="academic-note">
            Preços anunciados em fontes reais (como o Telegram), sujeitos a condições e mudanças. Confirme na loja antes da compra.
          </p>
        </aside>
      </div>
    </div>
  );
}
