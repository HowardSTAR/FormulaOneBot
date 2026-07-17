import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import "../account/AccountPage.css";
import "./ResetPasswordPage.css";

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (password !== confirmation) {
      setError("Пароли не совпадают");
      return;
    }
    setBusy(true);
    try {
      await apiRequest("/api/auth/password/reset", {
        token,
        new_password: password,
        password_confirmation: confirmation,
      }, "POST");
      setComplete(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось изменить пароль");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="account-page reset-password-page">
      <BackButton>← <span>Назад</span></BackButton>
      <header className="account-hero">
        <span>БЕЗОПАСНОСТЬ F1 HUB</span>
        <h1>НОВЫЙ ПАРОЛЬ</h1>
        <p>Придумайте новый пароль для входа в аккаунт.</p>
      </header>
      <section className="account-card account-auth-card reset-password-card">
        {!token ? (
          <div className="reset-password-result">
            <h2>Ссылка неполная</h2>
            <p>В адресе отсутствует токен восстановления. Запросите новое письмо.</p>
            <Link className="account-primary" to="/account">Перейти ко входу</Link>
          </div>
        ) : complete ? (
          <div className="reset-password-result">
            <h2>Пароль изменён</h2>
            <p>Все прежние сеансы завершены. Войдите с новым паролем.</p>
            <Link className="account-primary" to="/account">Войти в аккаунт</Link>
          </div>
        ) : (
          <form onSubmit={submit}>
            <label>Новый пароль<input type="password" autoComplete="new-password" minLength={12} required value={password} onChange={e => setPassword(e.target.value)} /></label>
            <label>Повторите новый пароль<input type="password" autoComplete="new-password" minLength={12} required value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
            <p className="reset-password-hint">Не менее 12 символов, обязательно буквы и цифры.</p>
            <button className="account-primary" disabled={busy || password !== confirmation}>{busy ? "Сохраняем…" : "Сохранить новый пароль"}</button>
          </form>
        )}
        {error && <div className="account-notice error" role="alert">{error}</div>}
      </section>
    </main>
  );
}
