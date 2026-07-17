import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Navigate } from "react-router-dom";
import { getWebsiteUser, hasTelegramAuth } from "../helpers/auth";

export function RequirePersonalAccount({ children }: { children: ReactElement }) {
  const telegramMiniApp = hasTelegramAuth();
  const [allowed, setAllowed] = useState<boolean | null>(telegramMiniApp ? true : null);

  useEffect(() => {
    if (telegramMiniApp) return;
    void getWebsiteUser().then((user) => setAllowed(Boolean(user?.telegram_id)));
  }, [telegramMiniApp]);

  if (allowed === null) return null;
  return allowed ? children : <Navigate to="/account" replace />;
}
