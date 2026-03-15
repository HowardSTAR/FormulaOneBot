// Точно как в web/app/static/js/common.js — читаем при каждом запросе
function getInitData(): string {
  const tg = typeof window !== 'undefined'
    ? (window as unknown as { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp
    : undefined;
  return tg?.initData ?? '';
}

// VITE_API_URL = полный URL бэкенда, если фронт и API на разных серверах
// BASE_URL = базовый путь, если приложение развёрнуто в подпапке (например /bot/)
const API_BASE = (import.meta.env.VITE_API_URL as string) || '';
const PATH_BASE = ((import.meta.env.BASE_URL as string) || '/').replace(/\/$/, '');
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS || 15000);

export async function apiRequest<T = unknown>(
  endpoint: string,
  params: Record<string, string | number | boolean | undefined> = {},
  method: 'GET' | 'POST' = 'GET'
): Promise<T> {
  const path = (PATH_BASE + endpoint).replace(/\/+/g, '/');
  const url = API_BASE ? new URL(endpoint, API_BASE) : new URL(path, window.location.origin);

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'X-Telegram-Init-Data': getInitData(),
  };

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const options: RequestInit = { method, headers, signal: controller.signal };

  if (method === 'GET') {
    Object.keys(params).forEach((key) => {
      const val = params[key];
      if (val !== null && val !== undefined) {
        url.searchParams.append(key, String(val));
      }
    });
  } else {
    (options as RequestInit & { body?: string }).body = JSON.stringify(params);
  }

  if (import.meta.env.DEV) {
    console.log(`[API] ${method} ${url.toString()}`);
  }

  let response: Response;
  try {
    response = await fetch(url, options);
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') {
      throw new Error('Превышено время ожидания ответа сервера.');
    }
    throw e;
  } finally {
    window.clearTimeout(timeoutId);
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('text/html')) {
    throw new Error(
      'Сервер вернул HTML вместо JSON. Убедитесь, что бэкенд запущен (python run_web.py) и приложение открыто с того же домена.'
    );
  }

  if (!response.ok) {
    const msg = response.status === 401
      ? 'Откройте приложение в Telegram'
      : `Ошибка сервера: ${response.status}`;
    throw new Error(msg);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new Error('Сервер вернул неверный ответ (не JSON). Проверьте, что API доступен.');
  }
}
