import { useEffect, useMemo, useState } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import "./predictions.css";

type Driver = { code: string; name: string };
type Prediction = {
  sprint_pole_driver: string;
  sprint_winner_driver: string;
  pole_driver: string;
  winner_driver: string;
  second_driver: string;
  third_driver: string;
  fourth_driver: string;
  fifth_driver: string;
  fastest_lap_driver: string;
  first_retirement_driver: string;
  safety_car: boolean;
  points?: number | null;
  max_points?: number | null;
};
type CurrentResponse = {
  status: string;
  season: number;
  round: number | null;
  event_name?: string;
  deadline_utc?: string | null;
  has_sprint: boolean;
  is_open: boolean;
  profile: { display_name: string; completed: boolean };
  drivers: Driver[];
  prediction: Prediction | null;
  scoring_rules: ScoringRule[];
};
type ScoringRule = { key: string; label: string; exact: number; offsets: [number, number, number] };
type HistoryItem = { season: number; round: number; event_name?: string; short_code: string; points: number; max_points: number };
type RoundColumn = { season: number; round: number; event_name: string; short_code: string; max_points: number };
type LeaderboardEntry = {
  place: number;
  telegram_id: number;
  display_name: string;
  total_points: number;
  rounds_scored: number;
  wins: number;
  best_points: number;
  average_points: number;
  history: HistoryItem[];
};
type LeaderboardResponse = { season: number; entries: LeaderboardEntry[]; rounds: RoundColumn[] };

const EMPTY_PREDICTION: Prediction = {
  sprint_pole_driver: "",
  sprint_winner_driver: "",
  pole_driver: "",
  winner_driver: "",
  second_driver: "",
  third_driver: "",
  fourth_driver: "",
  fifth_driver: "",
  fastest_lap_driver: "",
  first_retirement_driver: "",
  safety_car: false,
};

const SPRINT_DRIVER_FIELDS: Array<{ key: keyof Prediction; label: string; marker: string }> = [
  { key: "sprint_pole_driver", label: "Спринт-поул", marker: "SP" },
  { key: "sprint_winner_driver", label: "Спринт-победа", marker: "S1" },
];

const BASE_DRIVER_FIELDS: Array<{ key: keyof Prediction; label: string; marker: string }> = [
  { key: "pole_driver", label: "Поул-позиция", marker: "P" },
  { key: "winner_driver", label: "Победитель", marker: "1" },
  { key: "second_driver", label: "2 место", marker: "2" },
  { key: "third_driver", label: "3 место", marker: "3" },
  { key: "fourth_driver", label: "4 место", marker: "4" },
  { key: "fifth_driver", label: "5 место", marker: "5" },
  { key: "fastest_lap_driver", label: "Лучший круг", marker: "FL" },
  { key: "first_retirement_driver", label: "Первый сход", marker: "DNF" },
];

