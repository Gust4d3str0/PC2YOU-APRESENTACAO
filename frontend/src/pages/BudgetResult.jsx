import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import Header from '../components/Header';
import BudgetSummary from '../components/BudgetSummary';
import { budgetsApi } from '../api';

export default function BudgetResult() {
  const { id } = useParams();
  const [budget, setBudget] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const res = await budgetsApi.get(`/budgets/${id}`);
      setBudget(res.data);
      setLoading(false);
    };
    load().catch(() => setLoading(false));
  }, [id]);

  return (
    <>
      <Header />
      <main className="main-container">
        <Link to="/build" className="back-link">
          <ArrowLeft size={17} />
          Voltar ao montador
        </Link>

        <section className="page-heading">
          <div>
            <span className="eyebrow">Resultado</span>
            <h1>Orçamento final PC2YOU</h1>
          </div>
          <p>Relatório com preço total, perfil da build, links por peça e estimativa de desempenho.</p>
        </section>

        {loading ? (
          <p className="status-text">Carregando orçamento...</p>
        ) : budget ? (
          <BudgetSummary budget={budget} />
        ) : (
          <p className="status-text">Orçamento não encontrado.</p>
        )}
      </main>
    </>
  );
}
