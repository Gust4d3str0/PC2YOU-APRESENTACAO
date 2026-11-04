import { budgetsApi, catalogApi } from '../api';

// Read-only demo endpoints (api-catalogo /demo/*, api-orcamentos /demo/*). No writes except stateless demos.
export const demo = {
  status: () => catalogApi.get('/demo/status').then((r) => r.data),
  aiStatus: () => budgetsApi.get('/demo/ai-status').then((r) => r.data),
  metrics: () => catalogApi.get('/demo/metrics').then((r) => r.data),
  database: () => catalogApi.get('/demo/database').then((r) => r.data),
  collection: (name, page, pageSize = 5) => catalogApi.get(`/demo/database/${name}`, { params: { page, page_size: pageSize } }).then((r) => r.data),
  matcher: (text) => catalogApi.get('/demo/matcher', { params: { text } }).then((r) => r.data),
  telegramSamples: () => catalogApi.get('/demo/telegram-samples').then((r) => r.data),
  telegramParse: (text) => catalogApi.get('/demo/telegram-parse', { params: { text } }).then((r) => r.data),
  telegramLatest: (matched) => catalogApi.get('/demo/telegram-latest', { params: { matched } }).then((r) => r.data),
  mlComponents: () => catalogApi.get('/demo/ml-components').then((r) => r.data),
  mlExample: (componentId) => catalogApi.get('/demo/ml-example', { params: { component_id: componentId } }).then((r) => r.data),
  aiContext: (payload) => budgetsApi.get('/demo/ai-context', { params: { configuration: JSON.stringify(payload) } }).then((r) => r.data),
  analyze: (payload, signal) => budgetsApi.post('/ai/analyze-pc', payload, { signal, timeout: 130000 }).then((r) => r.data),
};

export function proxiedImage(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'https:' && (parsed.hostname === 'mlstatic.com' || parsed.hostname.endsWith('.mlstatic.com'))) {
      return `${catalogApi.defaults.baseURL}/images/proxy?url=${encodeURIComponent(url)}`;
    }
  } catch { /* not a URL */ }
  return null;
}

export function errorText(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  return fallback;
}

export function ago(iso, now = Date.now()) {
  const time = iso ? new Date(iso).getTime() : NaN;
  if (Number.isNaN(time)) return 'data desconhecida';
  const minutes = Math.max(0, Math.round((now - time) / 60000));
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `há ${hours} h` : `há ${Math.round(hours / 24)} dias`;
}
