import { useCallback, useEffect, useState } from "react";

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
  role: "user" | "admin" | "superadmin";
  display_name: string | null;
  telegram_username: string | null;
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

export type AuthState = {
  loaded: boolean;
  signedIn: boolean;
  personalized: boolean;
  telegramMiniApp: boolean;
  role: WebsiteUser["role"] | null;
};

export function useAuthState(): AuthState {
  const telegramMiniApp = hasTelegramAuth();
  const [state, setState] = useState<AuthState>(() => ({
    loaded: telegramMiniApp,
    signedIn: telegramMiniApp,
    personalized: telegramMiniApp,
    telegramMiniApp,
    role: null,
  }));

  const refresh = useCallback(() => {
    if (telegramMiniApp) {
      setState({ loaded: true, signedIn: true, personalized: true, telegramMiniApp: true, role: null });
      return;
    }
    void getWebsiteUser().then((user) => {
      setState({
        loaded: true,
        signedIn: Boolean(user),
        personalized: Boolean(user?.telegram_id),
        telegramMiniApp: false,
        role: user?.role ?? null,
      });
    });
  }, [telegramMiniApp]);

  useEffect(() => {
    if (!telegramMiniApp) void getWebsiteUser().then((user) => {
      setState({
        loaded: true,
        signedIn: Boolean(user),
        personalized: Boolean(user?.telegram_id),
        telegramMiniApp: false,
        role: user?.role ?? null,
      });
    });
    window.addEventListener(AUTH_CHANGED_EVENT, refresh);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, refresh);
  }, [refresh, telegramMiniApp]);

  return state;
}
