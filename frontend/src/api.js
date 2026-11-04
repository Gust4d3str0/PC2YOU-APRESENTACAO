import axios from 'axios';
import { imageCandidates } from './utils/commerce';

export const usersApi = axios.create({
  baseURL: import.meta.env.VITE_USERS_API_URL || 'http://localhost:8001',
});

export const catalogApi = axios.create({
  baseURL: import.meta.env.VITE_CATALOG_API_URL || 'http://localhost:8002',
});

export const budgetsApi = axios.create({
  baseURL: import.meta.env.VITE_BUDGETS_API_URL || 'http://localhost:8003',
});

const apiClients = [usersApi, catalogApi, budgetsApi];

apiClients.forEach((client) => {
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });
});

export function getStoredUser() {
  const value = localStorage.getItem('user');
  return value ? JSON.parse(value) : null;
}

export function getApiErrorMessage(error, fallback = 'Não foi possível concluir a operação.') {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  if (detail?.errors?.length) return detail.errors.join(' ');
  return fallback;
}

export function formatCurrency(value) {
  return Number(value || 0).toLocaleString('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  });
}

export function getBestPrice(component) {
  const prices = component?.prices || [];
  if (!prices.length) return null;
  return prices.reduce((best, current) => (
    current.price < best.price ? current : best
  ), prices[0]);
}

export function getPriceSummary(component) {
  const prices = component?.prices || [];
  if (!prices.length) return null;
  const sorted = [...prices].sort((a, b) => a.price - b.price);
  const realPrices = sorted.filter((p) => p.source === 'mercado_livre');
  const seedPrices = sorted.filter((p) => (p.source || 'seed') === 'seed');
  const avg = prices.reduce((s, p) => s + p.price, 0) / prices.length;
  const priceRange = sorted[sorted.length - 1].price - sorted[0].price;
  const sources = [...new Set(prices.map((p) => p.source || 'seed'))];
  const stats = (items) => {
    if (!items.length) {
      return {
        min_price: null,
        max_price: null,
        average_price: null,
        offers_count: 0,
        best_offer: null,
        highest_offer: null,
      };
    }
    return {
      min_price: items[0].price,
      max_price: items[items.length - 1].price,
      average_price: items.reduce((sum, p) => sum + p.price, 0) / items.length,
      offers_count: items.length,
      best_offer: items[0],
      highest_offer: items[items.length - 1],
    };
  };
  const realStats = stats(realPrices);
  const seedStats = stats(seedPrices);
  return {
    min_price: sorted[0].price,
    max_price: sorted[sorted.length - 1].price,
    average_price: avg,
    price_range: priceRange,
    variation_percent: sorted[0].price ? (priceRange / sorted[0].price) * 100 : 0,
    offers_count: prices.length,
    real_prices_count: realStats.offers_count,
    seed_prices_count: seedStats.offers_count,
    real_min_price: realStats.min_price,
    real_max_price: realStats.max_price,
    real_average_price: realStats.average_price,
    real_offers_count: realStats.offers_count,
    real_best_offer: realStats.best_offer,
    real_highest_offer: realStats.highest_offer,
    seed_min_price: seedStats.min_price,
    seed_max_price: seedStats.max_price,
    seed_average_price: seedStats.average_price,
    best_offer: sorted[0],
    highest_offer: sorted[sorted.length - 1],
    last_update: prices
      .map((p) => p.last_update)
      .filter(Boolean)
      .sort()
      .at(-1) || null,
    sources,
  };
}

export async function fetchPriceSummary(componentId) {
  const res = await catalogApi.get(`/components/${componentId}/price-summary`);
  return res.data;
}

export async function fetchPriceHistory(componentId) {
  const res = await catalogApi.get(`/components/${componentId}/price-history`);
  return res.data.history || [];
}

export async function refreshRealPrices(componentId) {
  const res = await catalogApi.post(`/components/${componentId}/refresh-real-prices`);
  return res.data;
}

function proxiedImageUrl(url) {
  if (typeof url !== 'string') return url;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'https:' && (
      parsed.hostname === 'mlstatic.com' || parsed.hostname.endsWith('.mlstatic.com')
    )) {
      return `${catalogApi.defaults.baseURL}/images/proxy?url=${encodeURIComponent(url)}`;
    }
  } catch {
    return url;
  }
  return url;
}

export function getComponentImage(component) {
  return proxiedImageUrl(imageCandidates(component)[0]);
}
