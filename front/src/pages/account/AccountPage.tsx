import { SelectField } from '../../components/CustomSelect';
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { notifyAuthChanged } from "../../helpers/auth";
import { visibleInterval } from "../../helpers/visibleInterval";
import "./AccountPage.css";
import { safeReturnPath } from '../../helpers/returnPath';
import { boostyCheckFailureLabel, boostySubscriptionLabel, type BoostyStatus } from '../../helpers/boosty';
import { checkBoostySubscription } from '../../helpers/boostyApi';
import RegistrationWizard, { type RegistrationProfile } from './RegistrationWizard';
import { defaultAvatar } from '../profile/avatar';
import { PasswordField } from '../../components/PasswordField';
import { useLoginCooldown } from './useLoginCooldown';
import { apiErrorMessage } from '../../helpers/errorMessages';

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

type LinkStatus = { status: "pending" | "approved" | "expired" | "cancelled" | "failed" };

type ApiErrorPayload = { detail?: { message?: string; code?: string; retry_after?: number; scope?: string } | string };

class AuthRequestError extends Error {
  readonly retryAfter?: number;
  readonly scope?: string;
  constructor(message: string, retryAfter?: number, scope?: string) {
    super(message);
    this.retryAfter = retryAfter;
    this.scope = scope;
  }
}

function registrationPasswordError(password: string): string {
  const length = [...password].length;
  if (length < 15) return 'Пароль должен содержать не менее 15 символов.';
  if (length > 128) return 'Пароль должен содержать не более 128 символов.';
  return '';
}

function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split("; ").find(value => value.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

async function authFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const csrf = sessionStorage.getItem("turbotears_csrf") || readCookie("turbotears_csrf");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  let response: Response;
  try { response = await fetch(path, { ...init, headers, credentials: "include" }); }
  catch { throw new AuthRequestError('Нет соединения с сервером. Проверьте сеть и повторите запрос.'); }
  if (!response.ok) {
    let payload: ApiErrorPayload = {};
    try { payload = await response.json() as ApiErrorPayload; } catch { /* no-op */ }
    const detail = payload?.detail;
    throw new AuthRequestError(apiErrorMessage(payload, response.status),
      typeof detail === 'object' ? detail?.retry_after : undefined,
      typeof detail === 'object' ? detail?.scope : undefined);
  }
  if (response.status === 204) return undefined as T;
  try { return await response.json() as T; }
  catch { throw new AuthRequestError('Не удалось прочитать ответ сервера. Попробуйте повторить запрос.'); }
}

