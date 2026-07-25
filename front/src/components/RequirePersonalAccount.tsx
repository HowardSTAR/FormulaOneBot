import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Navigate } from "react-router-dom";
import { getWebsiteUser, hasTelegramAuth } from "../helpers/auth";

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

  useEffect(() => {
    if (telegramMiniApp) return;
    void getWebsiteUser().then((user) => {
      setAllowed(requireTelegram ? Boolean(user?.telegram_id) : Boolean(user));
    });
  }, [requireTelegram, telegramMiniApp]);

  if (allowed === null) return null;
  return allowed ? children : <Navigate to="/account" replace />;
}
