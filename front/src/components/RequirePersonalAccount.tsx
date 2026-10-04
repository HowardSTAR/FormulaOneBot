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
  const location = useLocation();
  const [attempt, setAttempt] = useState(0);
  const requestKey = `${attempt}:${requireTelegram}`;
  const [result, setResult] = useState<{ key: string; status: "allowed" | "denied" | "error" } | null>(null);
  const status = telegramMiniApp ? "allowed" : result?.key === requestKey ? result.status : "loading";

  useEffect(() => {
    if (telegramMiniApp) return;
    let active = true;
    void getWebsiteUserStrict().then((user) => {
      if (active) setResult({ key: requestKey, status: (requireTelegram ? Boolean(user?.telegram_id) : Boolean(user)) ? "allowed" : "denied" });
    }).catch(() => { if (active) setResult({ key: requestKey, status: "error" }); });
    return () => { active = false; };
  }, [requireTelegram, telegramMiniApp, requestKey]);

  if (status === "error") return <PageFeedback retry={() => setAttempt(v => v + 1)} />;
  if (status === "loading") return <p role="status">Проверяем аккаунт…</p>;
  return status === "allowed" ? children : <Navigate to={`/account?returnPath=${encodeURIComponent(location.pathname + location.search)}&requireTelegram=${requireTelegram ? '1' : '0'}`} replace />;
}
