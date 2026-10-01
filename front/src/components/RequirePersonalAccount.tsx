import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { getWebsiteUserStrict, hasTelegramAuth } from "../helpers/auth";
import { PageFeedback } from './PageFeedback';

type RequirePersonalAccountProps = {
  children: ReactElement;
  requireTelegram?: boolean;
};

export function RequirePersonalAccount({
  children,
  requireTelegram = true,
}: RequirePersonalAccountProps) {
  const telegramMiniApp = hasTelegramAuth();
  const [allowed, setAllowed] = useState<boolean | null>(telegramMiniApp ? true : null);
  const location = useLocation();
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (telegramMiniApp) return;
    let active = true;
    setAllowed(null); setError(false);
    void getWebsiteUserStrict().then((user) => {
      if (active) setAllowed(requireTelegram ? Boolean(user?.telegram_id) : Boolean(user));
    }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [requireTelegram, telegramMiniApp, attempt]);

  if (error) return <PageFeedback retry={() => setAttempt(v => v + 1)} />;
  if (allowed === null) return <p role="status">Проверяем аккаунт…</p>;
  return allowed ? children : <Navigate to={`/account?returnPath=${encodeURIComponent(location.pathname + location.search)}&requireTelegram=${requireTelegram ? '1' : '0'}`} replace />;
}
