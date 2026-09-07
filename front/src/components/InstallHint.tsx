import { useEffect, useState } from "react";
import { INSTALL_HINT_KEY, mobilePlatform, shouldShowInstallHint } from "../helpers/installHint";
import "./InstallHint.css";

type InstallEvent = Event & { prompt(): Promise<void>; userChoice: Promise<{ outcome: string }> };
type HintState = { count?: number; lastShown?: number; dismissed?: boolean };
function readState(): HintState {
  try { const value = JSON.parse(localStorage.getItem(INSTALL_HINT_KEY) || "{}"); return value && typeof value === "object" ? value : {}; }
  catch { return { dismissed: true }; }
}
function saveState(state: HintState) { try { localStorage.setItem(INSTALL_HINT_KEY, JSON.stringify(state)); } catch { /* Private browsing. */ } }

export function InstallHint() {
  const [platform, setPlatform] = useState<"ios" | "android" | null>(null);
  const [installEvent, setInstallEvent] = useState<InstallEvent | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const mode = window.matchMedia("(display-mode: standalone)");
    const embedded = (window as unknown as { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp?.initData;
    const installed = () => mode.matches || !!(navigator as Navigator & { standalone?: boolean }).standalone;
    const device = mobilePlatform(navigator.userAgent, navigator.maxTouchPoints);
    if (!device || embedded || installed()) return;
    const before = (event: Event) => { event.preventDefault(); setInstallEvent(event as InstallEvent); };
    const hide = () => { saveState({ ...readState(), dismissed: true }); setPlatform(null); setInstallEvent(null); };
    const modeChanged = () => { if (installed()) hide(); };
    window.addEventListener("beforeinstallprompt", before);
    window.addEventListener("appinstalled", hide);
    mode.addEventListener("change", modeChanged);
    const timer = window.setTimeout(() => {
      const state = readState();
      if (installed() || !shouldShowInstallHint(state, Date.now())) return;
      saveState({ ...state, count: (state.count ?? 0) + 1, lastShown: Date.now() });
      setPlatform(device);
    }, 8000);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("beforeinstallprompt", before);
      window.removeEventListener("appinstalled", hide);
      mode.removeEventListener("change", modeChanged);
    };
  }, []);
  if (!platform) return null;
  const dismiss = (forever: boolean) => {
    saveState({ ...readState(), lastShown: Date.now(), dismissed: forever });
    setPlatform(null);
  };
  const install = async () => {
    if (!installEvent) { setExpanded(true); return; }
    setBusy(true);
    try {
      await installEvent.prompt();
      const choice = await installEvent.userChoice;
      dismiss(choice.outcome === "accepted");
    } catch { setExpanded(true); }
    finally { setInstallEvent(null); setBusy(false); }
  };
  return <aside className="install-hint" aria-label="Установка TurboTears">
    <button className="install-hint-close" aria-label="Напомнить через месяц" onClick={() => dismiss(false)}>×</button>
    <strong>TurboTears на главном экране</strong>
    <p>Открывайте сайт одним нажатием — прямо с иконки на телефоне.</p>
    {expanded && <p className="install-hint-steps">{platform === "ios"
      ? "Откройте сайт в Safari. В меню «Поделиться» выберите «На экран Домой», затем «Добавить». Если пункт скрыт, нажмите «Ещё»."
      : "Откройте сайт в Chrome. В меню ⋮ выберите «Добавить на главный экран» или «Установить приложение» и подтвердите."}</p>}
    <div className="install-hint-actions">
      <button disabled={busy} onClick={install}>{busy ? "Открываем…" : installEvent ? "Установить" : "Как добавить"}</button>
      <button onClick={() => dismiss(true)}>Больше не показывать</button>
    </div>
  </aside>;
}
