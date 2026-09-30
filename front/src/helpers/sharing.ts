import { apiRequest } from './api';

export type ShareOptions = {kind: 'prediction' | 'race' | 'league' | 'recap' | 'history'; season?: number; round?: number; track_id?: string; league_id?: number; history_kind?: string; ids?: string[]; start_year?: number; end_year?: number};
export type ShareCard = {token: string; kind: ShareOptions['kind']; title: string; subtitle: string; headline: string; lines: string[]; cta: string; provisional: boolean; web_url: string; share_url: string; mini_app_url: string | null; image_url: string; expires: number; chart?: unknown};
type SharingTelegram = {initData?: string; initDataUnsafe?: {start_param?: string}; isVersionAtLeast?: (version: string) => boolean; shareMessage?: (id: string, callback?: (sent: boolean) => void) => void; openTelegramLink?: (url: string) => void};
export const sharingTelegram = () => (window as unknown as {Telegram?: {WebApp?: SharingTelegram}}).Telegram?.WebApp;
export const validShareToken = (token: string) => /^[A-Za-z0-9_-]{32}$/.test(token);
const KEY = 'f1hub-pending-invitation';

export function rememberInvitation(token: string): void {
  if (!validShareToken(token)) return;
  try {
    const current = JSON.parse(localStorage.getItem(KEY) || 'null') as {expires: number} | null;
    if (!current || current.expires < Date.now()) localStorage.setItem(KEY, JSON.stringify({token, expires: Date.now() + 30 * 86400000}));
  } catch { /* Invitation still works without storage; attribution is optional. */ }
}
export function pendingInvitation(): string | null {
  try {
    const item = JSON.parse(localStorage.getItem(KEY) || 'null') as {token: string; expires: number} | null;
    return item && item.expires > Date.now() && validShareToken(item.token) ? item.token : null;
  } catch { return null; }
}
export function sharingEvent(token: string, event: 'share_opened' | 'share_sent' | 'share_copied' | 'arrival'): Promise<unknown> {
  return apiRequest('/api/engagement/event', {token, event}, 'POST').catch(() => null);
}
export async function sendCard(card: ShareCard): Promise<'sent' | 'opened' | 'cancelled'> {
  const tg = sharingTelegram();
  if (tg?.initData && tg.shareMessage && tg.isVersionAtLeast?.('8.0')) {
    try {
      const prepared = await apiRequest<{id: string}>(`/api/engagement/shares/${card.token}/telegram`, {}, 'POST', 16000);
      const sent = await new Promise<boolean>(resolve => tg.shareMessage!(prepared.id, resolve));
      if (sent) void sharingEvent(card.token, 'share_sent');
      return sent ? 'sent' : 'cancelled';
    } catch { /* Compatibility fallback: Telegram's ordinary link sharing dialog. */ }
  }
  const url = `https://t.me/share/url?${new URLSearchParams({url: card.share_url, text: `${card.title}\n${card.headline}`})}`;
  if (tg?.initData && tg.openTelegramLink) tg.openTelegramLink(url);
  else window.open(url, '_blank', 'noopener,noreferrer');
  void sharingEvent(card.token, 'share_opened');
  return 'opened';
}
