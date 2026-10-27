import { useState, useEffect, useMemo } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { CustomSelect } from "../../components/CustomSelect";
import { hapticSelection, hapticImpact } from "../../helpers/telegram";
import { visibleInterval } from "../../helpers/visibleInterval";
import { HomeIcon, type HomeIconName } from '../index/HomeIcon';
import { useAuthState } from '../../helpers/auth';
import { SettingsDayClock } from './SettingsDayClock';
import './settings.css';
import { Link, useBlocker } from 'react-router-dom';
import { FIXED_TIMEZONE_OPTIONS, timezoneName } from '../../helpers/presentation';
import { NOTIFY_OPTIONS, selectedIntervals, toggleInterval } from '../../helpers/reminderIntervals';

type SettingsResponse = { timezone?: string; notify_before?: number; notify_before_minutes?: number[]; notifications_enabled?: boolean; reminder_sessions?: number; results_spoiler?: boolean };
const SESSION_OPTIONS = [
  { bit: 1, icon: 'drivers', label: "Свободные заезды", detail: "FP1, FP2 и FP3" },
  { bit: 2, icon: 'quali', label: "Квалификация", detail: "Борьба за стартовую решётку" },
  { bit: 8, icon: 'sprintQuali', label: "Спринт-квалификация", detail: "Стартовая решётка спринта" },
  { bit: 16, icon: 'sprint', label: "Спринт", detail: "Короткая гонка" },
  { bit: 4, icon: 'race', label: "Гонка", detail: "Главная гонка уик-энда" },
] satisfies { bit: number; icon: HomeIconName; label: string; detail: string }[];

