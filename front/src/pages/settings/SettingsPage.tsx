import { useState, useEffect, useMemo } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { CustomSelect } from "../../components/CustomSelect";
import { hapticSelection, hapticImpact } from "../../helpers/telegram";
import { visibleInterval } from "../../helpers/visibleInterval";
import "../../assets/personal-pages.css";
import { Link, useBlocker } from 'react-router-dom';
import { timezoneName } from '../../helpers/presentation';
import { NOTIFY_OPTIONS, selectedIntervals, toggleInterval } from '../../helpers/reminderIntervals';

type SettingsResponse = { timezone?: string; notify_before?: number; notify_before_minutes?: number[]; notifications_enabled?: boolean; reminder_sessions?: number; results_spoiler?: boolean };
const SESSION_OPTIONS = [
  { bit: 1, label: "Свободные заезды", detail: "FP1, FP2 и FP3" },
  { bit: 2, label: "Квалификация", detail: "Борьба за стартовую решётку" },
  { bit: 4, label: "Гонка", detail: "Главная гонка уик-энда" },
  { bit: 8, label: "Спринт-квалификация", detail: "Стартовая решётка спринта" },
  { bit: 16, label: "Спринт", detail: "Короткая гонка" },
];

const TIMEZONES = [
  { value: "Etc/GMT+12", label: "UTC-12 (Паго-Паго, Нуук)" },
  { value: "Etc/GMT+11", label: "UTC-11 (Гонолулу, Папеэте)" },
  { value: "Etc/GMT+10", label: "UTC-10 (Анкоридж, Гамбьер)" },
  { value: "Etc/GMT+9", label: "UTC-9 (Лос-Анджелес, Ванкувер)" },
  { value: "Etc/GMT+8", label: "UTC-8 (Денвер, Эдмонтон)" },
  { value: "Etc/GMT+7", label: "UTC-7 (Мехико, Чикаго)" },
  { value: "Etc/GMT+6", label: "UTC-6 (Нью-Йорк, Оттава)" },
  { value: "Etc/GMT+5", label: "UTC-5 (Каракас, Ла-Пас)" },
  { value: "Etc/GMT+4", label: "UTC-4 (Буэнос-Айрес, Бразилиа)" },
  { value: "Etc/GMT+3", label: "UTC-3 (Фернанду-ди-Норонья, Южная Георгия)" },
  { value: "Etc/GMT+2", label: "UTC-2 (Прая, Понта-Делгада)" },
  { value: "Etc/GMT+1", label: "UTC-1 (Азоры, Кабо-Верде)" },
  { value: "UTC", label: "UTC (GMT) — Лондон, Рейкьявик, Аккра" },
  { value: "Etc/GMT-1", label: "UTC+1 (Париж, Берлин, Рим)" },
  { value: "Etc/GMT-2", label: "UTC+2 (Киев, Афины, Хельсинки)" },
  { value: "Etc/GMT-3", label: "UTC+3 (Москва, Стамбул, Эр-Рияд)" },
  { value: "Etc/GMT-4", label: "UTC+4 (Абу-Даби, Баку, Тбилиси)" },
  { value: "Etc/GMT-5", label: "UTC+5 (Ташкент, Исламабад, Мале)" },
  { value: "Etc/GMT-6", label: "UTC+6 (Астана, Дакка, Бишкек)" },
  { value: "Etc/GMT-7", label: "UTC+7 (Бангкок, Джакарта, Пномпень)" },
  { value: "Etc/GMT-8", label: "UTC+8 (Пекин, Сингапур, Куала-Лумпур)" },
  { value: "Etc/GMT-9", label: "UTC+9 (Токио, Сеул, Пхеньян)" },
  { value: "Etc/GMT-10", label: "UTC+10 (Канберра, Владивосток, Порт-Морсби)" },
  { value: "Etc/GMT-11", label: "UTC+11 (Хониара, Нумеа, Магадан)" },
  { value: "Etc/GMT-12", label: "UTC+12 (Веллингтон, Сува, Тарава)" },
].map(item => ({...item, label: timezoneName(item.value)}));

