import { Link } from 'react-router-dom';
import { ArrowRight, Zap } from 'lucide-react';
import { formatCurrency } from '../api';
import HardwareImage from './HardwareImage';
import FavoriteButton from './FavoriteButton';
import { currentOffers, conditionLabels } from '../utils/commerce';
import { formatSpecValue, getCategoryLabel, getSpecLabel } from '../utils/formatters';

export default function ComponentCard({ component, favorite = false, onFavoriteChange }) {
  const offers = currentOffers(component.current_offers);
  // "A partir de" only from real, current offers: unconditional first, a conditional one is labelled as such.
  const general = offers.find(o => !o.is_conditional) || null;
  const conditional = general ? null : offers[0] || null;
  const bestPrice = general || conditional;
  const specs = Object.entries(component.technical_specs || {}).slice(0, 2);

  return (
    <article className="component-card">
      <div className="component-image-wrap">
        <HardwareImage component={component} className="component-image" />
        <FavoriteButton
          componentId={component.id}
          active={favorite}
          onChange={onFavoriteChange}
        />
      </div>

      <div className="component-info">
        <div className="meta-row">
          <span>{getCategoryLabel(component.category)}</span>
          <span>{component.brand}</span>
        </div>
        <h3>{component.name}</h3>
        <p>{component.description}</p>
        <div className="spec-chips" aria-label="Especificações principais">
          {specs.map(([key, value]) => (
            <span key={key}>
              <Zap size={13} />
              {getSpecLabel(key)}: {formatSpecValue(key, value)}
            </span>
          ))}
        </div>

        <div className="price-row">
          <div>
            {bestPrice && <span className="muted">{conditional ? 'Oferta com condição a partir de' : 'A partir de'}</span>}
            <strong>{bestPrice ? formatCurrency(bestPrice.price) : 'Sem oferta atual'}</strong>
            {bestPrice?.coupon && <span className="price-range">Com cupom anunciado: {bestPrice.coupon}</span>}
            {conditional && conditionLabels(conditional).length > 0 && <span className="price-range">{conditionLabels(conditional).join(' · ')}</span>}
            {bestPrice && <span className="price-range">{offers.length} {offers.length === 1 ? 'oferta anunciada' : 'ofertas anunciadas'}</span>}
          </div>
          <span className="store-tag">{bestPrice?.store || 'Sem loja'}</span>
        </div>

        <Link className="details-link" to={`/components/${component.id}`}>
          {offers.length > 1 ? `Comparar ${offers.length} ofertas` : 'Ver detalhes'}
          <ArrowRight size={17} />
        </Link>
      </div>
    </article>
  );
}
