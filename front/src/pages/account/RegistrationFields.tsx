import { useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { avatarUrl, type Avatar } from '../profile/avatar';

export type RegistrationProfile = {
  display_name: string;
  avatar: Avatar;
  favorite_drivers: string[];
  favorite_teams: string[];
};
type Driver = { code: string; name: string };
type Team = { name: string };
const toggle = (values: string[], value: string) => values.includes(value)
  ? values.filter(item => item !== value) : [...values, value];

export default function RegistrationFields({ value, onChange, disabled }: {
  value: RegistrationProfile; onChange: (value: RegistrationProfile) => void; disabled: boolean;
}) {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true); setError('');
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
        if (!driverData.drivers?.length || !teamData.constructors?.length) setError('Списки пока недоступны. Избранное можно выбрать позже в профиле.');
      } catch {
        if (active) setError('Не удалось загрузить пилотов и команды. Избранное можно выбрать позже в профиле.');
      } finally { if (active) setLoading(false); }
    };
    void load();
    return () => { active = false; };
  }, [attempt]);
  return <fieldset className="registration-profile" disabled={disabled}>
    <legend>Ваш профиль на старте</legend>
    <label>Ник на сайте
      <input name="nickname" autoComplete="nickname" required minLength={2} maxLength={32}
        value={value.display_name} onChange={e => onChange({ ...value, display_name: e.target.value })}
        aria-describedby="registration-nickname-hint" placeholder="Например, TurboPilot" />
    </label>
    <p id="registration-nickname-hint" className="account-hint">От 2 до 32 символов. Этот ник будет виден в играх и прогнозах.</p>
    <details className="registration-avatar">
      <summary><img src={avatarUrl(value.avatar)} alt="Выбранный аватар" width="56" height="56" /><span>Выбрать аватар<small>Шлем, комбинезон и фон</small></span></summary>
      <div className="registration-avatar-options">
        <label>Шлем<select aria-label="Шлем" value={value.avatar.helmet} onChange={e => onChange({ ...value, avatar: { ...value.avatar, helmet: e.target.value } })}>
          <option value="scarlet">Алый / полоса</option><option value="cobalt">Кобальт / двойная полоса</option><option value="mint">Жемчуг / мята</option>
        </select></label>
        <label>Комбинезон<select aria-label="Комбинезон" value={value.avatar.suit} onChange={e => onChange({ ...value, avatar: { ...value.avatar, suit: e.target.value } })}>
          <option value="scarlet">Алый / графит</option><option value="cobalt">Индиго / лайм</option><option value="mint">Графит / мята</option>
        </select></label>
        <label>Фон<select aria-label="Фон" value={value.avatar.background} onChange={e => onChange({ ...value, avatar: { ...value.avatar, background: e.target.value } })}>
          <option value="garage">Ночной бокс</option><option value="scarlet">Красный сектор</option><option value="cobalt">Синий час</option><option value="mint">Полярное сияние</option><option value="gold">Золотой подиум</option>
        </select></label>
      </div>
    </details>
    <details className="registration-favorites">
      <summary>Избранные пилоты и команды · {value.favorite_drivers.length + value.favorite_teams.length}</summary>
      <p className="account-hint">Можно выбрать нескольких или добавить избранное позже.</p>
      {loading && <p role="status">Загружаем пилотов и команды…</p>}
      {error && <div role="status"><p>{error}</p><button type="button" className="account-secondary" onClick={() => setAttempt(n => n + 1)}>Повторить загрузку</button></div>}
      <fieldset className="registration-choices"><legend>Пилоты</legend>{drivers.map(driver => <label key={driver.code}>
        <input type="checkbox" checked={value.favorite_drivers.includes(driver.code)} onChange={() => onChange({ ...value, favorite_drivers: toggle(value.favorite_drivers, driver.code) })} />
        <span>{driver.name} <small>{driver.code}</small></span>
      </label>)}</fieldset>
      <fieldset className="registration-choices"><legend>Команды</legend>{teams.map(team => <label key={team.name}>
        <input type="checkbox" checked={value.favorite_teams.includes(team.name)} onChange={() => onChange({ ...value, favorite_teams: toggle(value.favorite_teams, team.name) })} />
        <span>{team.name}</span>
      </label>)}</fieldset>
    </details>
  </fieldset>;
}