function SettingsPage() {
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
    setSaving(true);
    setError("");
    try {
      await apiRequest(
        "/api/account/settings",
        JSON.parse(draft),
        "POST"
      );
      setToast(true);
      setSaved(draft);
      setTimeout(() => setToast(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить настройки");
    } finally {
      setSaving(false);
    }
  };

  const timezoneLabel = TIMEZONES.find((item) => item.value === timezone)?.label || timezone;
  const notifyLabel = notifyBeforeMinutes.map(minutes => NOTIFY_OPTIONS.find(item => item.value === minutes)?.label || `${minutes} минут`).join(', ');
  let localHour: number | null = null;
  try { localHour = Number(new Intl.DateTimeFormat('en', {timeZone: timezone, hour: 'numeric', hourCycle: 'h23'}).format(new Date(clockTick))); } catch { /* Unknown timezone must not crash settings. */ }
  const quietNow = !notificationsEnabled || localHour === null || localHour >= 21 || localHour < 10;

  return (
    <div className="personal-page settings-page">
      <BackButton />
      <header className="personal-page-header">
        <div>
          <span className="personal-page-kicker">Персонализация</span>
          <h1>Настройки</h1>
          <p>Управляйте локальным временем и уведомлениями о событиях гоночного уик-энда.</p>
        </div>
        <div className={`personal-status-badge ${notificationsEnabled ? "is-on" : ""}`}>
          <i aria-hidden />{!loaded ? 'Загружаем настройки…' : `${dirty ? 'Предпросмотр: ' : ''}${quietNow ? 'сейчас без звука' : 'сейчас со звуком'}`}
        </div>
      </header>

      <div className="settings-desktop-layout">
        <section className="personal-surface settings-form-panel">
          <div className="settings-section-heading">
            <span>01</span><div><h2>Время событий</h2><p>Расписание будет показано в выбранном часовом поясе.</p></div>
          </div>
          <div className="settings-fields-grid">
            <div className="setting-card">
              <div className="setting-label">Часовой пояс</div>
              <CustomSelect ariaLabel="Часовой пояс" options={TIMEZONES} value={timezone} onChange={(v) => setTimezone(String(v))} disabled={!loaded || saving} />
              <div className="timezone-preview">{timePreview}</div>
            </div>
            <fieldset className="setting-card reminder-intervals" disabled={!loaded || saving} aria-describedby="reminder-intervals-hint">
              <legend className="setting-label">Уведомлять заранее</legend>
              <p id="reminder-intervals-hint" className="setting-card-note">Можно выбрать несколько интервалов — по одному напоминанию в каждый выбранный момент.</p>
              <div className="reminder-interval-grid">
                {NOTIFY_OPTIONS.map(({value, label}) => (
                  <label key={value} className={`reminder-interval ${notifyBeforeMinutes.includes(value) ? 'is-selected' : ''}`}>
                    <input type="checkbox" checked={notifyBeforeMinutes.includes(value)} onChange={() => { hapticSelection(); setNotifyBeforeMinutes(current => toggleInterval(current, value)); }} />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              {notifyBeforeMinutes.length === 0 && <p className="setting-card-note" role="status">Напоминания о старте выключены. Результаты и другие сообщения остаются без изменений.</p>}
            </fieldset>
          </div>

          <div className="settings-section-heading settings-notifications-heading">
            <span>02</span><div><h2>Уведомления</h2><p>Получайте напоминания и не пропускайте старт сессии.</p></div>
          </div>
          <div className="setting-card notification-setting-card">
            <div>
              <strong>Звук сообщений в Telegram: {notificationsEnabled ? "включён" : "без звука"}</strong>
              <p>Сообщения приходят в обоих режимах. Выключенный переключатель отключает только звук. С 21:00 до 10:00 по вашему времени всегда действует тихий режим.</p>
            </div>
            <label className="switch" aria-label="Включить звук сообщений в Telegram">
              <input type="checkbox" disabled={!loaded || saving} checked={notificationsEnabled} onChange={(e) => { hapticSelection(); setNotificationsEnabled(e.target.checked); }} />
              <span className="slider round" />
            </label>
          </div>
          <div className="setting-card notification-setting-card">
            <div>
              <strong>Скрывать фото результатов в Telegram</strong>
              <p>Если включить, картинки с классификацией придут как спойлер. По умолчанию результаты видны сразу.</p>
            </div>
            <label className="switch" aria-label="Скрывать фото результатов в Telegram">
              <input type="checkbox" disabled={!loaded || saving} checked={resultsSpoiler} onChange={(e) => { hapticSelection(); setResultsSpoiler(e.target.checked); }} />
              <span className="slider round" />
            </label>
          </div>
          <fieldset className="session-reminder-options" disabled={!loaded || saving}>
            <legend>О каких сессиях напоминать</legend>
            <p>По умолчанию выбраны все. Выбор действует в боте и на сайте; результаты сессий не меняются. Push включается отдельно в разделе «Уведомления».</p>
            {SESSION_OPTIONS.map(({ bit, label, detail }) => (
              <label key={bit} className={`session-reminder-option ${reminderSessions & bit ? "is-selected" : ""}`}>
                <input type="checkbox" checked={Boolean(reminderSessions & bit)} onChange={() => { hapticSelection(); setReminderSessions((current) => current ^ bit); }} />
                <span><strong>{label}</strong><small>{detail}</small></span>
              </label>
            ))}
            {reminderSessions === 0 && <p role="status">Напоминания о начале сессий отключены. Остальные уведомления остаются без изменений.</p>}
          </fieldset>
        </section>

        <aside className="personal-surface settings-summary-panel">
          <span className="personal-control-label">{!loaded ? 'Загружаем конфигурацию…' : dirty ? 'Предпросмотр · ещё не сохранено' : 'Сохранённая конфигурация'}</span>
          <h2>Ваш гоночный день</h2>
          <dl>
            <div><dt>Локальное время</dt><dd>{timePreview.replace("Сейчас: ", "")}</dd></div>
            <div><dt>Часовой пояс</dt><dd>{timezoneLabel}</dd></div>
            <div><dt>Напоминания</dt><dd>{notifyBeforeMinutes.length && reminderSessions ? `За ${notifyLabel}` : 'Отключены'}</dd></div>
            <div><dt>Звук Telegram</dt><dd>{notificationsEnabled ? "Включён" : "Отключён"}</dd></div>
          </dl>
          <p>Выбрано категорий сессий: {SESSION_OPTIONS.filter(({ bit }) => reminderSessions & bit).length} из 5. Настройки синхронизируются с ботом для связанного аккаунта.</p>
          <Link className="ui-action-link" to="/notifications">Настроить push на этом устройстве →</Link>
        </aside>
      </div>

      <div className="settings-save-bar">
        <div>{error ? <span className="personal-error" role="alert">{error}{!loaded && <button onClick={() => setAttempt(value => value + 1)}>Повторить</button>}</span> : <span role="status">{!loaded ? 'Загрузка настроек…' : dirty ? 'Есть несохранённые изменения' : 'Настройки сохранены'}</span>}</div>
        <button type="button" className="btn-save" disabled={saving || !loaded || !dirty} onClick={() => { hapticImpact("medium"); void saveSettings(); }}>
          {saving ? "Сохранение…" : "Сохранить настройки"}
        </button>
      </div>

      {toast && (
        <div className="toast-msg show" role="status">
          Настройки сохранены ✅
        </div>
      )}
    </div>
  );
}

export default SettingsPage;
