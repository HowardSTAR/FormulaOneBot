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

let _isTelegram = false;

export function isTelegramWebApp(): boolean {
  return _isTelegram;
}

export function initTelegram(): boolean {
  const tg = (window as unknown as { Telegram?: { WebApp?: { ready?: () => void; expand?: () => void; setHeaderColor?: (c: string) => void; setBackgroundColor?: (c: string) => void; initData?: string } } }).Telegram?.WebApp;
  if (!tg) {
    console.warn("Telegram WebApp недоступен (открыто в браузере?)");
    _isTelegram = false;
    return false;
  }
  _isTelegram = Boolean(tg.initData);
  if (!_isTelegram) {
    console.warn("Telegram SDK загружен, но initData пуст (открыто в браузере)");
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
  return _isTelegram;
}
