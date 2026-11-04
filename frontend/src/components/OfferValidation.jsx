import { useState } from 'react';
import { catalogApi, getApiErrorMessage } from '../api';
import { DEMO } from '../demo';

function loggedIn() {
  try { return typeof localStorage !== 'undefined' && !!localStorage.getItem('token'); } catch { return false; }
}

/** A person's check of an announced offer. Nothing is deleted: "no longer works" only removes it from current offers. */
export default function OfferValidation({ offer, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  if (DEMO || !loggedIn() || !offer.id || offer.source !== 'telegram') return null;
  const send = async status => {
    setBusy(true); setMessage('');
    try {
      await catalogApi.post(`/promotions/${offer.id}/validation`, { status });
      setMessage(status === 'valid' ? 'Marcada como funcionando.' : 'Marcada como não funciona mais.');
      onChanged?.();
    } catch (error) { setMessage(getApiErrorMessage(error, 'Não foi possível registrar.')); }
    finally { setBusy(false); }
  };
  return <div className="offer-validation" aria-label="Validar oferta">
    <button type="button" className="secondary-button" disabled={busy} onClick={() => send('valid')}>✓ Oferta funcionando</button>
    <button type="button" className="secondary-button" disabled={busy} onClick={() => send('invalid')}>✕ Oferta não funciona mais</button>
    {message && <em role="status">{message}</em>}
  </div>;
}
