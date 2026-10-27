import { SelectField } from '../../components/CustomSelect';
import { useCallback, useEffect, useRef, useState } from "react";
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
import SupporterBadge from '../../components/SupporterBadge';
import { HomeIcon } from '../index/HomeIcon';
import '../index/home-controls.css';

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
  readonly status?: number;
  readonly retryAfter?: number;
  readonly scope?: string;
  constructor(message: string, retryAfter?: number, scope?: string, status?: number) {
    super(message);
    this.retryAfter = retryAfter;
    this.scope = scope;
    this.status = status;
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
      typeof detail === 'object' ? detail?.scope : undefined, response.status);
  }
  if (response.status === 204) return undefined as T;
  try { return await response.json() as T; }
  catch { throw new AuthRequestError('Не удалось прочитать ответ сервера. Попробуйте повторить запрос.'); }
}

export default function AccountPage({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate();
  const [returnParams] = useSearchParams();
  const [user, setUser] = useState<User | null>(null);
  const [accountLoading, setAccountLoading] = useState(true);
  const [accountError, setAccountError] = useState('');
  const [boosty, setBoosty] = useState<BoostyStatus | null>(null);
  const [boostyBusy, setBoostyBusy] = useState(false);
  const [boostyError, setBoostyError] = useState("");
  const [boostyAttempt, setBoostyAttempt] = useState(0);
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
  }, [user, boostyAttempt]);

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
  const deleteForm = useRef<HTMLFormElement>(null);
  const deleteTrigger = useRef<HTMLButtonElement>(null);
  const deletionWasOpen = useRef(false);
  useEffect(() => {
    if (deletePanelOpen) deleteForm.current?.querySelector('input')?.focus();
    else if (deletionWasOpen.current) deleteTrigger.current?.focus();
    deletionWasOpen.current = deletePanelOpen;
  }, [deletePanelOpen]);

  const loadAccount = useCallback(async (signal: AbortSignal) => {
    setAccountLoading(true); setAccountError('');
    try {
      const account = await authFetch<User>("/api/auth/me", { signal });
      if (!signal.aborted) setUser(account);
    } catch (reason) {
      if (signal.aborted) return;
      if (reason instanceof AuthRequestError && reason.status === 401) setUser(null);
      else setAccountError(reason instanceof Error ? reason.message : 'Не удалось загрузить аккаунт. Попробуйте ещё раз.');
    } finally { if (!signal.aborted) setAccountLoading(false); }
  }, []);
  const [accountAttempt, setAccountAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void loadAccount(controller.signal);
    return () => controller.abort();
  }, [loadAccount, accountAttempt]);

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
    if (busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await authFetch("/api/auth/logout", { method: "POST" });
      sessionStorage.removeItem("turbotears_csrf");
      setUser(null); setLinkSession(null); setMode("login");
      setBoosty(null); setBoostyError("");
      notifyAuthChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось выйти. Попробуйте ещё раз.');
    } finally { setBusy(false); }
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
    <main className="account-page" aria-busy={accountLoading}>
      {!embedded && <BackButton>← <span>Главное меню</span></BackButton>}
      <header className="account-hero">
        <h1>Аккаунт</h1>
        <p>{user ? "Вход, Telegram и безопасность вашего TurboTears." : "Войдите, чтобы сохранять прогнозы и свой прогресс. Telegram можно подключить позже."}</p>
      </header>
      {message && <div className="account-notice success" role="status">{message}</div>}
      {error && !registrationOpen && <div className="account-notice error" role="alert">{error}</div>}
      {safeReturnPath(returnParams.get('returnPath')) && <p className="ui-warning">{returnParams.get('requireTelegram') === '1' ? 'Для этого раздела войдите и подключите Telegram. Затем мы вернём вас обратно.' : 'Войдите в аккаунт — затем мы вернём вас в выбранный раздел.'}</p>}

      {accountLoading ? <div className="account-state" role="status">Загружаем аккаунт…</div> : accountError ? (
        <section className="account-state"><h2>Аккаунт недоступен</h2><p role="alert">{accountError}</p><button className="account-secondary" onClick={() => setAccountAttempt(value => value + 1)}>Повторить загрузку</button></section>
      ) : !user ? (
        <section className="account-card account-auth-card" aria-label={mode === 'forgot' ? 'Восстановление пароля' : 'Вход и регистрация'}>
          <div className="account-tabs" role="group" aria-label="Вход или регистрация">
            <button disabled={busy} aria-pressed={mode === "login"} className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(''); setMessage(''); setPasswordError(''); }}>Вход</button>
            <button disabled={busy} aria-pressed={mode === "register"} className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(''); setMessage(''); setPasswordError(''); }}>Регистрация</button>
          </div>
          {mode === 'forgot' && <div className="account-form-intro"><h2>Восстановить пароль</h2><p>Отправим ссылку для сброса на ваш email.</p></div>}
          <form onSubmit={submitAuth}>
            <label>Email<input name="email" type="email" autoComplete="email" autoCapitalize="none" spellCheck={false} disabled={busy} required value={email} onChange={e => setEmail(e.target.value)} /></label>
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
            <h2>Данные для входа</h2>
            <p className="account-identity">{user.email || (user.telegram_id ? "Аккаунт Telegram" : "Аккаунт сайта")}</p>
            {boosty?.premium_active && <span className="account-boosty-badge"><SupporterBadge tierName={boosty.level_name || undefined} />{boosty.premium_override === true ? 'Премиум включён вручную' : `Поддерживает TurboTears · ${boosty.level_name || 'Boosty'}`}</span>}
            <dl><div><dt>Email</dt><dd>{!user.email ? "Не подключён" : user.email_verified ? "Подтверждён" : "Не подтверждён"}</dd></div><div><dt>Telegram</dt><dd>{user.telegram_id ? `ID ${user.telegram_id}` : "Не подключён"}</dd></div></dl>
            {user.email && !user.email_verified && <p><Link to="/profile">Ввести код из письма в профиле →</Link></p>}
            <button className="account-secondary" disabled={busy} onClick={logout}>Выйти из аккаунта</button>
          </section>
          {user.telegram_id ? (
            <section className="account-card account-personal-card">
              <h2>Ваш TurboTears</h2>
              <p>Сохраняйте любимых пилотов и команды, настраивайте часовой пояс и уведомления о событиях.</p>
              <nav className="account-quick-links" aria-label="Персональные разделы">
                <Link to="/favorites"><HomeIcon name="favorite" /><span><strong>Избранное</strong><small>Пилоты и команды</small></span><HomeIcon name="chevronRight" /></Link>
                <Link to="/settings"><HomeIcon name="settings" /><span><strong>Настройки</strong><small>Время и уведомления</small></span><HomeIcon name="chevronRight" /></Link>
              </nav>
            </section>
          ) : (
            <section className="account-card account-link-card">
              <h2>Подключить Telegram</h2>
              <p>Свяжите профиль с ботом для избранного и уведомлений.</p>
              {!linkSession ? (
                <button className="account-primary" onClick={createLink} disabled={busy}>Создать ссылку и QR</button>
              ) : (
                <div className="account-link-session">
                  <img src={linkSession.qr_url} width="132" height="132" alt="QR-код для привязки Telegram" />
                  <div><a className="account-primary" href={linkSession.deep_link} target="_blank" rel="noreferrer">Открыть Telegram</a><small>Ссылка действует 5 минут</small></div>
                </div>
              )}
              <div className="account-divider"><span>или код из бота</span></div>
              <form className="account-code-form" onSubmit={linkByCode}>
                <label>Код из бота<input name="telegram-code" autoComplete="one-time-code" spellCheck={false} inputMode="numeric" pattern="[0-9]{6}" maxLength={6} placeholder="000000" value={manualCode} onChange={e => setManualCode(e.target.value.replace(/\D/g, ""))} /></label>
                <label>Основной профиль<SelectField disabled={busy} value={strategy} onChange={e => setStrategy(e as typeof strategy)} aria-label="Основной профиль">
                  <option value="keep_web">Сохранить профиль сайта</option>
                  <option value="keep_telegram">Сохранить профиль Telegram</option>
                </SelectField></label>
                <button className="account-secondary" disabled={manualCode.length !== 6 || busy}>Привязать</button>
              </form>
              <p className="account-hint">Отправьте команду <code>/link</code> боту и введите полученный код здесь.</p>
            </section>
          )}
          </div>
          <div className="account-details">
          {(boosty?.eligible || boostyError) && (
            <section className="account-card account-boosty-card">
              <div className="account-supporter-art" aria-hidden="true"><SupporterBadge large /></div>
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
                <button className="account-primary" disabled={!boosty?.configured || boosty?.can_check === false || boostyBusy} onClick={() => void checkBoosty()}><span aria-hidden="true"><SupporterBadge /></span>{boostyBusy ? "Проверяем…" : "Проверить подписку"}</button>
              </div>
              {boostyError && <div className="account-notice error"><p role="alert">{boostyError}</p><button className="account-secondary" onClick={() => { setBoostyError(''); setBoostyAttempt(value => value + 1); }}>Повторить загрузку статуса</button></div>}
            </section>
          )}
          {user.email && (
            <section className="account-card account-security-card">
              <div className="account-security-copy">
                <h2>Сменить пароль</h2>
                <p>После сохранения другие активные сеансы будут завершены.</p>
              </div>
              <form onSubmit={changePassword}>
                <PasswordField name="current-password" label="Текущий пароль" autoComplete="current-password" disabled={busy} required value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} />
                <PasswordField name="new-password" racer label="Новый пароль" autoComplete="new-password" disabled={busy} minLength={15} maxLength={128} required value={newPassword} onChange={e => setNewPassword(e.target.value)} />
                <PasswordField name="password-confirmation" label="Повторите новый пароль" autoComplete="new-password" disabled={busy} minLength={15} maxLength={128} required value={passwordConfirmation} onChange={e => setPasswordConfirmation(e.target.value)} />
                <p className="account-hint">От 15 до 128 символов. Выберите уникальную длинную фразу.</p>
                <button className="account-primary" disabled={busy || newPassword !== passwordConfirmation}>Изменить пароль</button>
              </form>
            </section>
          )}
          </div>
          <section className="account-card account-danger-card">
            <div className="account-security-copy">
              <h2>Удалить аккаунт</h2>
              <p>
                Будут удалены профиль, Telegram-привязка, email, сессии, избранное,
                настройки, голоса, прогнозы и персональные игровые данные.
              </p>
              <Link className="ui-action-link" to="/account/delete">Подробнее о процедуре</Link>
            </div>
            {!deletePanelOpen ? (
              <button ref={deleteTrigger} className="account-danger-button" type="button" aria-expanded={deletePanelOpen} onClick={() => setDeletePanelOpen(true)}>
                Перейти к удалению
              </button>
            ) : (
              <form ref={deleteForm} onSubmit={deleteAccount}>
                {user.email && (
                  <PasswordField label="Текущий пароль" autoComplete="current-password" disabled={busy} required value={deletePassword} onChange={e => setDeletePassword(e.target.value)} />
                )}
                <label>
                  Для подтверждения введите DELETE
                  <input name="delete-confirmation" autoComplete="off" spellCheck={false} required value={deleteConfirmation} onChange={e => setDeleteConfirmation(e.target.value.toUpperCase())} />
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
      {registrationOpen && <RegistrationWizard value={registration} onChange={setRegistration} busy={busy} error={error}
        onComplete={() => void createProfile()} onClose={() => { setRegistrationOpen(false); setError(''); }} />}
    </main>
  );
}
