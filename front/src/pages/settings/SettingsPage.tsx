import { useState, useEffect, useCallback } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { CustomSelect } from "../../components/CustomSelect";
import { hapticSelection, hapticImpact, isTelegramWebApp } from "../../helpers/telegram";

type SettingsResponse = { timezone?: string; notify_before?: number; notifications_enabled?: boolean };

const TIMEZONES = [
  { value: "Etc/GMT+12", label: "UTC-12" },
  { value: "Etc/GMT+11", label: "UTC-11" },
  { value: "Etc/GMT+10", label: "UTC-10" },
  { value: "Etc/GMT+9", label: "UTC-9" },
  { value: "Etc/GMT+8", label: "UTC-8" },
  { value: "Etc/GMT+7", label: "UTC-7" },
  { value: "Etc/GMT+6", label: "UTC-6" },
  { value: "Etc/GMT+5", label: "UTC-5" },
  { value: "Etc/GMT+4", label: "UTC-4" },
  { value: "Etc/GMT+3", label: "UTC-3" },
  { value: "Etc/GMT+2", label: "UTC-2" },
  { value: "Etc/GMT+1", label: "UTC-1" },
  { value: "UTC", label: "UTC (GMT)" },
  { value: "Etc/GMT-1", label: "UTC+1 (CET)" },
  { value: "Etc/GMT-2", label: "UTC+2 (EET)" },
  { value: "Etc/GMT-3", label: "UTC+3 (Москва, Стамбул)" },
  { value: "Etc/GMT-4", label: "UTC+4 (Дубай, Баку)" },
  { value: "Etc/GMT-5", label: "UTC+5 (Ташкент)" },
  { value: "Etc/GMT-6", label: "UTC+6 (Астана)" },
  { value: "Etc/GMT-7", label: "UTC+7 (Бангкок)" },
  { value: "Etc/GMT-8", label: "UTC+8 (Пекин, Сингапур)" },
  { value: "Etc/GMT-9", label: "UTC+9 (Токио)" },
  { value: "Etc/GMT-10", label: "UTC+10" },
  { value: "Etc/GMT-11", label: "UTC+11" },
  { value: "Etc/GMT-12", label: "UTC+12" },
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

  if (!isTelegramWebApp()) {
    return (
      <>
        <BackButton>← <span>На главную</span></BackButton>
        <h2 style={{ marginTop: 10, marginBottom: 20 }}>Настройки</h2>
        <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text-secondary)" }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔒</div>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>Доступно только в Telegram</div>
          <div>Откройте приложение через Telegram для изменения настроек</div>
        </div>
      </>
    );
  }

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
