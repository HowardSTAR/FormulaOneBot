type HapticAPI = {
  selectionChanged?: () => void;
  impactOccurred?: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
  notificationOccurred?: (type: "error" | "success" | "warning") => void;
};

function getHaptic(): HapticAPI | undefined {
  return (window as unknown as { Telegram?: { WebApp?: { HapticFeedback?: HapticAPI } } }).Telegram?.WebApp?.HapticFeedback;
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
  const tg = (window as unknown as { Telegram?: { WebApp?: { ready?: () => void; expand?: () => void; setHeaderColor?: (c: string) => void; setBackgroundColor?: (c: string) => void } } }).Telegram?.WebApp;
  if (!tg) {
    console.warn("Telegram WebApp недоступен (открыто в браузере?)");
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
