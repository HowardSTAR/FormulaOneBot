import { useEffect, useRef, useState, type FormEvent } from 'react';
import { apiRequest } from '../../helpers/api';
import { avatarUrl, type Avatar } from '../profile/avatar';
import './registration-wizard.css';

export type RegistrationProfile = {
  display_name: string;
  avatar: Avatar;
  favorite_drivers: string[];
  favorite_teams: string[];
};
type Driver = { code: string; name: string };
type Team = { name: string };
const titles = ['Ваш ник', 'Ваш аватар', 'Избранные пилоты', 'Избранные команды'];
const toggle = (values: string[], value: string) => values.includes(value)
  ? values.filter(item => item !== value) : [...values, value];

export default function RegistrationWizard({ value, onChange, busy, error, onComplete, onClose }: {
  value: RegistrationProfile; onChange: (value: RegistrationProfile) => void; busy: boolean;
  error: string; onComplete: () => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const nickname = useRef<HTMLInputElement>(null);
  const errorNotice = useRef<HTMLParagraphElement>(null);
  const [step, setStep] = useState(0);
  const [nameError, setNameError] = useState('');
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const node = dialog.current;
    const opener = document.activeElement;
    const overflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    node?.showModal();
    return () => {
      node?.close();
      document.documentElement.style.overflow = overflow;
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);
  useEffect(() => {
    dialog.current?.querySelector('.registration-step-body')?.scrollTo(0, 0);
    if (step === 0) nickname.current?.focus({ preventScroll: true });
    else heading.current?.focus({ preventScroll: true });
  }, [step]);
  useEffect(() => { if (error) errorNotice.current?.focus({ preventScroll: true }); }, [error]);
  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true); setLoadError('');
      try {
        const year = new Date().getFullYear();
        let [driverData, teamData] = await Promise.all([
          apiRequest<{ drivers?: Driver[] }>('/api/drivers', { season: year }),
          apiRequest<{ constructors?: Team[] }>('/api/constructors', { season: year }),
        ]);
        if (!driverData.drivers?.length) driverData = await apiRequest('/api/drivers', { season: year - 1 });
        if (!teamData.constructors?.length) teamData = await apiRequest('/api/constructors', { season: year - 1 });
        if (!active) return;
        setDrivers(driverData.drivers || []); setTeams(teamData.constructors || []);
        if (!driverData.drivers?.length || !teamData.constructors?.length) setLoadError('Списки пока недоступны. Избранное можно выбрать позже в профиле.');
      } catch {
        if (active) setLoadError('Не удалось загрузить пилотов и команды. Избранное можно выбрать позже в профиле.');
      } finally { if (active) setLoading(false); }
    };
    void load();
    return () => { active = false; };
  }, [attempt]);

  function next(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (step === 0) {
      const name = value.display_name.trim().replace(/\s+/g, ' ');
      if (name.length < 2 || name.length > 32 || [...name].some(char => char.charCodeAt(0) < 32)) {
        setNameError('Введите ник от 2 до 32 символов.');
        nickname.current?.focus();
        return;
      }
      onChange({ ...value, display_name: name });
      setNameError('');
    }
    if (step < titles.length - 1) setStep(step + 1);
    else onComplete();
  }

  return <dialog ref={dialog} className="registration-wizard" aria-labelledby="registration-step-title" aria-describedby="registration-step-description"
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <form onSubmit={next}>
      <header className="registration-step-header">
        <div><p className="registration-step-counter" aria-live="polite">НАСТРОЙКА ПРОФИЛЯ · ШАГ {step + 1} ИЗ {titles.length}</p>
          <h2 id="registration-step-title" ref={heading} tabIndex={-1}>{titles[step]}</h2></div>
        <button type="button" className="registration-step-close" aria-label="Закрыть настройку профиля" disabled={busy} onClick={onClose}>×</button>
      </header>
      <div className="registration-step-progress" aria-hidden="true">{titles.map((title, index) => <span key={title} data-done={index <= step || undefined} />)}</div>
      <div className="registration-step-body">
        <p id="registration-step-description" className="registration-step-description">{[
          'Этот ник будет виден в играх, прогнозах и вашем профиле.',
          'Соберите образ гонщика. Можно оставить выбранный вариант и изменить его позже.',
          'Выберите любимых пилотов. Можно выбрать нескольких или продолжить без избранного.',
          'Выберите любимые команды. Избранное можно добавить или изменить позже в профиле.',
        ][step]}</p>
        <fieldset className="registration-step-fields" disabled={busy}>
          {step === 0 && <><label>Ник на сайте
            <input ref={nickname} name="nickname" autoComplete="nickname" required minLength={2} maxLength={32}
              value={value.display_name} onChange={e => { onChange({ ...value, display_name: e.target.value }); setNameError(''); }}
              aria-describedby="registration-nickname-hint" aria-invalid={Boolean(nameError)} placeholder="Например, TurboPilot" />
          </label><p id="registration-nickname-hint" className="registration-step-description">От 2 до 32 символов.</p>
            {nameError && <p className="registration-step-error" role="alert">{nameError}</p>}</>}
          {step === 1 && <div className="registration-step-avatar">
            <img src={avatarUrl(value.avatar)} alt="Выбранный аватар" width="160" height="160" />
            <label>Шлем<select aria-label="Шлем" value={value.avatar.helmet} onChange={e => onChange({ ...value, avatar: { ...value.avatar, helmet: e.target.value } })}>
              <option value="scarlet">Алый / полоса</option><option value="cobalt">Кобальт / двойная полоса</option><option value="mint">Жемчуг / мята</option>
            </select></label>
            <label>Комбинезон<select aria-label="Комбинезон" value={value.avatar.suit} onChange={e => onChange({ ...value, avatar: { ...value.avatar, suit: e.target.value } })}>
              <option value="scarlet">Алый / графит</option><option value="cobalt">Индиго / лайм</option><option value="mint">Графит / мята</option>
            </select></label>
            <label>Фон<select aria-label="Фон" value={value.avatar.background} onChange={e => onChange({ ...value, avatar: { ...value.avatar, background: e.target.value } })}>
              <option value="garage">Ночной бокс</option><option value="scarlet">Красный сектор</option><option value="cobalt">Синий час</option><option value="mint">Полярное сияние</option><option value="gold">Золотой подиум</option>
            </select></label>
          </div>}
          {step >= 2 && <>
            {loading && <p role="status">Загружаем пилотов и команды…</p>}
            {loadError && <div role="status"><p>{loadError}</p><button type="button" className="account-secondary" onClick={() => setAttempt(n => n + 1)}>Повторить загрузку</button></div>}
            <fieldset className="registration-step-choices"><legend>Выбрано: {step === 2 ? value.favorite_drivers.length : value.favorite_teams.length}</legend>
              {step === 2 ? drivers.map(driver => <label key={driver.code}>
                <input type="checkbox" checked={value.favorite_drivers.includes(driver.code)} onChange={() => onChange({ ...value, favorite_drivers: toggle(value.favorite_drivers, driver.code) })} />
                <span>{driver.name} <small>{driver.code}</small></span>
              </label>) : teams.map(team => <label key={team.name}>
                <input type="checkbox" checked={value.favorite_teams.includes(team.name)} onChange={() => onChange({ ...value, favorite_teams: toggle(value.favorite_teams, team.name) })} />
                <span>{team.name}</span>
              </label>)}
            </fieldset>
          </>}
        </fieldset>
        {step === 3 && <p className="registration-step-summary">Профиль «{value.display_name}» · Пилоты: {value.favorite_drivers.length} · Команды: {value.favorite_teams.length}. После регистрации откроется профиль со знакомством с сайтом. Код из письма можно ввести там.</p>}
      </div>
      <footer className="registration-step-footer">
        {error && <p ref={errorNotice} tabIndex={-1} className="registration-step-error" role="alert">{error}</p>}
        <div><button type="button" className="account-secondary" disabled={busy} onClick={() => step ? setStep(step - 1) : onClose()}>{step ? 'Назад' : 'К email и паролю'}</button>
          <button className="account-primary" disabled={busy}>{busy ? 'Создаём профиль…' : step === 3 ? 'Создать профиль' : 'Продолжить'}</button></div>
      </footer>
    </form>
  </dialog>;
}
