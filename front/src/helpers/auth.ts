import { useEffect, useState } from "react";
import { apiRequest, ApiError, invalidateApiReads } from "./api";
import { SingleFlight } from './singleFlight';

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

export const AUTH_CHANGED_EVENT = "turbotears-auth-changed";
const pendingUser = new SingleFlight();
let identityVersion = 0;

export function getWebsiteUser(): Promise<WebsiteUser | null> {
  return pendingUser.run(String(identityVersion), async () => {
    try {
      const response = await fetch("/api/auth/me", { credentials: "include" });
      if (!response.ok) return null;
      return await response.json() as WebsiteUser;
    } catch {
      return null;
    }
  });
}

/** A failed request is not the same as a signed-out visitor. */
export function getWebsiteUserStrict(): Promise<WebsiteUser | null> {
  return pendingUser.run(`strict:${identityVersion}`, async () => {
    try { return await apiRequest<WebsiteUser>('/api/auth/me'); }
    catch (error) { if (error instanceof ApiError && error.status === 401) return null; throw error; }
  });
}

export function notifyAuthChanged(): void {
  identityVersion += 1;
  pendingUser.clear();
  invalidateApiReads();
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

  useEffect(() => {
    let active = true;
    let generation = 0;
    const refresh = () => {
      const current = ++generation;
      const identity = identityVersion;
      const update = (value: AuthState) => {
        if (active && current === generation && identity === identityVersion) setState(value);
      };
      if (telegramMiniApp) {
        void apiRequest<{ role: "admin" | "superadmin" }>("/api/admin/me")
          .then(({ role }) => update({ loaded: true, signedIn: true, personalized: true, telegramMiniApp: true, role }))
          .catch(() => update({ loaded: true, signedIn: true, personalized: true, telegramMiniApp: true, role: null }));
      } else {
        void getWebsiteUser().then(user => update({
          loaded: true, signedIn: Boolean(user), personalized: Boolean(user?.telegram_id),
          telegramMiniApp: false, role: user?.role ?? null,
        }));
      }
    };
    refresh();
    window.addEventListener(AUTH_CHANGED_EVENT, refresh);
    return () => { active = false; window.removeEventListener(AUTH_CHANGED_EVENT, refresh); };
  }, [telegramMiniApp]);

  return state;
}