function SettingsPage({ embedded = false }: { embedded?: boolean }) {
  const auth = useAuthState();
  const [timezone, setTimezone] = useState("Etc/GMT-3");
  const [notifyBefore, setNotifyBefore] = useState(60);
  const [notifyBeforeMinutes, setNotifyBeforeMinutes] = useState<number[]>([60]);
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [reminderSessions, setReminderSessions] = useState(31);
  const [resultsSpoiler, setResultsSpoiler] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [clockTick, setClockTick] = useState(() => Date.now());
  const [toast, setToast] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState('');
  const [attempt, setAttempt] = useState(0);
  const draft = JSON.stringify({timezone, notify_before: notifyBeforeMinutes[0] ?? notifyBefore, notify_before_minutes: notifyBeforeMinutes, notifications_enabled: notificationsEnabled, reminder_sessions: reminderSessions, results_spoiler: resultsSpoiler});
  const dirty = loaded && draft !== saved;
  const blocker = useBlocker(({currentLocation, nextLocation}) => dirty && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (blocker.state !== 'blocked') return;
    if (window.confirm('Настройки не сохранены. Уйти и потерять изменения?')) blocker.proceed();
    else blocker.reset();
  }, [blocker]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const timePreview = useMemo(() => {
    try {
      const timeString = new Date(clockTick).toLocaleTimeString("ru-RU", {
        timeZone: timezone,
        hour: "2-digit",
        minute: "2-digit",
      });
      return `Сейчас: ${timeString}`;
    } catch {
      return "Сейчас: --:--";
    }
  }, [timezone, clockTick]);

  useEffect(() => {
    return visibleInterval(() => setClockTick(Date.now()), 30_000);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(false), 3000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    let cancelled = false;
    setLoaded(false); setError('');
    apiRequest<SettingsResponse>("/api/account/settings")
      .then((s) => {
        if (cancelled) return;
        if (s?.timezone) setTimezone(s.timezone);
        if (s?.notify_before != null) setNotifyBefore(s.notify_before);
        const intervals = selectedIntervals(s.notify_before_minutes, s.notify_before ?? 60);
        setNotifyBeforeMinutes(intervals);
        if (s?.notifications_enabled !== undefined) setNotificationsEnabled(Boolean(s.notifications_enabled));
        setReminderSessions(s.reminder_sessions ?? 31);
        setResultsSpoiler(Boolean(s.results_spoiler));
        setSaved(JSON.stringify({timezone: s.timezone || 'Etc/GMT-3', notify_before: intervals[0] ?? s.notify_before ?? 60, notify_before_minutes: intervals, notifications_enabled: Boolean(s.notifications_enabled), reminder_sessions: s.reminder_sessions ?? 31, results_spoiler: Boolean(s.results_spoiler)}));
        setLoaded(true);
      })
      .catch(() => { if (!cancelled) setError("Не удалось загрузить настройки. Попробуйте повторить запрос."); });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const saveSettings = async () => {
    if (saving || !loaded || !dirty) return;
    setSaving(true);
    setError("");
    setToast(false);
    try {
      await apiRequest(
        "/api/account/settings",
        JSON.parse(draft),
        "POST"
      );
      setToast(true);
      setSaved(draft);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить настройки");
    } finally {
      setSaving(false);
    }
  };

  const timezoneOptions = useMemo(() => FIXED_TIMEZONE_OPTIONS.some(item => item.value === timezone)
    ? FIXED_TIMEZONE_OPTIONS
    : [...FIXED_TIMEZONE_OPTIONS, { value: timezone, label: timezoneName(timezone) }], [timezone]);
  const timezoneLabel = timezoneOptions.find((item) => item.value === timezone)?.label || timezone;
  const notifyLabel = notifyBeforeMinutes.map(minutes => NOTIFY_OPTIONS.find(item => item.value === minutes)?.label || `${minutes} минут`).join(', ');
  let localMinutes: number | null = null;
  try {
    const parts = new Intl.DateTimeFormat('en', { timeZone: timezone, hour: 'numeric', minute: 'numeric', hourCycle: 'h23' }).formatToParts(new Date(clockTick));
    localMinutes = Number(parts.find(part => part.type === 'hour')?.value) * 60 + Number(parts.find(part => part.type === 'minute')?.value);
  } catch { /* Unknown timezone must not crash settings. */ }
  const quietNow = !notificationsEnabled || localMinutes === null || localMinutes >= 21 * 60 || localMinutes < 10 * 60;

  return (
    <div className="settings-page">
      {!embedded && <BackButton />}
      <header className="settings-header">
        <div>
          <h1>Настройки</h1>
          <p>Время, напоминания и сообщения о гоночном уик-энде.</p>
        </div>
      </header>

      {!loaded && error ? <section className="settings-load-error" role="alert">
        <h2>Настройки не загрузились</h2>
        <p>{error}</p>
        <button type="button" className="settings-retry" onClick={() => setAttempt(value => value + 1)}>Повторить загрузку</button>
      </section> : <form className="settings-layout" onSubmit={event => { event.preventDefault(); hapticImpact('medium'); void saveSettings(); }}>
        <div className="settings-fields" aria-busy={!loaded}>
          {!loaded && <p className="settings-loading" role="status">Загружаем ваши настройки…</p>}
          <section className="settings-panel" aria-labelledby="settings-time-heading">
            <h2 id="settings-time-heading">Время и напоминания</h2>
            <div className="settings-timezone">
              <label htmlFor="settings-timezone">Часовой пояс</label>
              <span className="settings-time-preview"><HomeIcon name="clock" />{loaded ? timePreview : 'Загружаем время…'}</span>
              <CustomSelect id="settings-timezone" ariaLabel="Часовой пояс" options={timezoneOptions} value={timezone} onChange={(v) => setTimezone(String(v))} disabled={!loaded || saving} />
              <p>Задаёт тихие часы и время сообщений в старых клиентах Telegram. Расписание на сайте и в Mini App использует время устройства.</p>
            </div>
            <fieldset className="settings-intervals" disabled={!loaded || saving} aria-describedby="settings-intervals-hint">
              <legend>Уведомлять заранее</legend>
              <p id="settings-intervals-hint">Выберите один или несколько интервалов.</p>
              <div className="settings-interval-grid">
                {NOTIFY_OPTIONS.map(({value, label}) => (
                  <label key={value} className="settings-interval">
                    <input name="notify_before_minutes" value={value} type="checkbox" checked={notifyBeforeMinutes.includes(value)} onChange={() => { hapticSelection(); setNotifyBeforeMinutes(current => toggleInterval(current, value)); }} />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              {loaded && notifyBeforeMinutes.length === 0 && <p role="status">Напоминания о старте выключены. Результаты и другие сообщения остаются без изменений.</p>}
            </fieldset>
            <fieldset className="settings-sessions" disabled={!loaded || saving} aria-describedby="settings-sessions-hint">
              <legend>О каких сессиях напоминать</legend>
              <p id="settings-sessions-hint">Выбор действует в боте и на сайте. Результаты сессий приходят независимо от напоминаний.</p>
              <div className="settings-session-grid">
              {SESSION_OPTIONS.map(({ bit, icon, label, detail }) => (
                <label key={bit} className={`settings-session${bit === 4 ? ' settings-session-race' : ''}`}>
                  <HomeIcon name={icon} />
                  <span><strong>{label}</strong><small>{detail}</small></span>
                  <input name="reminder_sessions" value={bit} type="checkbox" checked={Boolean(reminderSessions & bit)} onChange={() => { hapticSelection(); setReminderSessions((current) => current ^ bit); }} />
                </label>
              ))}
              </div>
              {loaded && reminderSessions === 0 && <p role="status">Напоминания о начале сессий отключены. Остальные уведомления остаются без изменений.</p>}
            </fieldset>
          </section>

          <section className="settings-panel" aria-labelledby="settings-messages-heading">
            <h2 id="settings-messages-heading">Сообщения в Telegram</h2>
            <label className="settings-toggle-row">
              <span><strong id="settings-sound-label">Звук сообщений</strong><small id="settings-sound-hint">Сообщения приходят в обоих режимах. С 21:00 до 10:00 по выбранному поясу звук всегда выключен.</small></span>
              <input name="notifications_enabled" aria-labelledby="settings-sound-label" aria-describedby="settings-sound-hint" className="settings-switch" type="checkbox" role="switch" disabled={!loaded || saving} checked={notificationsEnabled} onChange={(e) => { hapticSelection(); setNotificationsEnabled(e.target.checked); }} />
            </label>
            <label className="settings-toggle-row">
              <span><strong id="settings-spoiler-label">Фото результатов под спойлером</strong><small id="settings-spoiler-hint">Классификация будет скрыта, пока вы не откроете картинку в Telegram.</small></span>
              <input name="results_spoiler" aria-labelledby="settings-spoiler-label" aria-describedby="settings-spoiler-hint" className="settings-switch" type="checkbox" role="switch" disabled={!loaded || saving} checked={resultsSpoiler} onChange={(e) => { hapticSelection(); setResultsSpoiler(e.target.checked); }} />
            </label>
          </section>
          <div className="settings-save">
            <div className="settings-save-feedback">
              {error ? <p className="settings-error" role="alert">{error}</p> : <p role="status">{saving ? 'Сохраняем настройки…' : !loaded ? 'Загрузка настроек…' : dirty ? 'Есть несохранённые изменения' : toast ? 'Настройки сохранены' : 'Все изменения сохранены'}</p>}
            </div>
            <button type="submit" className="settings-save-button" data-analytics-action="settings_save" disabled={saving || !loaded || !dirty}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>
              {saving ? 'Сохранение…' : 'Сохранить настройки'}
            </button>
          </div>
        </div>

        <aside className="settings-summary" aria-labelledby="settings-summary-heading">
          <h2 id="settings-summary-heading">Ваш гоночный день</h2>
          <SettingsDayClock time={timePreview.replace('Сейчас: ', '')} minutes={localMinutes} loaded={loaded} sound={notificationsEnabled} quiet={quietNow} draft={dirty} />
          <p className="settings-summary-state"><span aria-hidden="true" />{!loaded ? 'Загружаем настройки…' : dirty ? 'Предпросмотр изменений' : 'Сохранённые настройки'}</p>
          <dl>
            <div><dt>Часовой пояс</dt><dd>{loaded ? timezoneLabel : '—'}</dd></div>
            <div><dt>Напоминания</dt><dd>{!loaded ? '—' : notifyBeforeMinutes.length && reminderSessions ? `За ${notifyLabel}` : 'Отключены'}</dd></div>
            <div><dt>Сессии</dt><dd>{loaded ? `${SESSION_OPTIONS.filter(({ bit }) => reminderSessions & bit).length} из 5` : '—'}</dd></div>
            <div><dt>Фото результатов</dt><dd>{!loaded ? '—' : resultsSpoiler ? 'Под спойлером' : 'Видны сразу'}</dd></div>
          </dl>
          <p className="settings-sync-note">{auth.personalized ? 'Настройки синхронизируются с вашим ботом Telegram.' : <>Для сообщений в боте <Link to="/account">подключите Telegram в аккаунте</Link>.</>}</p>
          <Link className="settings-push-link" to="/notifications"><HomeIcon name="notifications" /><span><strong>Push на этом устройстве</strong><small>Настраиваются отдельно</small></span><HomeIcon name="chevronRight" /></Link>
        </aside>
      </form>}
    </div>
  );
}

export default SettingsPage;
