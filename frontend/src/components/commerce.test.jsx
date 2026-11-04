import { describe, it, expect, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { PromotionCard } from './PromotionSection';
import HardwareImage from './HardwareImage';
import PriceTable from './PriceTable';
import OfferTable from './OfferTable';
import { currentOffers, imageCandidates, offerLabel, copyText, destinationLabel, announcedAgo, isCurrent } from '../utils/commerce';
import ComponentCard from './ComponentCard';
import ExternalSpecs from './ExternalSpecs';

const offer = {id:'one',component_id:'gpu',name:'RTX 5060 Ti 8GB',category:'gpu',brand:'NVIDIA',source:'telegram',store:'KaBuM',price:2000,coupon:'ANNOUNCED',state:'active',url:'https://www.kabum.com.br/produto/123',captured_at:new Date().toISOString()};
const render = o => renderToStaticMarkup(<MemoryRouter><PromotionCard offer={o}/></MemoryRouter>);

describe('home commerce cards', () => {
  it('shows a real projected active promotion with announced coupon and working URL', () => {
    const html=render(offer);expect(html).toContain('RTX 5060 Ti 8GB');expect(html).toContain('Ver oferta');expect(html).toContain('Cupom anunciado');expect(html).not.toContain('Cupom validado');
  });
  it('keeps expired prices visibly historical and removes the purchase action', () => {
    const html=render({...offer,state:'expired'});expect(html).toContain('Expirada');expect(html).toContain('Preço histórico');expect(html).not.toContain('Ver oferta');
  });
  it('does not render an invalid URL action', () => {expect(render({...offer,url:'javascript:alert(1)'})).not.toContain('Ver oferta');});
  it('uses real image ahead of fallback and preserves local category fallback', () => {
    expect(renderToStaticMarkup(<HardwareImage component={{name:'GPU',category:'gpu',real_image:'https://example.com/gpu.jpg'}}/>)).toContain('https://example.com/gpu.jpg');
    expect(imageCandidates({category:'gpu'})).toContain('/components/default-gpu.png');
    expect(imageCandidates({category:'cpu'})).not.toEqual(imageCandidates({category:'gpu'}));
  });
  it('rejects a coupon whose deadline passed even when a stale active flag remains', () => {
    const expired={...offer,valid_until:'2000-01-01T00:00:00Z'};
    expect(currentOffers([expired])).toEqual([]);expect(offerLabel(expired)).toBe('Expirada');
  });
  it('sorts only non-seed valid offers by the lowest current price', () => {
    expect(currentOffers([{...offer,price:2200},{...offer,price:1900},{...offer,price:1,source:'seed'}])[0].price).toBe(1900);
  });
  it('keeps freshness separate from a deadline announced by the channel', () => {
    expect(render({...offer,valid_until:null,fresh_until:'2099-01-01T00:00:00Z'})).toContain('Validade não informada');
    expect(currentOffers([{...offer,fresh_until:'2000-01-01T00:00:00Z'}])).toEqual([]);
  });
  it('does not turn catalog reference links into purchase actions', () => {
    const html=renderToStaticMarkup(<PriceTable prices={[{store:'Seed',price:1,url:'https://example.com',source:'seed'}]} allowPurchase={false}/>);
    expect(html).not.toContain('href=');
  });
});

describe('telegram commerce final', () => {
  it('shows announced coupon with a copy button, the price condition and never claims validation', () => {
    const html = render({...offer, coupon: 'ZAFADINHO10', price: 2789});
    expect(html).toContain('Cupom anunciado'); expect(html).toContain('ZAFADINHO10'); expect(html).toContain('Copiar cupom');
    expect(html).toContain('com cupom'); expect(html).not.toMatch(/validado|funcionando/i);
  });
  it('copies the coupon text', async () => {
    const writeText = vi.fn().mockResolvedValue();
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    expect(await copyText('ZAFADINHO10')).toBe(true); expect(writeText).toHaveBeenCalledWith('ZAFADINHO10');
    vi.unstubAllGlobals();
  });
  it('uses neutral states for missing store, coupon and deadline', () => {
    const html = render({...offer, store: null, coupon: null, valid_until: null});
    expect(html).toContain('Loja não identificada'); expect(html).toContain('Sem cupom anunciado'); expect(html).toContain('Validade não informada');
  });
  it('labels the destination and warns when the link only leads to a search or homepage', () => {
    expect(render({...offer, url_kind: 'product'})).toContain('Destino: Produto');
    const search = render({...offer, url_kind: 'search'});
    expect(search).toContain('Busca na loja'); expect(search).toContain('não ao produto'); expect(search).toContain('Ver oferta');
    expect(render({...offer, url_kind: 'homepage'})).toContain('página inicial');
    expect(destinationLabel(undefined)).toBe('Destino não verificado');
  });
  it('shows an offers-available link only for several active offers and keeps expired ones non-purchasable', () => {
    expect(render({...offer, offers_count: 6})).toContain('6 ofertas disponíveis');
    expect(render({...offer, offers_count: 1})).not.toContain('ofertas disponíveis');
    const expired = render({...offer, state: 'expired', offers_count: 6});
    expect(expired).toContain('Expirada'); expect(expired).not.toContain('Ver oferta'); expect(expired).not.toContain('ofertas disponíveis');
  });
  it('renders the comparison table with store, price, coupon, status and destination', () => {
    const rows = [{...offer, id: 'a', price: 2000, url_kind: 'product'}, {...offer, id: 'b', price: 2100, store: 'Pichau', coupon: null, url_kind: 'search'}];
    const html = renderToStaticMarkup(<OfferTable offers={rows} bestId="a"/>);
    for (const text of ['Loja', 'Preço', 'Cupom', 'Status', 'Destino', 'Pichau', 'Melhor oferta', 'Busca na loja']) expect(html).toContain(text);
  });
  it('prefers the promotion image, then component images, then a distinct category fallback', () => {
    expect(imageCandidates({category: 'gpu', image: 'https://img.example/promo.jpg'})[0]).toBe('https://img.example/promo.jpg');
    for (const category of ['cpu', 'gpu', 'motherboard', 'ram', 'storage', 'psu', 'case', 'cooler']) expect(imageCandidates({category})).toContain(`/components/default-${category}.png`);
  });
});

describe('real pricing refactor', () => {
  const cond = {...offer, status: 'conditional', is_conditional: true, condition_labels: ['Exige cupom', 'Somente primeira compra'], eligible: true};
  it('never calls an announcement "active": recent, conditional and confirmed are different statuses', () => {
    expect(offerLabel({...offer, status: 'announced'})).toBe('Anunciada recentemente');
    expect(offerLabel(cond)).toBe('Oferta com condição');
    expect(offerLabel({...offer, status: 'confirmed'})).toBe('Confirmada recentemente');
    expect(offerLabel({...offer, status: 'stale', eligible: true})).toBe('Oferta desatualizada');
    expect(offerLabel({...offer, status: 'invalid', state: 'invalid'})).toBe('Não funciona mais');
    for (const status of ['announced', 'conditional', 'confirmed']) expect(offerLabel({...offer, status})).not.toBe('Ativa');
  });
  it('invalid and ineligible offers are not current', () => {
    expect(currentOffers([{...offer, status: 'invalid', state: 'invalid'}, {...offer, eligible: false}])).toEqual([]);
    expect(isCurrent({...offer, state: 'invalid', status: 'invalid'})).toBe(false);
  });
  it('shows condition, announcement age and the "confirm in store" warning on an unconfirmed card', () => {
    const html = render({...cond, coupon: 'AURAGAMER', captured_at: new Date(Date.now() - 18 * 60000).toISOString()});
    expect(html).toContain('Condição: Somente primeira compra'); expect(html).toContain('Anunciada há 18 min');
    expect(html).toContain('Confirme na loja antes da compra'); expect(html).not.toContain('confirmada recentemente');
    expect(html).toContain('Oferta com condição'); expect(html).not.toContain('>Exige cupom<');
  });
  it('shows the confirmed badge only for a confirmed offer', () => {
    expect(render({...offer, status: 'confirmed'})).toContain('✓ Oferta confirmada recentemente');
    expect(render({...offer, status: 'announced'})).not.toContain('confirmada recentemente');
  });
  it('catalog card says "A partir de" only with a real offer and otherwise "Sem oferta atual"', () => {
    const card = c => renderToStaticMarkup(<MemoryRouter><ComponentCard component={{id:'g',name:'GPU',category:'gpu',brand:'X',description:'d',technical_specs:{},...c}}/></MemoryRouter>);
    expect(card({current_offers: []})).toContain('Sem oferta atual'); expect(card({current_offers: []})).not.toContain('A partir de');
    const general = card({current_offers: [{...offer, price: 1839, is_conditional: false}, {...cond, price: 1683}]});
    expect(general).toContain('A partir de'); expect(general).toContain('1.839'); expect(general).not.toContain('com condição');
    const only = card({current_offers: [{...cond, price: 1683}]});
    expect(only).toContain('Oferta com condição a partir de'); expect(only).toContain('Somente primeira compra');
  });
  it('formats how long ago the offer was announced', () => {
    const now = new Date('2026-11-03T12:00:00Z');
    expect(announcedAgo('2026-11-03T11:42:00Z', now)).toBe('Anunciada há 18 min');
    expect(announcedAgo('2026-11-03T08:00:00Z', now)).toBe('Anunciada há 4 h');
    expect(announcedAgo(null, now)).toContain('não informada');
  });
});

describe('promotion validation wording', () => {
  it('says conditions were not informed when there is a coupon and no known condition', () => {
    expect(render({...offer, coupon: 'XYZ', condition_labels: ['Exige cupom']})).toContain('Condições não informadas no anúncio.');
    expect(render({...offer, coupon: 'XYZ', condition_labels: ['Exige cupom', 'Somente pelo app']})).not.toContain('Condições não informadas');
  });
  it('shows first-purchase and app conditions objectively in the comparison table', () => {
    const rows = [{...offer, id: 'a', coupon: 'AURAGAMER', condition_labels: ['Exige cupom', 'Somente primeira compra', 'Somente pelo app'], status: 'conditional'},
                  {...offer, id: 'b', coupon: null, condition_labels: [], status: 'announced', store: 'Amazon'}];
    const html = renderToStaticMarkup(<OfferTable offers={rows} bestId="b" bestConditionalId="a"/>);
    expect(html).toContain('Somente primeira compra · Somente pelo app'); expect(html).toContain('Melhor com condição'); expect(html).toContain('Oferta com condição');
  });
  it('an old unconfirmed offer is "desatualizada", never "ativa"', () => {
    expect(offerLabel({...offer, status: 'stale', eligible: true})).toBe('Oferta desatualizada');
    expect(offerLabel({...offer, status: 'stale', eligible: false})).toBe('Histórico');
  });
});

describe('Mercado Livre product enrichment', () => {
  const official = 'https://http2.mlstatic.com/D_NQ_NP_a.jpg';
  const enriched = (extra = {}) => ({id: 'gpu-x', category: 'gpu', name: 'GeForce RTX 5060 Ti 8GB', real_image: 'https://img.example/real.jpg',
    external_enrichment: {mercado_livre: {match_status: 'matched', external_conflict: false, images: [official], brand: 'Gigabyte', manufacturer: 'Nvidia',
      model: 'WINDFORCE MAX OC', short_description: 'Placa compacta.', specs: {memory_size: '8 GB', memory_type: 'GDDR7', power_requirement: '650 W', length: '208 mm', unknown_key: 'x'}, ...extra}}});
  it('uses the official picture ahead of the internal real image, after a promotion picture', () => {
    expect(imageCandidates(enriched())[0]).toBe(official);
    expect(imageCandidates({...enriched(), current_offers: [{image: 'https://img.example/promo.jpg', image_source: 'promotion'}]})[0]).toBe('https://img.example/promo.jpg');
    expect(imageCandidates(enriched())).toContain('/components/default-gpu.png');
  });
  it('ignores an enrichment that conflicts or was not matched', () => {
    for (const extra of [{match_status: 'conflict'}, {match_status: 'ambiguous'}, {external_conflict: true}]) expect(imageCandidates(enriched(extra))[0]).toBe('https://img.example/real.jpg');
  });
  it('renders the enriched specifications discreetly and only the known fields', () => {
    const html = renderToStaticMarkup(<ExternalSpecs component={enriched()}/>);
    for (const text of ['Especificações enriquecidas por fonte externa', 'Gigabyte', 'WINDFORCE MAX OC', 'GDDR7', '650 W', '208 mm', 'Placa compacta.']) expect(html).toContain(text);
    expect(html).not.toContain('unknown_key'); expect(html).not.toContain('Erro'); expect(html).not.toMatch(/403|PolicyAgent|token/i);
  });
  it('shows nothing without trusted enrichment', () => {
    expect(renderToStaticMarkup(<ExternalSpecs component={{name: 'x'}}/>)).toBe('');
    expect(renderToStaticMarkup(<ExternalSpecs component={enriched({match_status: 'conflict'})}/>)).toBe('');
  });
});
