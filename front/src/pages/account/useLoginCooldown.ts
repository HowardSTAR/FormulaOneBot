import { useEffect, useState } from 'react';

const storageKey = 'turbotears-login-cooldowns-v1';
type Deadlines = Record<string, number>;

function readDeadlines(): Deadlines {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(storageKey) || '{}');
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    const now = Date.now();
    return Object.fromEntries(Object.entries(value).filter(([, until]) =>
      typeof until === 'number' && Number.isFinite(until) && until > now && until <= now + 86400000));
  } catch { return {}; }
}

export function useLoginCooldown(email: string) {
  const [deadlines, setDeadlines] = useState<Deadlines>(readDeadlines);
  const [now, setNow] = useState(() => Date.now());
  const accountKey = `email:${email.trim().toLowerCase()}`;
  const latest = Math.max(0, ...Object.values(deadlines));
  const seconds = Math.max(0, Math.ceil((Math.max(deadlines[accountKey] || 0, deadlines.all || 0) - now) / 1000));

  useEffect(() => {
    if (!latest) return;
    const refresh = () => {
      const current = Date.now();
      setNow(current);
      if (current >= latest) window.clearInterval(timer);
    };
    const timer = window.setInterval(refresh, 1000);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [latest]);

  const block = (retryAfter: number, scope?: string) => {
    if (!Number.isFinite(retryAfter) || retryAfter <= 0) return;
    const current = Date.now();
    const key = scope === 'ip' || scope === 'global' ? 'all' : accountKey;
    setNow(current);
    setDeadlines(previous => ({ ...previous, [key]: current + Math.min(retryAfter, 86400) * 1000 }));
  };

  useEffect(() => {
    // Only deadlines and email identifiers, never passwords or session tokens.
    try { sessionStorage.setItem(storageKey, JSON.stringify(deadlines)); } catch { /* Server still enforces the limit. */ }
  }, [deadlines]);

  const label = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  return { seconds, label, block };
}
