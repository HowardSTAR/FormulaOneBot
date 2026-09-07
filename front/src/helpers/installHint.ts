export const INSTALL_HINT_KEY = "turbotears-install-hint-v2";
export function mobilePlatform(userAgent: string, maxTouchPoints: number): "ios" | "android" | null {
  if (/iPhone|iPad|iPod/i.test(userAgent) || (/Macintosh/i.test(userAgent) && maxTouchPoints > 1)) return "ios";
  return /Android/i.test(userAgent) ? "android" : null;
}
export function shouldShowInstallHint(state: { count?: number; lastShown?: number; dismissed?: boolean }, now: number) {
  return !state.dismissed && (state.count ?? 0) < 3 && (!state.lastShown || now - state.lastShown >= 30 * 86400000);
}
