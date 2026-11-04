import { ExternalLink } from 'lucide-react';
import { formatCurrency } from '../api';
import { safeLink } from '../utils/commerce';

function formatUpdate(value) {
  if (!value) return 'Sem data';
  const [datePart, timePart = ''] = String(value).split('T');
  const [year, month, day] = datePart.split('-');
  if (!year || !month || !day) return value;
  const time = timePart.slice(0, 5);
  return time ? `${day}/${month}/${year} ${time}` : `${day}/${month}/${year}`;
}

function sourceLabel(source) {
  if (source === 'mercado_livre') return 'Real';
  if (source === 'manual') return 'Manual';
  if (source === 'telegram') return 'Telegram';
  return 'Legado';
}

export default function PriceTable({ prices = [], allowPurchase = true }) {
  const sortedPrices = [...prices].sort((a, b) => Number(a.price || 0) - Number(b.price || 0));

  return (
    <div className="table-wrap">
      <table className="price-table">
        <thead>
          <tr>
            <th>Oferta</th>
            <th>Origem</th>
            <th>Preço</th>
            <th>Atualização</th>
            <th>Link</th>
          </tr>
        </thead>
        <tbody>
          {!sortedPrices.length && (
            <tr>
              <td colSpan="5">Nenhuma oferta cadastrada.</td>
            </tr>
          )}
          {sortedPrices.map((price, index) => (
            <tr key={price.external_id || `${price.store}-${price.url}-${index}`}>
              <td>
                <strong className="offer-title">{price.title || price.store}</strong>
                <span className="offer-store">{price.seller || price.store}</span>
              </td>
              <td>
                <span className={`price-source-pill source-${price.source || 'seed'}`}>
                  {sourceLabel(price.source)}
                </span>
              </td>
              <td>{formatCurrency(price.price)}</td>
              <td>{formatUpdate(price.last_update)}</td>
              <td>
                {allowPurchase && price.source !== 'seed' && safeLink(price.url) ? <a href={price.url} target="_blank" rel="noreferrer" className="store-link" title="Abrir loja">
                  Abrir loja
                  <ExternalLink size={17} />
                </a> : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
