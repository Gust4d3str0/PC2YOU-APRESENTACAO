import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DEMO } from '../demo';
import { Check, Info, Minus, Plus, RotateCcw } from 'lucide-react';
import Header from '../components/Header';
import { budgetsApi, formatCurrency, getBestPrice, getComponentImage, getStoredUser } from '../api';
import LoadingState from '../components/LoadingState';
import { formatSpecValue, getCategoryLabel, getSpecLabel } from '../utils/formatters';

const steps = [
  { id: 'cpu', label: 'Processador' },
  { id: 'cooler', label: 'Cooler' },
  { id: 'motherboard', label: 'Placa-mãe' },
  { id: 'ram', label: 'Memória RAM' },
  { id: 'storage', label: 'Armazenamento' },
  { id: 'gpu', label: 'Placa de vídeo' },
  { id: 'psu', label: 'Fonte' },
  { id: 'case', label: 'Gabinete' },
];

const formatApiError = (detail, fallback) => {
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (detail.message) return detail.message;
  if (detail.errors?.length) return detail.errors.join(' ');
  return fallback;
};

export default function Build() {
  const [selected, setSelected] = useState({});
  const [options, setOptions] = useState([]);
  const [selectedDetails, setSelectedDetails] = useState({});
  const [nextCategory, setNextCategory] = useState('cpu');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [ramQuantity, setRamQuantity] = useState(1);
  const navigate = useNavigate();
  const user = getStoredUser();

  const currentStep = useMemo(() => (
    steps.find((step) => step.id === nextCategory)
  ), [nextCategory]);

  // Max RAM slots from selected motherboard, default 4
  const maxRamSlots = useMemo(() => {
    const mb = selectedDetails.motherboard;
    return mb?.technical_specs?.memory_slots || 4;
  }, [selectedDetails.motherboard]);

  const selectedCount = Object.keys(selected).length;
  const done = selectedCount === steps.length;

  const partialTotal = Object.values(selectedDetails).reduce((sum, component) => {
    const price = getBestPrice(component);
    const isRam = component.category === 'ram' || component.category === 'kit-ram';
    return sum + Number(price?.price || 0) * (isRam ? ramQuantity : 1);
  }, 0);

  useEffect(() => {
    const loadOptions = async () => {
      setLoading(true);
      setError('');
      try {
        const res = await budgetsApi.post('/build/next-options', {
          selected_components: selected,
        });
        setOptions(res.data.options || []);
        setNextCategory(res.data.next_category);
      } catch (err) {
        setError(formatApiError(err.response?.data?.detail, 'Erro ao buscar opções compatíveis'));
      } finally {
        setLoading(false);
      }
    };
    loadOptions();
  }, [selected]);

  // Reset RAM quantity when motherboard changes
  useEffect(() => {
    setRamQuantity(1);
  }, [selectedDetails.motherboard]);

  const choose = (component) => {
    const stepKey = component.category === 'kit-ram' ? 'ram' : component.category;
    setSelected((current) => ({ ...current, [stepKey]: component.id }));
    setSelectedDetails((current) => ({ ...current, [stepKey]: component }));
  };

  const resetFrom = (category) => {
    const index = steps.findIndex((step) => step.id === category);
    const next = {};
    steps.slice(0, index).forEach((step) => {
      if (selected[step.id]) next[step.id] = selected[step.id];
    });
    setSelected(next);
    setSelectedDetails((current) => {
      const details = {};
      steps.slice(0, index).forEach((step) => {
        if (current[step.id]) details[step.id] = current[step.id];
      });
      return details;
    });
    // Reset RAM quantity if resetting from/before RAM step
    if (index <= steps.findIndex((s) => s.id === 'ram')) {
      setRamQuantity(1);
    }
  };

  const finalize = async () => {
    if (DEMO) {
      // Saving a budget needs login (full project). The wizard stops before persistence in the presentation build.
      setError('Salvar orçamento está desativado na versão de demonstração (exige login no projeto completo).');
      return;
    }
    if (!user) {
      navigate('/login');
      return;
    }
    try {
      setError('');
      const componentIds = steps.map((step) => selected[step.id]);
      const quantities = {};
      if (selected.ram && ramQuantity > 1) {
        quantities[selected.ram] = ramQuantity;
      }
      const res = await budgetsApi.post('/build/finalize', {
        user_id: user.id,
        components: componentIds,
        quantities,
        name: 'Orçamento principal PC2YOU',
      });
      navigate(`/budget/${res.data.budget_id}`);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail, 'Erro ao gerar orçamento final'));
    }
  };

  const isRamStep = nextCategory === 'ram';

  return (
    <>
      <Header />
      <main className="main-container build-page">
        <section className="page-heading">
          <div>
            <span className="eyebrow">Monte seu PC</span>
            <h1>Escolha uma peça por etapa e veja somente opções compatíveis.</h1>
          </div>
          <button
            className="secondary-button"
            onClick={() => {
              setSelected({});
              setSelectedDetails({});
              setRamQuantity(1);
            }}
            type="button"
          >
            <RotateCcw size={17} />
            Reiniciar
          </button>
        </section>

        <div className="stepper">
          {steps.map((step) => (
            <button
              type="button"
              key={step.id}
              className={selected[step.id] ? 'is-done' : step.id === nextCategory ? 'is-current' : ''}
              onClick={() => selected[step.id] && resetFrom(step.id)}
            >
              {selected[step.id] ? <Check size={16} /> : <span />}
              {step.label}
            </button>
          ))}
        </div>

        {error && <div className="error-msg">{error}</div>}

        <div className="build-layout">
          <section className="build-options">
            {done ? (
              <div className="summary-panel finish-panel">
                <span className="eyebrow">Pronto para finalizar</span>
                <h2>Build validada pela PC2YOU</h2>
                <p>As oito etapas foram preenchidas. Gere o relatório final com preço total, links e desempenho.</p>
                <button className="btn-primary" onClick={finalize} type="button" disabled={DEMO}>
                  {DEMO ? "Montagem concluída (sem salvar)" : "Gerar orçamento final"}
                </button>
              </div>
            ) : (
              <>
                <div className="section-title">
                  <div>
                    <span className="eyebrow">Etapa {selectedCount + 1} de {steps.length}</span>
                    <h2>{currentStep?.label || 'Próxima etapa'}</h2>
                  </div>
                  <span className="compat-note"><Info size={16} /> Opções filtradas por compatibilidade</span>
                </div>

                {/* RAM quantity selector */}
                {isRamStep && !loading && options.length > 0 && (
                  <div className="ram-qty-panel">
                    <span>Quantidade de módulos de RAM:</span>
                    <div className="qty-controls">
                      <button
                        type="button"
                        className="qty-btn"
                        onClick={() => setRamQuantity((q) => Math.max(1, q - 1))}
                        disabled={ramQuantity <= 1}
                        aria-label="Diminuir quantidade"
                      >
                        <Minus size={14} />
                      </button>
                      <span className="qty-value">{ramQuantity}</span>
                      <button
                        type="button"
                        className="qty-btn"
                        onClick={() => setRamQuantity((q) => Math.min(maxRamSlots, q + 1))}
                        disabled={ramQuantity >= maxRamSlots}
                        aria-label="Aumentar quantidade"
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                    <small className="qty-hint">
                      Máximo: {maxRamSlots} slots (placa-mãe selecionada)
                    </small>
                  </div>
                )}

                {loading ? (
                  <LoadingState label="Calculando opções compatíveis..." cards={4} />
                ) : options.length === 0 ? (
                  <div className="state-panel">
                    <h2>Nenhuma opção compatível</h2>
                    <p>Tente voltar uma etapa ou reiniciar a montagem para testar outra combinação.</p>
                  </div>
                ) : (
                  <div className="option-list">
                    {options.map((component) => {
                      const bestPrice = component.best_price || getBestPrice(component);
                      const specs = Object.entries(component.technical_specs || {}).slice(0, 3);
                      const imgSrc = getComponentImage(component);
                      const unitPrice = bestPrice ? Number(bestPrice.price) : 0;
                      const totalPrice = isRamStep ? unitPrice * ramQuantity : unitPrice;

                      return (
                        <button
                          type="button"
                          className="option-row"
                          key={component.id}
                          onClick={() => choose(component)}
                        >
                          <img
                            src={imgSrc}
                            alt={component.name}
                            onError={(e) => { e.target.onerror = null; e.target.src = '/components/default-component.png'; }}
                          />
                          <span>
                            <strong>{component.name}</strong>
                            <small>{component.brand} · {getCategoryLabel(component.category)}</small>
                            <small className="option-specs">
                              {specs.map(([key, value]) => `${getSpecLabel(key)}: ${formatSpecValue(key, value)}`).join(' · ')}
                            </small>
                          </span>
                          <span className="option-price-col">
                            <em>{bestPrice ? formatCurrency(totalPrice) : 'Sem preço'}</em>
                            {isRamStep && ramQuantity > 1 && (
                              <small className="option-unit-price">
                                {ramQuantity}× {formatCurrency(unitPrice)}
                              </small>
                            )}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </section>

          <aside className="build-summary">
            <span className="eyebrow">Resumo da build</span>
            <h2>Total parcial</h2>
            <strong className="summary-total">{formatCurrency(partialTotal)}</strong>
            <div className="summary-parts">
              {steps.map((step) => {
                const component = selectedDetails[step.id];
                const isRam = step.id === 'ram';
                return (
                  <div className="summary-part" key={step.id}>
                    <span>{step.label}</span>
                    <strong>
                      {component
                        ? (isRam && ramQuantity > 1 ? `${ramQuantity}× ` : '') + component.name
                        : 'Aguardando seleção'}
                    </strong>
                  </div>
                );
              })}
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}
