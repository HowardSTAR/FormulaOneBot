import { SingleFlight } from './singleFlight';

// Точно как в web/app/static/js/common.js — читаем при каждом запросе
function getInitData(): string {
  const tg = typeof window !== 'undefined'
    ? (window as unknown as { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp
    : undefined;
  return tg?.initData ?? '';
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split('; ').find((value) => value.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

// VITE_API_URL = полный URL бэкенда, если фронт и API на разных серверах
// BASE_URL = базовый путь, если приложение развёрнуто в подпапке (например /bot/)
const CONFIGURED_API_BASE = (import.meta.env.VITE_API_URL as string) || '';
const IS_LOCAL_HOST = typeof window !== 'undefined'
  && ['localhost', '127.0.0.1'].includes(window.location.hostname);
const API_BASE = IS_LOCAL_HOST ? '' : CONFIGURED_API_BASE;
const PATH_BASE = ((import.meta.env.BASE_URL as string) || '/').replace(/\/$/, '');
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS || 15000);
const reportedErrors = new Map<string,number>();
const pendingReads = new SingleFlight();

export function invalidateApiReads(): void {
  pendingReads.clear();
}

export function apiAssetUrl(
  endpoint: string,
  params: Record<string, string | number | boolean | undefined> = {}
): string {
  const path = (PATH_BASE + endpoint).replace(/\/+/g, '/');
  const url = API_BASE ? new URL(endpoint, API_BASE) : new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      url.searchParams.set(key, String(value));
    }
  });
  return url.toString();
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.name = 'ApiError'; this.status = status; }
}

export function apiRequest<T = unknown>(
  endpoint: string,
  params: Record<string, unknown> = {},
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE' = 'GET',
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const request = () => executeApiRequest<T>(endpoint, params, method, timeoutMs);
  if (method !== 'GET') return request();
  const key = JSON.stringify([
    endpoint, Object.entries(params).sort(([a], [b]) => a.localeCompare(b)),
    getInitData(), readCookie('turbotears_csrf'), timeoutMs,
  ]);
  return pendingReads.run(key, request);
}

async function executeApiRequest<T = unknown>(
  endpoint: string,
  params: Record<string, unknown> = {},
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE' = 'GET',
  timeoutMs: number = REQUEST_TIMEOUT_MS
): Promise<T> {
  const path = (PATH_BASE + endpoint).replace(/\/+/g, '/');
  const url = API_BASE ? new URL(endpoint, API_BASE) : new URL(path, window.location.origin);

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  const initData = getInitData();
  if (initData) {
    headers['X-Telegram-Init-Data'] = initData;
  }
  const csrf = readCookie('turbotears_csrf');
  if (csrf) {
    headers['X-CSRF-Token'] = csrf;
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const options: RequestInit = { method, headers, signal: controller.signal, credentials: 'include' };

  if (method === 'GET') {
    Object.keys(params).forEach((key) => {
      const val = params[key];
      if (val !== null && val !== undefined) {
        url.searchParams.append(key, String(val));
      }
    });
  } else if (method !== 'DELETE' || Object.keys(params).length > 0) {
    (options as RequestInit & { body?: string }).body = JSON.stringify(params);
  }

  if (import.meta.env.DEV) {
    console.log(`[API] ${method} ${url.toString()}`);
  }

  let response: Response;
  const reportError = (error_code: number) => {
    if (endpoint.startsWith('/api/analytics/')) return;
    const path = window.location.pathname.startsWith('/share/') ? '/share' : window.location.pathname;
    if (!/^\/[a-zA-Z0-9/_-]*$/.test(path) || path.length > 160) return;
    if (Date.now() - (reportedErrors.get(path) || 0) < 300000) return;
    reportedErrors.set(path,Date.now());
    const platform = getInitData() ? 'telegram' : window.matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone ? 'pwa' : 'browser';
    // No response body, URL query, form values, or stack trace. Raw fetch avoids recursion.
    void fetch(apiAssetUrl('/api/analytics/event'), { method:'POST',credentials:'include',headers,
      body:JSON.stringify({event:'error',path,platform,error_code}),keepalive:true }).catch(() => {});
  };
  try {
    response = await fetch(url, options);
  } catch (e) {
    reportError(0);
    if ((e as Error)?.name === 'AbortError') {
      throw new Error('Превышено время ожидания ответа сервера.');
    }
    throw new ApiError('Нет соединения с сервером. Проверьте сеть и повторите запрос.', 0);
  } finally {
    window.clearTimeout(timeoutId);
  }

  const contentType = response.headers.get('content-type') || '';
  if (response.status >= 500) reportError(response.status);
  if (contentType.includes('text/html')) {
    throw new ApiError('Сервис временно недоступен. Попробуйте повторить запрос.', response.status);
  }

  if (!response.ok) {
    let serverMessage = "";
    try {
      const payload = await response.json() as { detail?: string | { message?: string } | { msg?: string }[] };
      serverMessage = typeof payload.detail === 'string' ? payload.detail
        : Array.isArray(payload.detail) ? payload.detail[0]?.msg || ''
          : payload.detail?.message || '';
    } catch { /* response without JSON */ }
    const msg = serverMessage || (response.status === 401
      ? 'Войдите в аккаунт или откройте приложение в Telegram'
      : response.status === 403
        ? 'Нет доступа к этому действию. Проверьте аккаунт и права доступа.'
        : 'Не удалось получить ответ сервера. Попробуйте повторить запрос.');
    throw new ApiError(response.status >= 500 ? 'Сервис временно недоступен. Попробуйте повторить запрос.' : msg, response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError('Не удалось прочитать ответ сервера. Попробуйте повторить запрос.', response.status);
  }
}
