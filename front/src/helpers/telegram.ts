type HapticAPI = {
  selectionChanged?: () => void;
  impactOccurred?: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
  notificationOccurred?: (type: "error" | "success" | "warning") => void;
};

type TelegramWebApp = {
  initData?: string;
  HapticFeedback?: HapticAPI;
  ready?: () => void;
  expand?: () => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
};

function getTelegramWebApp(): TelegramWebApp | undefined {
  return (window as unknown as { Telegram?: { WebApp?: TelegramWebApp } }).Telegram?.WebApp;
}

function getHaptic(): HapticAPI | undefined {
  const telegram = getTelegramWebApp();
  // telegram-web-app.js exposes a compatibility object in regular browsers too.
  // initData is the reliable signal that the page is actually inside Telegram.
  return telegram?.initData ? telegram.HapticFeedback : undefined;
}

/** Лёгкая вибрация при смене выбора (тумблер, переключатель) */
export function hapticSelection(): void {
  getHaptic()?.selectionChanged?.();
}

/** Тактильная отдача при нажатии кнопки */
export function hapticImpact(style: "light" | "medium" | "heavy" = "medium"): void {
  getHaptic()?.impactOccurred?.(style);
}

export function initTelegram(): boolean {
  const tg = getTelegramWebApp();
  if (!tg?.initData) {
    return false;
  }
  try {
    tg.ready?.();
    tg.expand?.();
    const bgColor = "#0b0d12";
    tg.setHeaderColor?.(bgColor);
    tg.setBackgroundColor?.(bgColor);
  } catch (e) {
    console.warn("Telegram WebApp init error", e);
  }
  return true;
}