function deadlineText(value?: string | null) {
  if (!value) return "Время квалификации уточняется";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function pointsLabel(points: number) {
  if (points === 1) return "1 балл";
  if (points >= 2 && points <= 4) return `${points} балла`;
  return `${points} баллов`;
}

export default function PredictionsPage() {
  const [tab, setTab] = useState<"form" | "leaderboard">("form");
  const [current, setCurrent] = useState<CurrentResponse | null>(null);
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [rounds, setRounds] = useState<RoundColumn[]>([]);
  const [leaderboardSeason, setLeaderboardSeason] = useState<number | null>(null);
  const [form, setForm] = useState<Prediction>(EMPTY_PREDICTION);
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [currentData, leaderboardData] = await Promise.all([
        apiRequest<CurrentResponse>("/api/predictions/current"),
        apiRequest<LeaderboardResponse>("/api/predictions/leaderboard"),
      ]);
      setCurrent(currentData);
      setDisplayName(currentData.profile.display_name || "");
      setForm(currentData.prediction ? { ...EMPTY_PREDICTION, ...currentData.prediction } : EMPTY_PREDICTION);
      setEntries(leaderboardData.entries || []);
      setRounds(leaderboardData.rounds || []);
      setLeaderboardSeason(leaderboardData.season || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить прогнозы");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const selectedTopFive = useMemo(
    () => new Set([form.winner_driver, form.second_driver, form.third_driver, form.fourth_driver, form.fifth_driver].filter(Boolean)),
    [form],
  );

  const saveName = async () => {
    setSaving(true);
    setError("");
    try {
      const profile = await apiRequest<{ display_name: string; completed: boolean }>(
        "/api/predictions/profile",
        { display_name: displayName },
        "POST",
      );
      setCurrent((value) => value ? { ...value, profile } : value);
      setDisplayName(profile.display_name);
      setNotice("Имя участника сохранено");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить имя");
    } finally {
      setSaving(false);
    }
  };

  const savePrediction = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await apiRequest("/api/predictions/current", form, "POST");
      setNotice("Прогноз сохранён. Его можно изменить до начала квалификации.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить прогноз");
    } finally {
      setSaving(false);
    }
  };

  const driverFields = current?.has_sprint
    ? [...SPRINT_DRIVER_FIELDS, ...BASE_DRIVER_FIELDS]
    : BASE_DRIVER_FIELDS;
  const formComplete = driverFields.every(({ key }) => Boolean(form[key]));

  return (
    <main className="predictions-page">
      <BackButton>← <span>Назад</span></BackButton>
      <header className="predictions-hero">
        <div>
          <span className="predictions-kicker">F1 Forecast</span>
          <h2>Прогнозы</h2>
          <p>Прогноз закрывается перед первой квалификацией. Чем точнее позиция — тем больше баллов.</p>
        </div>
        {current?.status === "ok" && (
          <div className={`predictions-deadline ${current.is_open ? "is-open" : "is-closed"}`}>
            <span>{current.is_open ? "Приём открыт" : "Приём закрыт"}</span>
            <strong>{deadlineText(current.deadline_utc)}</strong>
          </div>
        )}
      </header>

      <div className="predictions-tabs" role="tablist">
        <button className={tab === "form" ? "active" : ""} onClick={() => setTab("form")}>Мой прогноз</button>
        <button className={tab === "leaderboard" ? "active" : ""} onClick={() => setTab("leaderboard")}>Турнирная таблица</button>
      </div>

      <details className="prediction-rules">
        <summary>
          <span>Как начисляются баллы</span>
          <strong>MAX 37 · СПРИНТ 43</strong>
        </summary>
        <div className="prediction-rules-scroll">
          <table>
            <thead>
              <tr>
                <th>Категория</th>
                <th>Точное попадание</th>
                <th>Ошибка на 1 место</th>
                <th>Ошибка на 2 места</th>
                <th>Ошибка на 3 места</th>
              </tr>
            </thead>
            <tbody>
              {(current?.scoring_rules || []).map((rule) => (
                <tr key={rule.key}>
                  <th>{rule.label}</th>
                  <td>{pointsLabel(rule.exact)}</td>
                  {rule.offsets.map((points, index) => (
                    <td key={index} className={points ? "" : "is-zero"}>{pointsLabel(points)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      {error && <div className="predictions-message is-error">{error}</div>}
      {notice && <div className="predictions-message is-success">{notice}</div>}
      {loading && <div className="predictions-loading">Загрузка данных этапа…</div>}

      {!loading && current && tab === "form" && (
        <section className="prediction-form-shell">
          <div className="prediction-round-title">
            <span>Этап {current.round ?? "—"} · {current.season}</span>
            <h3>{current.event_name || "Следующий Гран-при"}</h3>
          </div>

          {!current.profile.completed ? (
            <div className="prediction-name-card">
              <span className="prediction-step">Шаг 01</span>
              <h3>Имя участника</h3>
              <p>Оно будет отображаться в общей турнирной таблице.</p>
              <div className="prediction-name-row">
                <input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  maxLength={40}
                  placeholder="Например, Alex Racing"
                />
                <button disabled={saving || displayName.trim().length < 2} onClick={() => void saveName()}>
                  Продолжить
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="prediction-profile-line">
                <span>Участник</span>
                <strong>{current.profile.display_name}</strong>
                <button onClick={() => setCurrent({ ...current, profile: { ...current.profile, completed: false } })}>Изменить</button>
              </div>

              <div className="prediction-grid">
                {driverFields.map(({ key, label, marker }) => (
                  <label key={key} className="prediction-field">
                    <span className="prediction-field-marker">{marker}</span>
                    <span className="prediction-field-copy">{label}</span>
                    <select
                      value={String(form[key] ?? "")}
                      disabled={!current.is_open}
                      onChange={(event) => setForm({ ...form, [key]: event.target.value })}
                    >
                      <option value="">Выберите пилота</option>
                      {current.drivers.map((driver) => {
                        const isPlacement = ["winner_driver", "second_driver", "third_driver", "fourth_driver", "fifth_driver"].includes(key);
                        const disabled = isPlacement && selectedTopFive.has(driver.code) && form[key] !== driver.code;
                        return <option key={driver.code} value={driver.code} disabled={disabled}>{driver.name} · {driver.code}</option>;
                      })}
                    </select>
                  </label>
                ))}

                <fieldset className="prediction-field prediction-safety-car" disabled={!current.is_open}>
                  <span className="prediction-field-marker">SC</span>
                  <legend>Машина безопасности</legend>
                  <div>
                    <button type="button" className={form.safety_car ? "active" : ""} onClick={() => setForm({ ...form, safety_car: true })}>Да</button>
                    <button type="button" className={!form.safety_car ? "active" : ""} onClick={() => setForm({ ...form, safety_car: false })}>Нет</button>
                  </div>
                </fieldset>
              </div>

              <div className="prediction-submit-row">
                <p>{current.is_open
                  ? `После старта ${current.has_sprint ? "спринт-квалификации" : "квалификации"} сервер заблокирует любые изменения.`
                  : "Прогноз доступен только для просмотра."}</p>
                <button disabled={!current.is_open || !formComplete || saving} onClick={() => void savePrediction()}>
                  {saving ? "Сохраняем…" : current.prediction ? "Обновить прогноз" : "Отправить прогноз"}
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {!loading && tab === "leaderboard" && (
        <section className="prediction-leaderboard">
          <div className="prediction-leaderboard-title">
            <div>
              <span>Season standings · {leaderboardSeason ?? current?.season}</span>
              <h3>Турнирная таблица</h3>
            </div>
            <p>Прокрутите таблицу вправо, чтобы увидеть результаты каждого этапа.</p>
          </div>
          <div className="prediction-leaderboard-scroll">
            <table>
              <thead>
                <tr>
                  <th className="is-place">Место</th>
                  <th className="is-name">Участник</th>
                  <th>Побед</th>
                  <th>Лучший</th>
                  <th>Средний</th>
                  <th>Этапы</th>
                  <th className="is-total">Баллы всего</th>
                  {rounds.map((roundInfo) => (
                    <th key={`${roundInfo.season}-${roundInfo.round}`} title={roundInfo.event_name}>
                      {roundInfo.short_code}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const stagePoints = new Map(
                    entry.history.map((item) => [`${item.season}-${item.round}`, item.points]),
                  );
                  return (
                    <tr key={entry.telegram_id}>
                      <td className="is-place"><strong>{String(entry.place).padStart(2, "0")}</strong></td>
                      <th className="is-name">{entry.display_name}</th>
                      <td>{entry.wins}</td>
                      <td>{entry.best_points}</td>
                      <td>{entry.average_points.toFixed(1)}</td>
                      <td>{entry.rounds_scored}</td>
                      <td className="is-total"><strong>{entry.total_points}</strong></td>
                      {rounds.map((roundInfo) => {
                        const points = stagePoints.get(`${roundInfo.season}-${roundInfo.round}`);
                        return (
                          <td key={`${roundInfo.season}-${roundInfo.round}`} title={roundInfo.event_name}>
                            {points ?? "—"}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!entries.length && <div className="predictions-loading">Турнирная таблица пока пуста.</div>}
        </section>
      )}
    </main>
  );
}
