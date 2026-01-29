const getInitData = (): string => {
  const tg = (window as unknown as { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp;
  return tg?.initData ?? '';
};

export async function apiRequest<T = unknown>(
  endpoint: string,
  params: Record<string, string | number | undefined> = {},
  method: 'GET' | 'POST' = 'GET'
): Promise<T> {
  const url = new URL(`${import.meta.env.VITE_API_URL}${endpoint}`, window.location.origin);
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'X-Telegram-Init-Data': getInitData(),
  };
  const options: RequestInit = { method, headers };

  if (method === 'GET') {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        url.searchParams.append(key, String(value));
      }
    });
  } else {
    (options as RequestInit & { body?: string }).body = JSON.stringify(params);
  }

  const response = await fetch(url.toString(), options);
  if (!response.ok) {
    throw new Error(`Server Error: ${response.status}`);
  }
  return response.json() as Promise<T>;
}