export default function AccountPage({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate();
  const [returnParams] = useSearchParams();
  const [user, setUser] = useState<User | null>(null);
  const [boosty, setBoosty] = useState<BoostyStatus | null>(null);
  const [boostyBusy, setBoostyBusy] = useState(false);
  const [boostyError, setBoostyError] = useState("");
  useEffect(() => {
    if (!user) return;
    let active = true;
    const refresh = () => {
      void authFetch<BoostyStatus>("/api/account/boosty").then(value => {
        if (active) { setBoosty(value); setBoostyError(""); }
      }).catch(() => {
        if (active) setBoostyError("Не удалось загрузить статус Boosty");
      });
    };
    refresh();
    const stop = visibleInterval(refresh, 60000);
    return () => { active = false; stop(); };
  }, [user]);

  const checkBoosty = async () => {
    setBoostyBusy(true); setBoostyError("");
    try { setBoosty(await checkBoostySubscription()); }
    catch (reason) { setBoostyError(reason instanceof Error ? reason.message : "Не удалось проверить Boosty"); }
    finally { setBoostyBusy(false); }
  };
  useEffect(() => {
    const path = safeReturnPath(returnParams.get('returnPath'));
    if (user && path && (returnParams.get('requireTelegram') !== '1' || user.telegram_id)) navigate(path, {replace: true});
    if (user && returnParams.get('returnTo') === 'predictions') navigate('/predictions', {replace: true});
    if (user && returnParams.get('returnTo') === 'leagues') navigate(`/predictions?tab=leagues${window.location.hash}`, {replace: true});
    if (user && returnParams.get('returnTo') === 'community') navigate('/community', {replace: true});
  }, [user, returnParams, navigate]);
  const [mode, setMode] = useState<"login" | "register" | "forgot">(() => returnParams.get("mode") === "register" ? "register" : "login");
  const [registration, setRegistration] = useState<RegistrationProfile>({
    display_name: '', avatar: defaultAvatar, favorite_drivers: [], favorite_teams: [],
  });
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [email, setEmail] = useState("");
  const loginCooldown = useLoginCooldown(email);
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState('');
  const [manualCode, setManualCode] = useState("");
  const [strategy, setStrategy] = useState<"keep_web" | "keep_telegram">("keep_web");
  const [linkSession, setLinkSession] = useState<LinkSession | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deletePanelOpen, setDeletePanelOpen] = useState(false);

  useEffect(() => {
    authFetch<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    if (!linkSession) return;
    let active = true;
    let checking = false;

    const checkStatus = async () => {
      if (checking) return;
      checking = true;
      try {
        const result = await authFetch<LinkStatus>(`/api/auth/telegram/link-sessions/${linkSession.token}/status`);
        if (!active) return;
        if (result.status === "approved") {
          const refreshedUser = await authFetch<User>("/api/auth/me");
          if (!active) return;
          setUser(refreshedUser);
          setLinkSession(null);
          notifyAuthChanged();
        } else if (["expired", "cancelled", "failed"].includes(result.status)) {
          setLinkSession(null);
          setError("Ссылка больше не действует. Создайте новую ссылку.");
        }
      } catch {
        // Временная ошибка сети не должна прерывать активную сессию привязки.
      } finally {
        checking = false;
      }
    };

    void checkStatus();
    const stop = visibleInterval(() => void checkStatus(), 2000);
    return () => {
      active = false;
      stop();
    };
  }, [linkSession]);

  const createProfile = async () => {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await authFetch<{ csrf_token: string; user: User; email_sent: boolean }>("/api/auth/register", {
        method: "POST", body: JSON.stringify({ email, password, ...registration }),
      });
      sessionStorage.setItem("turbotears_csrf", result.csrf_token);
      setPassword('');
      notifyAuthChanged();
      navigate('/profile', { replace: true, state: { registered: true, emailSent: result.email_sent } });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось создать профиль. Попробуйте ещё раз.');
    } finally { setBusy(false); }
  };

  const submitAuth = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || (mode === 'login' && loginCooldown.seconds > 0)) return;
    setError(""); setMessage("");
    if (mode === 'register') {
      const validation = registrationPasswordError(password);
      setPasswordError(validation);
      if (validation) {
        event.currentTarget.querySelector<HTMLInputElement>('input[name="password"]')?.focus();
        return;
      }
      setRegistrationOpen(true);
      return;
    }
    setBusy(true);
    try {
      if (mode === "forgot") {
        const result = await authFetch<{ message: string }>("/api/auth/password/forgot", {
          method: "POST", body: JSON.stringify({ email }),
        });
        setMessage(result.message);
      } else {
        const result = await authFetch<{ csrf_token: string; user: User }>("/api/auth/login", {
          method: "POST", body: JSON.stringify({ email, password }),
        });
        sessionStorage.setItem("turbotears_csrf", result.csrf_token);
        notifyAuthChanged();
        if (!result.user.email_verified) { navigate('/profile', { replace: true }); return; }
        setUser(result.user);
      }
    } catch (reason) {
      if (mode === 'login' && reason instanceof AuthRequestError && reason.retryAfter) {
        loginCooldown.block(reason.retryAfter, reason.scope);
        setError('');
      } else setError(reason instanceof Error ? reason.message : "Не удалось выполнить запрос");
    } finally { setBusy(false); }
  };

  const changePassword = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await authFetch<{ message: string }>("/api/auth/password/change", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          password_confirmation: passwordConfirmation,
        }),
      });
      setCurrentPassword(""); setNewPassword(""); setPasswordConfirmation("");
      setMessage(result.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось изменить пароль");
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
      setLinkSession(null);
      notifyAuthChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось привязать Telegram");
    } finally { setBusy(false); }
  };

  const logout = async () => {
    await authFetch("/api/auth/logout", { method: "POST" });
    sessionStorage.removeItem("turbotears_csrf");
    setUser(null); setLinkSession(null); setMode("login");
    setBoosty(null); setBoostyError("");
    notifyAuthChanged();
  };

  const deleteAccount = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      await authFetch<void>("/api/auth/account", {
        method: "DELETE",
        body: JSON.stringify({
          confirmation: deleteConfirmation,
          current_password: deletePassword || null,
        }),
      });
      sessionStorage.removeItem("turbotears_csrf");
      setUser(null); setLinkSession(null); setMode("login");
      setBoosty(null); setBoostyError("");
      setDeletePassword(""); setDeleteConfirmation(""); setDeletePanelOpen(false);
      setMessage("Аккаунт и связанные персональные данные удалены.");
      notifyAuthChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось удалить аккаунт");
    } finally { setBusy(false); }
  };

  return (
    <main className="account-page">
      {!embedded && <BackButton>← <span>Главное меню</span></BackButton>}
      <header className="account-hero">
        <span>ЛИЧНЫЙ РАЗДЕЛ TURBOTEARS</span>
        <h1>{user?.telegram_id ? "АККАУНТ" : "АККАУНТ И TELEGRAM"}</h1>
        <p>{user?.telegram_id
          ? "Управляйте входом, привязкой Telegram и подпиской."
          : "Email используется для безопасного входа. Telegram подключается отдельно через бота."}</p>
      </header>
      {safeReturnPath(returnParams.get('returnPath')) && <p className="ui-warning">{returnParams.get('requireTelegram') === '1' ? 'Для этого раздела войдите и подключите Telegram. Затем мы вернём вас обратно.' : 'Войдите в аккаунт — затем мы вернём вас в выбранный раздел.'}</p>}

      {!user ? (
        <section className="account-card account-auth-card">
          <div className="account-tabs">
            <button disabled={busy} className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(''); setMessage(''); setPasswordError(''); }}>Вход</button>
            <button disabled={busy} className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(''); setMessage(''); setPasswordError(''); }}>Регистрация</button>
          </div>
          <form onSubmit={submitAuth}>
            <label>Email<input type="email" autoComplete="email" disabled={busy} required value={email} onChange={e => setEmail(e.target.value)} /></label>
            {mode !== "forgot" && (
              <PasswordField racer key={mode} name="password" label="Пароль" autoComplete={mode === 'register' ? 'new-password' : 'current-password'} disabled={busy} minLength={mode === "register" ? 15 : undefined} maxLength={128} required value={password}
                aria-invalid={mode === 'register' && Boolean(passwordError)}
                aria-describedby={mode === 'register' ? `registration-password-hint${passwordError ? ' registration-password-error' : ''}` : undefined}
                onBlur={() => { if (mode === 'register') setPasswordError(registrationPasswordError(password)); }}
                onInvalid={event => { if (mode === 'register') setPasswordError(registrationPasswordError(event.currentTarget.value)); }}
                onChange={event => {
                  setPassword(event.target.value);
                  if (mode === 'register' && passwordError) setPasswordError(registrationPasswordError(event.target.value));
                }} />
            )}
            {mode === 'register' && <>
              {passwordError && <p id="registration-password-error" className="account-password-error" role="alert">{passwordError}</p>}
              <p id="registration-password-hint" className="account-hint">Пароль: от 15 до 128 символов. Используйте уникальную длинную фразу; можно с пробелами и кириллицей.</p><p className="account-hint">Далее — ник, аватар, любимые пилоты и команды. Каждый шаг откроется в отдельном окне.</p></>}
            {mode === "login" && (
              <button type="button" className="account-text-button" onClick={() => { setMode("forgot"); setError(""); setMessage(""); }}>
                Забыли пароль?
              </button>
            )}
            {mode === 'login' && loginCooldown.seconds > 0 && <p className="account-hint" role="status">Вход временно заблокирован. Повторите через {loginCooldown.label}. Можно восстановить пароль по email.</p>}
            <button className="account-primary" disabled={busy || (mode === 'login' && loginCooldown.seconds > 0)}>{busy ? "Подождите…" : mode === "login" ? loginCooldown.seconds > 0 ? `Войти через ${loginCooldown.label}` : "Войти" : mode === "register" ? "Продолжить регистрацию" : "Отправить ссылку"}</button>
            {mode === "forgot" && (
              <button type="button" className="account-text-button account-text-button-center" onClick={() => setMode("login")}>
                Вернуться ко входу
              </button>
            )}
          </form>
        </section>
      ) : (
        <div className="account-grid">
          <div className="account-overview">
          <section className="account-card account-profile-card">
            <span className="account-kicker">ТЕКУЩИЙ ПРОФИЛЬ</span>
            <h2>{user.email || "Аккаунт Telegram"}</h2>
            {!embedded && <p><Link to="/profile">Мой профиль · рекорды и прогнозы →</Link></p>}
            {boosty?.premium_active && <span className="account-boosty-badge">{boosty.premium_override === true ? 'Премиум · включён вручную' : `Поддерживает TurboTears · ${boosty.level_name || 'Boosty'}`}</span>}
            <dl><div><dt>Email</dt><dd>{!user.email ? "Не подключён" : user.email_verified ? "Подтверждён" : "Не подтверждён"}</dd></div><div><dt>Telegram</dt><dd>{user.telegram_id ? `ID ${user.telegram_id}` : "Не подключён"}</dd></div></dl>
            {user.email && !user.email_verified && <p><Link to="/profile">Ввести код из письма в профиле →</Link></p>}
            <button className="account-secondary" onClick={logout}>Выйти</button>
          </section>
          {user.telegram_id ? (
            <section className="account-card account-personal-card">
              <span className="account-kicker">ПЕРСОНАЛИЗАЦИЯ</span>
              <h2>Ваш TurboTears</h2>
              <p>Сохраняйте любимых пилотов и команды, настраивайте часовой пояс и уведомления о событиях.</p>
              <nav className="account-quick-links" aria-label="Персональные разделы">
                <Link to="/favorites"><strong>Избранное</strong><span>Пилоты и команды</span><b aria-hidden>→</b></Link>
                <Link to="/settings"><strong>Настройки</strong><span>Время и уведомления</span><b aria-hidden>→</b></Link>
              </nav>
            </section>
          ) : (
            <section className="account-card account-link-card">
              <span className="account-kicker">СВЯЗАТЬ АККАУНТЫ</span>
              <h2>Подключить Telegram</h2>
              {!linkSession ? (
                <button className="account-primary" onClick={createLink} disabled={busy}>Создать ссылку и QR</button>
              ) : (
                <div className="account-link-session">
                  <img src={linkSession.qr_url} alt="QR-код для привязки Telegram" />
                  <div><a className="account-primary" href={linkSession.deep_link} target="_blank" rel="noreferrer">Открыть Telegram</a><small>Ссылка действует 5 минут</small></div>
                </div>
              )}
              <div className="account-divider"><span>или код из бота</span></div>
              <form className="account-code-form" onSubmit={linkByCode}>
                <input aria-label="Шестизначный код" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} placeholder="000000" value={manualCode} onChange={e => setManualCode(e.target.value.replace(/\D/g, ""))} />
                <SelectField value={strategy} onChange={e => setStrategy(e as typeof strategy)} aria-label="Основной профиль">
                  <option value="keep_web">Сохранить профиль сайта</option>
                  <option value="keep_telegram">Сохранить профиль Telegram</option>
                </SelectField>
                <button className="account-secondary" disabled={manualCode.length !== 6 || busy}>Привязать</button>
              </form>
              <p className="account-hint">Отправьте команду <code>/link</code> боту и введите полученный код здесь.</p>
            </section>
          )}
          </div>
          <div className="account-details">
          {(boosty?.eligible || boostyError) && (
            <section className="account-card account-boosty-card">
              <span className="account-kicker">ПОДДЕРЖКА ПРОЕКТА</span>
              <h2>Подписка Boosty</h2>
              <p>Для проверки используйте одинаковый подтверждённый email на сайте и в Boosty.</p>
              <p role="status">{!boosty ? "Статус недоступен" : !boosty.configured
                ? "Подключение проверки готовится"
                : boostySubscriptionLabel(boosty)}</p>
              {boosty?.checked_at && <p className="account-hint">Последняя проверка: {new Date(boosty.checked_at * 1000).toLocaleString("ru-RU")}</p>}
              {boosty?.check_unavailable_reason && <p className="account-hint">{boosty.check_unavailable_reason}</p>}
              {boosty?.check_failed && <p role="alert">{boostyCheckFailureLabel(boosty)}</p>}
              <div className="account-boosty-actions">
                <a className="account-secondary" href={boosty?.blog_url || "https://boosty.to/turbotears"} target="_blank" rel="noopener noreferrer">Открыть Boosty</a>
                <button className="account-primary" disabled={!boosty?.configured || boosty?.can_check === false || boostyBusy} onClick={() => void checkBoosty()}>{boostyBusy ? "Проверяем…" : "Проверить подписку"}</button>
              </div>
              {boostyError && <p role="alert" className="account-notice error">{boostyError}</p>}
            </section>
          )}
          {user.email && (
            <section className="account-card account-security-card">
              <div className="account-security-copy">
                <span className="account-kicker">БЕЗОПАСНОСТЬ</span>
                <h2>Сменить пароль</h2>
                <p>После сохранения другие активные сеансы будут завершены.</p>
              </div>
              <form onSubmit={changePassword}>
                <PasswordField label="Текущий пароль" autoComplete="current-password" disabled={busy} required value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} />
                <PasswordField racer label="Новый пароль" autoComplete="new-password" disabled={busy} minLength={15} maxLength={128} required value={newPassword} onChange={e => setNewPassword(e.target.value)} />
                <PasswordField label="Повторите новый пароль" autoComplete="new-password" disabled={busy} minLength={15} maxLength={128} required value={passwordConfirmation} onChange={e => setPasswordConfirmation(e.target.value)} />
                <p className="account-hint">От 15 до 128 символов. Выберите уникальную длинную фразу.</p>
                <button className="account-primary" disabled={busy || newPassword !== passwordConfirmation}>Изменить пароль</button>
              </form>
            </section>
          )}
          </div>
          <section className="account-card account-danger-card">
            <div className="account-security-copy">
              <span className="account-kicker">УДАЛЕНИЕ ДАННЫХ</span>
              <h2>Удалить аккаунт</h2>
              <p>
                Будут удалены профиль, Telegram-привязка, email, сессии, избранное,
                настройки, голоса, прогнозы и персональные игровые данные.
              </p>
              <Link className="ui-action-link" to="/account/delete">Подробнее о процедуре</Link>
            </div>
            {!deletePanelOpen ? (
              <button className="account-danger-button" type="button" onClick={() => setDeletePanelOpen(true)}>
                Перейти к удалению
              </button>
            ) : (
              <form onSubmit={deleteAccount}>
                {user.email && (
                  <PasswordField label="Текущий пароль" autoComplete="current-password" disabled={busy} required value={deletePassword} onChange={e => setDeletePassword(e.target.value)} />
                )}
                <label>
                  Для подтверждения введите DELETE
                  <input required value={deleteConfirmation} onChange={e => setDeleteConfirmation(e.target.value.toUpperCase())} />
                </label>
                <div className="account-danger-actions">
                  <button className="account-secondary" type="button" onClick={() => { setDeletePanelOpen(false); setDeletePassword(""); setDeleteConfirmation(""); }}>
                    Отмена
                  </button>
                  <button className="account-danger-button" disabled={busy || deleteConfirmation !== "DELETE"}>
                    Удалить безвозвратно
                  </button>
                </div>
              </form>
            )}
          </section>
        </div>
      )}
      {message && <div className="account-notice success">{message}</div>}
      {error && !registrationOpen && <div className="account-notice error">{error}</div>}
      {registrationOpen && <RegistrationWizard value={registration} onChange={setRegistration} busy={busy} error={error}
        onComplete={() => void createProfile()} onClose={() => { setRegistrationOpen(false); setError(''); }} />}
    </main>
  );
}
