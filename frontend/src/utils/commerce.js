export function safeLink(value) {
  try { const u = new URL(value); return ['http:', 'https:'].includes(u.protocol) && !u.username && !u.password ? value : null; }
  catch { return null; }
}

export function currentOffers(offers = [], now = new Date()) {
  return offers.filter(o => o.source !== 'seed' && o.state === 'active' && o.eligible !== false && o.status !== 'invalid' && Number(o.price) > 0
    && (!o.valid_until || new Date(o.valid_until) >= now)
    && (!o.fresh_until || new Date(o.fresh_until) >= now)).sort((a, b) => a.price - b.price);
}

const HOUR = 3600 * 1000;
const NOT_CURRENT = ['Expirada', 'Não funciona mais', 'Sem validade conhecida', 'Histórico'];

/** Honest wording: an announcement is never "active"; only a recorded check makes it "confirmed". */
export function offerLabel(offer, now = new Date()) {
  if (offer.status === 'invalid' || offer.state === 'invalid') return 'Não funciona mais';
  if (offer.status === 'expired' || offer.state === 'expired' || (offer.valid_until && new Date(offer.valid_until) < now)
    || (offer.fresh_until && new Date(offer.fresh_until) < now)) return 'Expirada';
  if (offer.state !== 'active') return 'Sem validade conhecida';
  if (offer.status === 'stale') return offer.eligible === false ? 'Histórico' : 'Oferta desatualizada';
  if (offer.valid_until && new Date(offer.valid_until).toLocaleDateString('pt-BR', {timeZone:'America/Sao_Paulo'}) === now.toLocaleDateString('pt-BR', {timeZone:'America/Sao_Paulo'})) return 'Expira hoje';
  if (offer.status === 'confirmed') return 'Confirmada recentemente';
  if (offer.status === 'conditional' || offer.is_conditional) return 'Oferta com condição';
  return 'Anunciada recentemente';
}

export const isCurrent = (offer, now = new Date()) => !NOT_CURRENT.includes(offerLabel(offer, now));

/** "Anunciada há 18 min" — relative to the Telegram announcement, not to any check. */
export function announcedAgo(iso, now = new Date()) {
  const at = iso ? new Date(iso) : null;
  if (!at || Number.isNaN(at.getTime())) return 'Data do anúncio não informada';
  const minutes = Math.max(0, Math.round((now - at) / 60000));
  if (minutes < 1) return 'Anunciada agora há pouco';
  if (minutes < 60) return `Anunciada há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `Anunciada há ${hours} h`;
  return `Anunciada há ${Math.round(hours / 24)} dias`;
}

/** Condition labels shown beside the coupon block (the coupon itself has its own block). */
export const conditionLabels = offer => (offer.condition_labels || []).filter(l => l !== 'Exige cupom');

export const isConfirmed = offer => offer.status === 'confirmed';

export function imageCandidates(component = {}) {
  const category = component.category === 'kit-ram' ? 'ram' : component.category;
  const official = component.external_enrichment?.mercado_livre;
  const officialImages = official && official.match_status === 'matched' && !official.external_conflict ? official.images || [] : [];
  // promotion image > official Mercado Livre product picture > internal real image > the rest
  const remote = [...(component.current_offers || []).flatMap(o => [o.thumbnail, o.image_source === 'promotion' ? o.image : null]),
    ...officialImages, component.real_image, ...(component.images || []), component.thumbnail,
    ...(component.current_offers || []).flatMap(o => [o.image_source === 'promotion' ? null : o.image]),
    ...(component.prices || []).filter(p => p.source === 'mercado_livre').flatMap(p => [p.thumbnail, ...(p.images || [])]), component.image];
  const local = ['rtx-5060-8gb', 'rtx-5060-ti-8gb', 'rtx-5060-ti-16gb'].includes(component.id) ? `/images/${component.id}.png` : null;
  return [...new Set([...remote.filter(v => typeof v === 'string' && !v.includes('default-') && !v.includes('placehold.co')), local,
    `/components/default-${category || 'component'}.png`, '/components/default-component.png'].filter(v =>
    typeof v === 'string' && (v.startsWith('/') && !v.startsWith('//') || safeLink(v))))];
}

export const DESTINATION_LABELS = { product: 'Produto', search: 'Busca na loja', homepage: 'Página inicial', unknown: 'Destino não verificado' };
export const destinationLabel = kind => DESTINATION_LABELS[kind] || DESTINATION_LABELS.unknown;

export async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch {
    try {
      const field = Object.assign(document.createElement('textarea'), { value: text });
      field.setAttribute('readonly', ''); field.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(field); field.select();
      const ok = document.execCommand('copy'); field.remove(); return ok;
    } catch { return false; }
  }
}
