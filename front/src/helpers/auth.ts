export function hasTelegramAuth(): boolean {
  const tg = (window as unknown as { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp;
  const initData = tg?.initData ?? "";
  return Boolean(initData && initData.trim().length > 0);
}
