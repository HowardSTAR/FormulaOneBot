import { useEffect, useRef, useState, type FormEvent } from 'react';
import { apiAssetUrl, apiRequest } from '../../helpers/api';
import { avatarUrl, type Avatar } from '../profile/avatar';
import { avatarSprites, avatarVariants } from '../profile/avatarSprites';
import './registration-wizard.css';

export type RegistrationProfile = {
  display_name: string;
  avatar: Avatar;
  favorite_drivers: string[];
  favorite_teams: string[];
};
type Driver = { code: string; name: string };
type Team = { name: string; constructorId?: string };
const titles = ['Ваш ник', 'Ваш аватар', 'Избранные пилоты', 'Избранные команды'];
const avatarChoices = {
  helmet: { title: 'Шлем', labels: ['Алый / полоса', 'Кобальт / двойная полоса', 'Жемчуг / мята'] },
  suit: { title: 'Комбинезон', labels: ['Алый / графит', 'Индиго / лайм', 'Графит / мята'] },
  background: { title: 'Фон', labels: ['Ночной бокс', 'Красный сектор', 'Синий час', 'Полярное сияние', 'Золотой подиум'] },
};
const toggle = (values: string[], value: string) => values.includes(value)
  ? values.filter(item => item !== value) : [...values, value];

function FavoriteImage({ src, fallback, team = false }: { src: string; fallback: string; team?: boolean }) {
  const [failed, setFailed] = useState(false);
  return <span className={`registration-favorite-image${team ? ' registration-favorite-logo' : ''}`} aria-hidden="true">
    {failed ? <span className="registration-favorite-placeholder">{fallback}</span>
      : <img src={src} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />}
  </span>;
}

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
  const [seasons, setSeasons] = useState({ drivers: new Date().getFullYear(), teams: new Date().getFullYear() });
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
        let driverSeason = year, teamSeason = year;
        let [driverData, teamData] = await Promise.all([
          apiRequest<{ drivers?: Driver[] }>('/api/drivers', { season: year }),
          apiRequest<{ constructors?: Team[] }>('/api/constructors', { season: year }),
        ]);
        if (!driverData.drivers?.length) {
          driverSeason = year - 1;
          driverData = await apiRequest('/api/drivers', { season: driverSeason });
        }
        if (!teamData.constructors?.length) {
          teamSeason = year - 1;
          teamData = await apiRequest('/api/constructors', { season: teamSeason });
        }
        if (!active) return;
        setDrivers(driverData.drivers || []); setTeams(teamData.constructors || []);
        setSeasons({ drivers: driverSeason, teams: teamSeason });
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
            {(['helmet', 'suit', 'background'] as const).map(part => <fieldset key={part}
              className="registration-avatar-options" aria-label={avatarChoices[part].title}>
              <legend>{avatarChoices[part].title}<span>{avatarChoices[part].labels[avatarVariants[part].indexOf(value.avatar[part])]}</span></legend>
              <div className="registration-avatar-grid" data-part={part}>
                {avatarVariants[part].map((id, index) => <label key={id} className="registration-avatar-choice" title={avatarChoices[part].labels[index]}>
                  <input type="radio" name={`avatar-${part}`} value={id} aria-label={avatarChoices[part].labels[index]}
                    checked={value.avatar[part] === id} onChange={() => onChange({ ...value, avatar: { ...value.avatar, [part]: id } })} />
                  <span className="registration-avatar-icon" aria-hidden="true" style={{
                    backgroundImage: `url("${avatarSprites[part]}")`,
                    backgroundSize: `${avatarVariants[part].length * 100}% 100%`,
                    backgroundPosition: `${index * 100 / (avatarVariants[part].length - 1)}% 0`,
                  }} />
                </label>)}
              </div>
            </fieldset>)}
          </div>}
          {step >= 2 && <>
            {loading && <p role="status">Загружаем пилотов и команды…</p>}
            {loadError && <div role="status"><p>{loadError}</p><button type="button" className="account-secondary" onClick={() => setAttempt(n => n + 1)}>Повторить загрузку</button></div>}
            <fieldset className="registration-step-choices"><legend aria-live="polite">Выбрано: {step === 2 ? value.favorite_drivers.length : value.favorite_teams.length}</legend>
              <div className="registration-favorites-grid">{step === 2 ? drivers.map(driver => <label key={`${seasons.drivers}:${driver.code}`}>
                <input type="checkbox" checked={value.favorite_drivers.includes(driver.code)} onChange={() => onChange({ ...value, favorite_drivers: toggle(value.favorite_drivers, driver.code) })} />
                <FavoriteImage src={apiAssetUrl('/api/pilot-portrait', { code: driver.code, name: driver.name, season: seasons.drivers, strict: true, v: 3 })} fallback={driver.code} />
                <span className="registration-favorite-name">{driver.name} <small>{driver.code}</small></span>
              </label>) : teams.map(team => <label key={`${seasons.teams}:${team.name}`}>
                <input type="checkbox" checked={value.favorite_teams.includes(team.name)} onChange={() => onChange({ ...value, favorite_teams: toggle(value.favorite_teams, team.name) })} />
                <FavoriteImage src={apiAssetUrl('/api/team-logo', { team: team.constructorId || team.name, name: team.name, season: seasons.teams })}
                  fallback={team.name.slice(0, 3).toUpperCase()} team />
                <span className="registration-favorite-name">{team.name}</span>
              </label>)}</div>
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
