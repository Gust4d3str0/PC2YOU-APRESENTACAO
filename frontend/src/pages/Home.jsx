import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useSearchParams } from 'react-router-dom';
import { SearchX, ArrowUpRight, Sparkles } from 'lucide-react';
import PromotionSection from '../components/PromotionSection';
import './Commerce.css';
import Header from '../components/Header';
import ComponentCard from '../components/ComponentCard';
import EmptyState from '../components/EmptyState';
import LoadingState from '../components/LoadingState';
import { catalogApi, getStoredUser, usersApi } from '../api';

const categories = [
  { id: '', label: 'Todos' },
  { id: 'cpu', label: 'Processadores' },
  { id: 'motherboard', label: 'Placas-mãe' },
  { id: 'ram', label: 'Memórias' },
  { id: 'storage', label: 'SSDs' },
  { id: 'gpu', label: 'Placas de vídeo' },
  { id: 'psu', label: 'Fontes' },
  { id: 'case', label: 'Gabinetes' },
  { id: 'cooler', label: 'Coolers' },
];

const PAGE_SIZE = 24;

export default function Home() {
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get('q') || '';
  const category = searchParams.get('category') || '';
  const [components, setComponents] = useState([]);
  const [favoriteIds, setFavoriteIds] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);

  const activeLabel = useMemo(() => (
    categories.find((item) => item.id === category)?.label || 'Todos'
  ), [category]);

  useEffect(() => {
    const controller = new AbortController();
    let firstLoad = true;
    const fetchResults = async () => {
      if (firstLoad) setLoading(true);
      setError('');
      try {
        const params = { skip: 0, limit: PAGE_SIZE };
        if (q) params.q = q;
        if (category) params.category = category;
        const res = await catalogApi.get('/commerce/catalog', { params, signal:controller.signal });
        if (controller.signal.aborted) return;
        setComponents(res.data.items);
        setTotal(res.data.total ?? res.data.items.length);
      } catch (err) {
        if (controller.signal.aborted) return;
        console.error(err);
        setError('Não foi possível carregar o catálogo agora.');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
        firstLoad = false;
      }
    };

    fetchResults();
    return () => controller.abort();
  }, [q, category, reloadKey]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const params = { skip: components.length, limit: PAGE_SIZE };
      if (q) params.q = q;
      if (category) params.category = category;
      const res = await catalogApi.get('/commerce/catalog', { params });
      setComponents((current) => {
        const seen = new Set(current.map((item) => item.id));
        return [...current, ...res.data.items.filter((item) => !seen.has(item.id))];
      });
      setTotal(res.data.total ?? total);
    } catch (err) {
      console.error(err);
      setError('Não foi possível carregar mais peças agora.');
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    const loadFavorites = async () => {
      const user = getStoredUser();
      if (!user) return;
      const res = await usersApi.get(`/favorites/${user.id}`);
      setFavoriteIds(new Set(res.data.map((item) => item.component_id)));
    };
    loadFavorites().catch(() => setFavoriteIds(new Set()));
  }, []);

  const setCategory = (nextCategory) => {
    const params = {};
    if (q) params.q = q;
    if (nextCategory) params.category = nextCategory;
    setSearchParams(params);
  };

  const handleFavoriteChange = (componentId, active) => {
    setFavoriteIds((current) => {
      const next = new Set(current);
      if (active) next.add(componentId);
      else next.delete(componentId);
      return next;
    });
  };

  return (
    <>
      <Header />
      <main className="main-container">
        <section className="commerce-hero">
          <div><span className="eyebrow"><Sparkles size={14} /> Hardware, ofertas e escolhas melhores</span>
          <h1>Monte, compare e encontre o melhor hardware para seu PC.</h1>
          <p>Compare preços, encontre promoções e use inteligência artificial para escolher suas peças.</p>
          <div className="hero-actions"><Link className="btn-primary" to="/build">Montar meu PC <ArrowUpRight size={17}/></Link>
          <a className="secondary-button" href="#promocoes">Ver promoções</a>
          <Link className="commerce-ai-link" to="/analyze-pc">Analisar meu PC com IA →</Link></div></div>
          <aside className="hero-note"><span>Seu próximo upgrade</span><strong>Começa com<br/>uma boa comparação.</strong><p>Do produto certo à oferta que faz sentido para você.</p></aside>
        </section>
        <PromotionSection key={`a-${category}`} category={category} mode="active" />

        <section className="catalog-section" id="catalogo">
          <div className="page-heading catalog-heading">
            <div>
              <span className="eyebrow">Catálogo PC2YOU</span>
              <h2>Hardware</h2>
            </div>
            <p>
              {q ? `Resultados para "${q}" em ${activeLabel}` : `Exibindo ${activeLabel}`}
            </p>
          </div>

          <div className="category-tabs" role="tablist" aria-label="Categorias">
            {categories.map((item) => (
              <button
                type="button"
                key={item.id}
                className={item.id === category ? 'is-active' : ''}
                onClick={() => setCategory(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>

          {error ? (
            <EmptyState
              icon={<SearchX size={30} />}
              title="Catálogo indisponível"
              text={error}
              actionLabel="Tentar novamente"
              onAction={() => setReloadKey(k => k+1)}
            />
          ) : loading ? (
            <LoadingState label="Carregando peças..." cards={6} />
          ) : components.length === 0 ? (
            <EmptyState
              icon={<SearchX size={30} />}
              title="Nenhuma peça encontrada"
              text="Tente outro termo de busca ou veja todas as categorias disponíveis."
              actionLabel="Limpar filtros"
              actionTo="/"
            />
          ) : (
            <div className="component-grid">
              {components.map(component => (
                <ComponentCard
                  key={component.id}
                  component={component}
                  favorite={favoriteIds.has(component.id)}
                  onFavoriteChange={handleFavoriteChange}
                />
              ))}
            </div>
          )}
          {!loading && !error && components.length > 0 && components.length < total && (
            <div className="load-more">
              <button type="button" className="secondary-button" onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? 'Carregando...' : 'Carregar mais'}
              </button>
              <small>{components.length} de {total}</small>
            </div>
          )}
        </section>
        <PromotionSection key={`h-${category}`} category={category} mode="history" />
      </main>
    </>
  );
}
