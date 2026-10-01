const personalPaths = new Set(['/favorites', '/settings', '/voting', '/notifications']);
export function safeReturnPath(value: string | null): string | null {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return null;
  try {
    const url = new URL(value, 'https://f1hub.invalid');
    if (url.origin !== 'https://f1hub.invalid' || !personalPaths.has(url.pathname)) return null;
    const query = new URLSearchParams();
    for (const key of ['season', 'round']) {
      const raw = url.searchParams.get(key);
      const number = Number(raw);
      const min = key === 'season' ? 1950 : 1;
      const max = key === 'season' ? new Date().getFullYear() : 40;
      if (raw && Number.isInteger(number) && number >= min && number <= max) query.set(key, String(number));
    }
    return url.pathname + (query.size ? `?${query}` : '');
  }
  catch { return null; }
}
