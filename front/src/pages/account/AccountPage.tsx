import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { BackButton } from "../../components/BackButton";
import "./AccountPage.css";

type User = {
  id: number;
  email: string | null;
  telegram_id: number | null;
  email_verified: boolean;
};

type LinkSession = {
  token: string;
  short_code: string;
  expires_at: string;
  deep_link: string;
  qr_url: string;
};

type ApiErrorPayload = { detail?: { message?: string; code?: string } | string };

function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split("; ").find(value => value.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

async function authFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const csrf = sessionStorage.getItem("f1hub_csrf") || readCookie("f1hub_csrf");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(path, { ...init, headers, credentials: "include" });
  if (!response.ok) {
    let payload: ApiErrorPayload = {};
    try { payload = await response.json() as ApiErrorPayload; } catch { /* no-op */ }
    const detail = payload.detail;
    const message = typeof detail === "string" ? detail : detail?.message;
    throw new Error(message || `Ошибка API: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export default function AccountPage() {
  const [user, setUser] = useState<User | null>(null);
  const [mode, setMode] = useState<"login" | "register" | "verify">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [manualCode, setManualCode] = useState("");
  const [strategy, setStrategy] = useState<"keep_web" | "keep_telegram">("keep_web");
  const [linkSession, setLinkSession] = useState<LinkSession | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    authFetch<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  const submitAuth = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      if (mode === "register") {
        await authFetch("/api/auth/register", {
          method: "POST", body: JSON.stringify({ email, password }),
        });
        setMode("verify");
        setMessage("Код отправлен на email. Он действует 10 минут.");
      } else if (mode === "verify") {
        const result = await authFetch<{ csrf_token: string; user: User }>("/api/auth/verify-email", {
          method: "POST", body: JSON.stringify({ email, code }),
        });
        sessionStorage.setItem("f1hub_csrf", result.csrf_token);
        setUser(result.user);
      } else {
        const result = await authFetch<{ csrf_token: string; user: User }>("/api/auth/login", {
          method: "POST", body: JSON.stringify({ email, password }),
        });
        sessionStorage.setItem("f1hub_csrf", result.csrf_token);
        setUser(result.user);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось выполнить запрос");
    } finally { setBusy(false); }
  };

  const createLink = async () => {
    setBusy(true); setError(""); setMessage("");
    try {
      setLinkSession(await authFetch<LinkSession>("/api/auth/telegram/link-sessions", { method: "POST" }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать ссылку");
    } finally { setBusy(false); }
  };

  const linkByCode = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const result = await authFetch<{ user: User }>("/api/auth/telegram/link-by-code", {
        method: "POST", body: JSON.stringify({ code: manualCode, strategy }),
      });
      setUser(result.user);
      setMessage("Telegram успешно привязан.");
      setLinkSession(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось привязать Telegram");
    } finally { setBusy(false); }
  };

  const logout = async () => {
    await authFetch("/api/auth/logout", { method: "POST" });
    sessionStorage.removeItem("f1hub_csrf");
    setUser(null); setLinkSession(null); setMode("login");
  };

  return (
    <main className="account-page">
      <BackButton>← <span>Главное меню</span></BackButton>
      <header className="account-hero">
        <span>ПРОФИЛЬ F1 HUB</span>
        <h1>АККАУНТ И TELEGRAM</h1>
        <p>Email используется для безопасного входа. Telegram подключается отдельно через бота.</p>
      </header>

      {!user ? (
        <section className="account-card account-auth-card">
          <div className="account-tabs">
            <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Вход</button>
            <button className={mode !== "login" ? "active" : ""} onClick={() => setMode("register")}>Регистрация</button>
          </div>
          <form onSubmit={submitAuth}>
            <label>Email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
            {mode !== "verify" && (
              <label>Пароль<input type="password" minLength={12} required value={password} onChange={e => setPassword(e.target.value)} /></label>
            )}
            {mode === "verify" && (
              <label>Код из письма<input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ""))} /></label>
            )}
            <button className="account-primary" disabled={busy}>{busy ? "Подождите…" : mode === "login" ? "Войти" : mode === "register" ? "Получить код" : "Подтвердить email"}</button>
          </form>
        </section>
      ) : (
        <div className="account-grid">
          <section className="account-card account-profile-card">
            <span className="account-kicker">ТЕКУЩИЙ ПРОФИЛЬ</span>
            <h2>{user.email}</h2>
            <dl><div><dt>Email</dt><dd>Подтверждён</dd></div><div><dt>Telegram</dt><dd>{user.telegram_id ? `ID ${user.telegram_id}` : "Не подключён"}</dd></div></dl>
            <button className="account-secondary" onClick={logout}>Выйти</button>
          </section>
          <section className="account-card account-link-card">
            <span className="account-kicker">СВЯЗАТЬ АККАУНТЫ</span>
            <h2>Подключить Telegram</h2>
            {!linkSession ? (
              <button className="account-primary" onClick={createLink} disabled={busy || Boolean(user.telegram_id)}>Создать ссылку и QR</button>
            ) : (
              <div className="account-link-session">
                <img src={linkSession.qr_url} alt="QR-код для привязки Telegram" />
                <div><a className="account-primary" href={linkSession.deep_link} target="_blank" rel="noreferrer">Открыть Telegram</a><small>Ссылка действует 5 минут</small></div>
              </div>
            )}
            <div className="account-divider"><span>или код из бота</span></div>
            <form className="account-code-form" onSubmit={linkByCode}>
              <input aria-label="Шестизначный код" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} placeholder="000000" value={manualCode} onChange={e => setManualCode(e.target.value.replace(/\D/g, ""))} />
              <select value={strategy} onChange={e => setStrategy(e.target.value as typeof strategy)} aria-label="Основной профиль">
                <option value="keep_web">Сохранить профиль сайта</option>
                <option value="keep_telegram">Сохранить профиль Telegram</option>
              </select>
              <button className="account-secondary" disabled={manualCode.length !== 6 || busy}>Привязать</button>
            </form>
            <p className="account-hint">Отправьте команду <code>/link</code> боту и введите полученный код здесь.</p>
          </section>
        </div>
      )}
      {message && <div className="account-notice success">{message}</div>}
      {error && <div className="account-notice error">{error}</div>}
    </main>
  );
}
