export function hasTelegramAuth(): boolean {
  const tg = (window as unknown as { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp;
  const initData = tg?.initData ?? "";
  return Boolean(initData && initData.trim().length > 0);
}

export type WebsiteUser = {
  id: number;
  email: string | null;
  telegram_id: number | null;
  email_verified: boolean;
};

export const AUTH_CHANGED_EVENT = "f1hub-auth-changed";

export async function getWebsiteUser(): Promise<WebsiteUser | null> {
  try {
    const response = await fetch("/api/auth/me", { credentials: "include" });
    if (!response.ok) return null;
    return await response.json() as WebsiteUser;
  } catch {
    return null;
  }
}

export function notifyAuthChanged(): void {
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}
