import { useState } from 'react';
import { Heart } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getStoredUser, usersApi } from '../api';
import { DEMO } from '../demo';

export default function FavoriteButton({ componentId, active = false, onChange }) {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const isActive = active;
  if (DEMO) return null; // favorites need login: hidden in the presentation build

  const handleClick = async () => {
    const user = getStoredUser();
    if (!user) {
      navigate('/login');
      return;
    }

    setLoading(true);
    try {
      if (isActive) {
        await usersApi.delete(`/favorites/${user.id}/${componentId}`);
      } else {
        await usersApi.post('/favorites', {
          user_id: user.id,
          component_id: componentId,
        });
      }
      const next = !isActive;
      onChange?.(componentId, next);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      className={`icon-only favorite-button ${isActive ? 'is-active' : ''}`}
      onClick={handleClick}
      disabled={loading}
      title={isActive ? 'Remover dos favoritos' : 'Favoritar peça'}
      aria-label={isActive ? 'Remover dos favoritos' : 'Favoritar peça'}
      type="button"
    >
      <Heart size={19} fill={isActive ? 'currentColor' : 'none'} />
    </button>
  );
}
