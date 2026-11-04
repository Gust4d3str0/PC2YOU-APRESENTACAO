import { useEffect, useState } from 'react';
import { Heart } from 'lucide-react';
import Header from '../components/Header';
import ComponentCard from '../components/ComponentCard';
import EmptyState from '../components/EmptyState';
import LoadingState from '../components/LoadingState';
import { catalogApi, getStoredUser, usersApi } from '../api';

export default function Favorites() {
  const [components, setComponents] = useState([]);
  const [favoriteIds, setFavoriteIds] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const user = getStoredUser();
  const userId = user?.id;

  useEffect(() => {
    const load = async () => {
      if (!userId) {
        setLoading(false);
        return;
      }
      const favorites = await usersApi.get(`/favorites/${userId}`);
      const ids = favorites.data.map((item) => item.component_id);
      setFavoriteIds(new Set(ids));
      const pieces = await Promise.all(ids.map((id) => catalogApi.get(`/components/${id}`)));
      setComponents(pieces.map((res) => res.data));
      setLoading(false);
    };
    load().catch(() => setLoading(false));
  }, [userId]);

  const handleFavoriteChange = (componentId, active) => {
    if (active) return;
    setComponents((current) => current.filter((item) => item.id !== componentId));
    setFavoriteIds((current) => {
      const next = new Set(current);
      next.delete(componentId);
      return next;
    });
  };

  return (
    <>
      <Header />
      <main className="main-container">
        <section className="page-heading">
          <div>
            <span className="eyebrow">Sua lista</span>
            <h1>Favoritos</h1>
          </div>
          <p>Peças separadas para comparar antes de fechar o orçamento.</p>
        </section>

        {!user ? (
          <EmptyState
            icon={<Heart size={30} />}
            title="Entre para ver seus favoritos"
            text="Sua lista fica vinculada à conta para facilitar a comparação depois."
            actionLabel="Fazer login"
            actionTo="/login"
          />
        ) : loading ? (
          <LoadingState label="Carregando favoritos..." cards={3} />
        ) : components.length === 0 ? (
          <EmptyState
            icon={<Heart size={30} />}
            title="Você ainda não favoritou nenhuma peça"
            text="Salve componentes para comparar preços e detalhes antes de fechar a build."
            actionLabel="Explorar catálogo"
            actionTo="/"
          />
        ) : (
          <div className="component-grid">
            {components.map((component) => (
              <ComponentCard
                key={component.id}
                component={component}
                favorite={favoriteIds.has(component.id)}
                onFavoriteChange={handleFavoriteChange}
              />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
