import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { DEMO } from '../demo';
import { ArrowLeft, Gauge, RefreshCw, ShoppingBag, TrendingDown } from 'lucide-react';
import Header from '../components/Header';
import OfferComparison from '../components/OfferComparison';
import HardwareImage from '../components/HardwareImage';
import './Commerce.css';
import FavoriteButton from '../components/FavoriteButton';
import PriceTable from '../components/PriceTable';
import PriceChart from '../components/PriceChart';
import LoadingState from '../components/LoadingState';
import ExternalSpecs from '../components/ExternalSpecs';
import EmptyState from '../components/EmptyState';
import {
  catalogApi,
  fetchPriceHistory,
  fetchPriceSummary,
  formatCurrency,
  getPriceSummary,
  getStoredUser,
  refreshRealPrices,
  usersApi,
} from '../api';
import {
  formatSpecValue,
  generateTechnicalSummary,
  getCategoryBadge,
  getCategoryLabel,
  getSpecLabel,
} from '../utils/formatters';

function KeyValueList({ data }) {
  const entries = Object.entries(data || {});
  if (!entries.length) {
    return <p className="details-note">Nenhuma informação cadastrada para esta seção.</p>;
  }

  return (
    <dl className="kv-list">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{getSpecLabel(key)}</dt>
          <dd>{formatSpecValue(key, value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function formatUpdate(value) {
  if (!value) return 'Sem registro';
  const [datePart, timePart = ''] = String(value).split('T');
  const [year, month, day] = datePart.split('-');
  if (!year || !month || !day) return value;
  const time = timePart.slice(0, 5);
  return time ? `${day}/${month}/${year} ${time}` : `${day}/${month}/${year}`;
}

function sourceLabel(source) {
  if (source === 'mercado_livre') return 'Mercado Livre';
  if (source === 'manual') return 'Manual';
  if (source === 'telegram') return 'Telegram';
  return 'Legado';
}

function PriceSummaryBox({ summary }) {
  if (!summary) return null;
  const hasRealPrices = (summary.real_offers_count || summary.real_prices_count || 0) > 0;
  const hasSeedPrices = (summary.seed_prices_count || 0) > 0;
  return (
    <div className="price-summary-box">
      <div className="price-summary-item">
        <span>{hasRealPrices && hasSeedPrices ? 'Menor preço geral' : 'Menor preço'}</span>
        <strong className="price-min">{formatCurrency(summary.min_price)}</strong>
      </div>
      {hasRealPrices && (
        <div className="price-summary-item">
          <span>Menor preço Mercado Livre</span>
          <strong className="price-min">{formatCurrency(summary.real_min_price)}</strong>
        </div>
      )}
      <div className="price-summary-item">
        <span>Maior preço</span>
        <strong>{formatCurrency(summary.max_price)}</strong>
      </div>
      <div className="price-summary-item">
        <span>Preço médio</span>
        <strong>{formatCurrency(summary.average_price)}</strong>
      </div>
      <div className="price-summary-item">
        <span>Ofertas encontradas</span>
        <strong>{summary.offers_count}</strong>
      </div>
      <div className="price-summary-item">
        <span>Preços reais</span>
        <strong>{summary.real_offers_count || summary.real_prices_count || 0}</strong>
      </div>
      {hasRealPrices && (
        <div className="price-summary-item">
          <span>Média Mercado Livre</span>
          <strong>{formatCurrency(summary.real_average_price)}</strong>
        </div>
      )}
      <div className="price-summary-item">
        <span>Faixa de variação</span>
        <strong>{formatCurrency(summary.price_range || 0)}</strong>
      </div>
      {summary.last_update && (
        <div className="price-summary-item">
          <span>Última atualização</span>
          <strong>{formatUpdate(summary.last_update)}</strong>
        </div>
      )}
      {!!summary.sources?.length && (
        <div className="price-summary-item price-summary-sources">
          <span>Origem dos preços</span>
          <strong>{summary.sources.map(sourceLabel).join(', ')}</strong>
        </div>
      )}
    </div>
  );
}

export default function ComponentDetails() {
  const { id } = useParams();
  const [component, setComponent] = useState(null);
  const [commerce, setCommerce] = useState(null);
  const [favorite, setFavorite] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [priceSummary, setPriceSummary] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);
  const [priceNotice, setPriceNotice] = useState('');
  const [priceNoticeStatus, setPriceNoticeStatus] = useState('warning');

  const load = useCallback(async () => {
    setCommerce(null);
    const user = getStoredUser();
    
    let nextComponent;
    try {
      const componentRes = await catalogApi.get(`/components/${id}`);
      nextComponent = componentRes.data;
      setComponent(nextComponent);
      setLoading(false); // show the technical sheet now; prices/history/favorites fill in afterwards
    } catch {
      setComponent(null);
      return;
    }

    try {
      const summaryRes = await fetchPriceSummary(id);
      setPriceSummary(summaryRes || getPriceSummary(nextComponent));
    } catch {
      setPriceSummary(getPriceSummary(nextComponent));
    }

    try {
      const historyRes = await fetchPriceHistory(id);
      setPriceHistory(historyRes || nextComponent.price_history || []);
    } catch {
      setPriceHistory(nextComponent.price_history || []);
    }

    try {
      if (user && !DEMO) {
        const favoritesRes = await usersApi.get(`/favorites/${user.id}`);
        setFavorite((favoritesRes.data || []).some((item) => item.component_id === id));
      }
    } catch {
      setFavorite(false);
    }
  }, [id]);

  useEffect(() => {
    load().catch(() => {}).finally(() => setLoading(false));
  }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setPriceNotice('');
    setPriceNoticeStatus('warning');
    try {
      const result = await refreshRealPrices(id);
      const componentRes = await catalogApi.get(`/components/${id}`);
      setComponent(componentRes.data);
      setPriceSummary(result.summary || getPriceSummary(componentRes.data));
      setPriceHistory(result.history || componentRes.data.price_history || []);
      if (result.updated_external) {
        setPriceNoticeStatus('success');
        setPriceNotice(
          `Preços reais encontrados no Mercado Livre. ${result.offers_used || 0} ofertas reais foram adicionadas ao histórico.`
        );
      } else {
        setPriceNoticeStatus('warning');
        setPriceNotice(
          result.external_error
          || `Token válido, mas não foi possível obter ofertas com preço para este produto via ${result.strategy || 'products_search'}. `
          + `Produtos encontrados: ${result.catalog_products_found || 0}. Nenhum preço fictício é exibido.`
        );
      }
    } catch {
      setPriceNoticeStatus('warning');
      setPriceNotice('Não foi possível buscar preços reais agora. Mantivemos os preços salvos no catálogo.');
    } finally {
      setRefreshing(false);
    }
  };

  if (loading) {
    return (
      <>
        <Header />
        <main className="main-container">
          <LoadingState label="Carregando ficha técnica..." />
        </main>
      </>
    );
  }

  if (!component) {
    return (
      <>
        <Header />
        <main className="main-container">
          <EmptyState
            icon={<ShoppingBag size={30} />}
            title="Peça não encontrada"
            text="O componente não está disponível no catálogo atual."
            actionLabel="Voltar ao catálogo"
            actionTo="/"
          />
        </main>
      </>
    );
  }

  const summary = priceSummary || getPriceSummary(component);
  const bestPrice = commerce?.best_general_offer || commerce?.best_conditional_offer || null;
  const bestIsConditional = !commerce?.best_general_offer && !!commerce?.best_conditional_offer;
  const technicalSummary = generateTechnicalSummary(component);
  const categoryLabel = getCategoryLabel(component.category);

  const history = priceHistory.length ? priceHistory : component.price_history || [];


  return (
    <>
      <Header />
      <main className="main-container">
        <Link to="/" className="back-link">
          <ArrowLeft size={17} />
          Voltar ao catálogo
        </Link>

        <section className="details-layout">
          <div className="details-media">
            <HardwareImage component={component} />
          </div>
          <div className="details-content">
            <div className="meta-row">
              <span>{categoryLabel}</span>
              <span>{component.brand}</span>
            </div>
            <div className="details-title-row">
              <h1>{component.name}</h1>
              <FavoriteButton componentId={component.id} active={favorite} onChange={(_, next) => setFavorite(next)} />
            </div>
            <p>{component.description}</p>
            <div className="technical-callout">
              <span className="category-badge">{getCategoryBadge(component.category)}</span>
              <p>{technicalSummary}</p>
            </div>
            <div className="highlight-price">
              <span>{bestIsConditional ? 'Melhor preço com condição' : 'Melhor preço geral'}</span>
              <strong>{bestPrice ? formatCurrency(bestPrice.price) : 'Sem oferta atual'}</strong>
              <small>{bestPrice ? (bestPrice.store || 'Loja não identificada') : 'Sem oferta vigente'}</small>
              {bestPrice?.coupon && <small>Com cupom anunciado: {bestPrice.coupon}</small>}
              {bestPrice && <small>Preço anunciado no Telegram. Confirme na loja antes da compra.</small>}
            </div>
            {bestPrice?.url && (
              <a className="btn-primary buy-link" href={bestPrice.url} target="_blank" rel="noreferrer">
                Ver oferta
              </a>
            )}
          </div>
        </section>

        <OfferComparison key={id} componentId={id} onLoad={setCommerce} />
        {/* Price summary section */}
        <section className="summary-panel price-panel">
          <div className="section-title">
            <div>
              <TrendingDown size={18} />
              <h2>Resumo de preços reais e histórico</h2>
            </div>
            {!DEMO && <button
              type="button"
              className="secondary-button refresh-btn"
              onClick={handleRefresh}
              disabled={refreshing}
              title="Atualizar preços reais"
            >
              <RefreshCw size={15} className={refreshing ? 'spin' : ''} />
              {refreshing ? 'Atualizando...' : 'Atualizar preços reais'}
            </button>}
          </div>
          <PriceSummaryBox summary={summary} />
          {priceNotice && (
            <p className={`price-notice is-${priceNoticeStatus}`}>
              {priceNotice}
            </p>
          )}
          <p className="details-note">Somente preços de fontes reais (ofertas anunciadas e consultas oficiais). O catálogo não gera preços; sem oferta, aparece “Sem oferta atual”.</p><PriceTable prices={component.prices} allowPurchase={false} />
        </section>

        {/* Price history chart */}
        {history.length >= 2 && (
          <section className="summary-panel price-panel">
            <div className="section-title">
              <h2>Histórico de preços</h2>
            </div>
            <PriceChart history={history} />
          </section>
        )}

        <section className="details-columns">
          <div>
            <h2>Ficha técnica</h2>
            <KeyValueList data={component.technical_specs} />
          </div>
          <div>
            <h2>Compatibilidade</h2>
            <KeyValueList data={component.compatibility} />
          </div>
        </section>

        <ExternalSpecs component={component} />

        <section className="details-columns details-secondary">
          <div>
            <div className="section-title">
              <h2>Benchmark</h2>
              <Gauge size={20} />
            </div>
            <KeyValueList data={component.benchmark} />
          </div>
          <div>
            <h2>Resumo técnico</h2>
            <p className="details-note">{technicalSummary}</p>
            <div className="summary-tags">
              <span>{categoryLabel}</span>
              <span>{component.brand}</span>
              <span>{bestPrice ? `A partir de ${formatCurrency(bestPrice.price)}` : 'Preço indisponível'}</span>
            </div>
          </div>
        </section>
      </main>
    </>
  );
}
