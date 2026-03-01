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

export async function apiRequest<T = unknown>(
  endpoint: string,
  params: Record<string, string | number | boolean | undefined> = {},
  method: 'GET' | 'POST' = 'GET'
): Promise<T> {
  const path = (PATH_BASE + endpoint).replace(/\/+/g, '/');
  const url = API_BASE ? new URL(endpoint, API_BASE) : new URL(path, window.location.origin);

  const initData = getInitData();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (initData) {
    headers['X-Telegram-Init-Data'] = initData;
  }

  const options: RequestInit = { method, headers };

  if (method === 'GET') {
    Object.keys(params).forEach((key) => {
      const val = params[key];
      if (val !== null && val !== undefined && typeof val !== 'boolean') {
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
  } catch {
    throw new Error('Не удалось подключиться к серверу. Проверьте интернет-соединение.');
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('text/html')) {
    throw new Error(
      'Сервер вернул HTML вместо JSON. Убедитесь, что бэкенд запущен (python run_web.py) и приложение открыто с того же домена.'
    );
  }

  if (!response.ok) {
    const err = new Error(
      response.status === 401
        ? 'Требуется авторизация через Telegram'
        : `Ошибка сервера: ${response.status}`
    );
    (err as Error & { status: number }).status = response.status;
    throw err;
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new Error('Сервер вернул неверный ответ (не JSON). Проверьте, что API доступен.');
  }
}
