import { useState, useEffect, useCallback } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { CustomSelect } from "../../components/CustomSelect";
import { hapticSelection, hapticImpact } from "../../helpers/telegram";

type SettingsResponse = { timezone?: string; notify_before?: number; notifications_enabled?: boolean };

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
  const [timePreview, setTimePreview] = useState("--:--");
  const [toast, setToast] = useState(false);

  const updateTimePreview = useCallback(() => {
    try {
      const tz = timezone;
      const timeString = new Date().toLocaleTimeString("ru-RU", {
        timeZone: tz,
        hour: "2-digit",
        minute: "2-digit",
      });
      setTimePreview(`Сейчас: ${timeString}`);
    } catch {
      setTimePreview("Сейчас: --:--");
    }
  }, [timezone]);

  useEffect(() => {
    updateTimePreview();
    const id = setInterval(updateTimePreview, 1000);
    return () => clearInterval(id);
  }, [updateTimePreview]);

  useEffect(() => {
    let cancelled = false;
    apiRequest<SettingsResponse>("/api/settings")
      .then((s) => {
        if (cancelled) return;
        if (s?.timezone) setTimezone(s.timezone);
        if (s?.notify_before != null) setNotifyBefore(s.notify_before);
        if (s?.notifications_enabled !== undefined) setNotificationsEnabled(Boolean(s.notifications_enabled));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const saveSettings = async () => {
    try {
      await apiRequest(
        "/api/settings",
        { timezone, notify_before: notifyBefore, notifications_enabled: notificationsEnabled },
        "POST"
      );
      setToast(true);
      setTimeout(() => setToast(false), 3000);
    } catch (e) {
      alert("Ошибка сохранения: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  return (
    <>
      <BackButton>← <span>На главную</span></BackButton>
      <h2 style={{ marginTop: 10, marginBottom: 20 }}>Настройки</h2>

      <div className="setting-card">
        <div className="setting-label">ЧАСОВОЙ ПОЯС</div>
        <CustomSelect
          options={TIMEZONES}
          value={timezone}
          onChange={(v) => setTimezone(String(v))}
        />
        <div className="timezone-preview">{timePreview}</div>
      </div>

      <div className="setting-card">
        <div className="setting-label">УВЕДОМЛЯТЬ ЗА</div>
        <CustomSelect
          options={NOTIFY_OPTIONS}
          value={notifyBefore}
          onChange={(v) => setNotifyBefore(Number(v))}
        />
      </div>

      <div className="setting-card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="setting-label" style={{ marginBottom: 0 }}>Включить уведомления</div>
          <label className="switch">
            <input
              type="checkbox"
              checked={notificationsEnabled}
              onChange={(e) => {
                hapticSelection();
                setNotificationsEnabled(e.target.checked);
              }}
            />
            <span className="slider round" />
          </label>
        </div>
        <p
          style={{
            margin: "12px 0 0",
            fontSize: 13,
            color: "var(--text-secondary)",
            fontStyle: "italic",
          }}
        >
          С 21:00 до 10:00 по вашему времени уведомления приходят в тихом режиме (без звука).
        </p>
      </div>

      <button
        type="button"
        className="btn-save"
        onClick={() => {
          hapticImpact("medium");
          saveSettings();
        }}
      >
        Сохранить
      </button>

      {toast && (
        <div className="toast-msg show" role="status">
          Настройки сохранены ✅
        </div>
      )}
    </>
  );
}

export default SettingsPage;
