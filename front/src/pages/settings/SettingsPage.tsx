import { useState, useEffect, useMemo } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { CustomSelect } from "../../components/CustomSelect";
import { hapticSelection, hapticImpact } from "../../helpers/telegram";
import "../../assets/personal-pages.css";

type SettingsResponse = { timezone?: string; notify_before?: number; notifications_enabled?: boolean; reminder_sessions?: number };
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
];
const NOTIFY_OPTIONS = [
  { value: 15, label: "15 минут" },
  { value: 30, label: "30 минут" },
  { value: 60, label: "1 час" },
  { value: 120, label: "2 часа" },
  { value: 1440, label: "24 часа" },
];

function SettingsPage() {
  const [timezone, setTimezone] = useState("Etc/GMT-3");
  const [notifyBefore, setNotifyBefore] = useState(60);
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [reminderSessions, setReminderSessions] = useState(31);
  const [loaded, setLoaded] = useState(false);
  const [clockTick, setClockTick] = useState(() => Date.now());
  const [toast, setToast] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

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
    const id = window.setInterval(() => setClockTick(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiRequest<SettingsResponse>("/api/account/settings")
      .then((s) => {
        if (cancelled) return;
        if (s?.timezone) setTimezone(s.timezone);
        if (s?.notify_before != null) setNotifyBefore(s.notify_before);
        if (s?.notifications_enabled !== undefined) setNotificationsEnabled(Boolean(s.notifications_enabled));
        setReminderSessions(s.reminder_sessions ?? 31);
        setLoaded(true);
      })
      .catch(() => { if (!cancelled) setError("Не удалось загрузить настройки. Обновите страницу."); });
    return () => {
      cancelled = true;
    };
  }, []);

  const saveSettings = async () => {
    setSaving(true);
    setError("");
    try {
      await apiRequest(
        "/api/account/settings",
        { timezone, notify_before: notifyBefore, notifications_enabled: notificationsEnabled, reminder_sessions: reminderSessions },
        "POST"
      );
      setToast(true);
      setTimeout(() => setToast(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить настройки");
    } finally {
      setSaving(false);
    }
  };

  const timezoneLabel = TIMEZONES.find((item) => item.value === timezone)?.label || timezone;
  const notifyLabel = NOTIFY_OPTIONS.find((item) => item.value === notifyBefore)?.label || `${notifyBefore} минут`;

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
          <i aria-hidden />{notificationsEnabled ? "Уведомления бота включены" : "Уведомления бота выключены"}
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
              <CustomSelect options={TIMEZONES} value={timezone} onChange={(v) => setTimezone(String(v))} />
              <div className="timezone-preview">{timePreview}</div>
            </div>
            <div className="setting-card">
              <div className="setting-label">Уведомлять заранее</div>
              <CustomSelect options={NOTIFY_OPTIONS} value={notifyBefore} onChange={(v) => setNotifyBefore(Number(v))} />
              <div className="setting-card-note">Перед началом каждой важной сессии</div>
            </div>
          </div>

          <div className="settings-section-heading settings-notifications-heading">
            <span>02</span><div><h2>Уведомления</h2><p>Получайте напоминания и не пропускайте старт сессии.</p></div>
          </div>
          <div className="setting-card notification-setting-card">
            <div>
              <strong>Уведомления бота</strong>
              <p>С 21:00 до 10:00 по вашему времени сообщения приходят без звука.</p>
            </div>
            <label className="switch" aria-label="Включить уведомления">
              <input type="checkbox" checked={notificationsEnabled} onChange={(e) => { hapticSelection(); setNotificationsEnabled(e.target.checked); }} />
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
          <span className="personal-control-label">Текущая конфигурация</span>
          <h2>Ваш гоночный день</h2>
          <dl>
            <div><dt>Локальное время</dt><dd>{timePreview.replace("Сейчас: ", "")}</dd></div>
            <div><dt>Часовой пояс</dt><dd>{timezoneLabel}</dd></div>
            <div><dt>Напоминание</dt><dd>За {notifyLabel}</dd></div>
            <div><dt>Статус</dt><dd>{notificationsEnabled ? "Активно" : "Отключено"}</dd></div>
          </dl>
          <p>Выбрано категорий сессий: {SESSION_OPTIONS.filter(({ bit }) => reminderSessions & bit).length} из 5. Настройки синхронизируются с ботом для связанного аккаунта.</p>
        </aside>
      </div>

      <div className="settings-save-bar">
        <div>{error ? <span className="personal-error" role="alert">{error}</span> : <span>Изменения применятся на сайте и в боте</span>}</div>
        <button type="button" className="btn-save" disabled={saving || !loaded} onClick={() => { hapticImpact("medium"); void saveSettings(); }}>
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
