import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";

type SettingsResponse = { timezone?: string; notify_before?: number };

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
        { timezone, notify_before: notifyBefore },
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
      <Link to="/" className="btn-back">
        ← <span>На главную</span>
      </Link>
      <h2 style={{ marginTop: 10, marginBottom: 20 }}>Настройки</h2>

      <div className="setting-card">
        <div className="setting-label">ЧАСОВОЙ ПОЯС</div>
        <select
          className="setting-select"
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
        >
          {TIMEZONES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <div className="timezone-preview">{timePreview}</div>
      </div>

      <div className="setting-card">
        <div className="setting-label">УВЕДОМЛЯТЬ ЗА</div>
        <select
          className="setting-select"
          value={notifyBefore}
          onChange={(e) => setNotifyBefore(Number(e.target.value))}
        >
          {NOTIFY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <button type="button" className="btn-save" onClick={saveSettings}>
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
