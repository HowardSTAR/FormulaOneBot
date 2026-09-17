import { GlossaryText } from "../../components/GlossaryText";
import { DriverPicker, type PickerDriver } from "../../components/DriverPicker";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { getWebsiteUser, hasTelegramAuth, useAuthState } from "../../helpers/auth";
import "./predictions.css";
import { PersonalReview } from "./PersonalReview";
import { trackPrediction } from '../../helpers/analytics';
import { SeasonProgress } from './SeasonProgress';
import { LeaguePanel, StageScores } from './LeaguePanel';

type Driver = PickerDriver;
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
  opens_at_utc?: string | null;
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
  user_id: number;
  display_name: string;
  total_points: number;
  rounds_scored: number;
  wins: number;
  best_points: number;
  average_points: number;
  history: HistoryItem[];
};
type LeaderboardResponse = { season: number; entries: LeaderboardEntry[]; rounds: RoundColumn[]; current_user_id: number };

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
  const auth = useAuthState();
  if (!auth.loaded) return <p role="status">Проверяем вход…</p>;
  return <PredictionsContent key={String(auth.signedIn)} guest={!auth.signedIn} />;
}

function PredictionsContent({ guest }: { guest: boolean }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const tab = !guest && ['leaderboard', 'history', 'leagues'].includes(requestedTab || '') ? requestedTab : 'form';
  const [stageRound, setStageRound] = useState(0);
  const setTab = (value: "form" | "leaderboard" | "history" | "leagues") => {
    setSearchParams((params) => { params.set("tab", value); return params; }, { replace: true });
  };
  const [current, setCurrent] = useState<CurrentResponse | null>(null);
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [reviewRound, setReviewRound] = useState<RoundColumn | null>(null);
  const [rounds, setRounds] = useState<RoundColumn[]>([]);
  const [leaderboardSeason, setLeaderboardSeason] = useState<number | null>(null);
  const [form, setForm] = useState<Prediction>(EMPTY_PREDICTION);
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showTelegramReminder, setShowTelegramReminder] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [currentData, leaderboardData] = await Promise.all([
        apiRequest<CurrentResponse>(guest ? "/api/predictions/preview" : "/api/predictions/current"),
        guest ? Promise.resolve<LeaderboardResponse>({season: 0, entries: [], rounds: [], current_user_id: 0}) : apiRequest<LeaderboardResponse>("/api/predictions/leaderboard"),
      ]);
      setCurrent(currentData);
      setDisplayName(currentData.profile.display_name || "");
      setForm(currentData.prediction ? { ...EMPTY_PREDICTION, ...currentData.prediction } : EMPTY_PREDICTION);
      if (!currentData.prediction) {
        try {
          const draft = JSON.parse(sessionStorage.getItem(`prediction-draft:${currentData.season}:${currentData.round}`) || 'null');
          if (draft && typeof draft === 'object') {
            const safe = { ...EMPTY_PREDICTION };
            for (const key of Object.keys(EMPTY_PREDICTION) as Array<keyof typeof EMPTY_PREDICTION>) {
              if (key === 'safety_car') safe.safety_car = draft.safety_car === true;
              else if (typeof draft[key] === 'string' && currentData.drivers.some(d => d.code === draft[key])) Object.assign(safe, {[key]: draft[key]});
            }
            setForm(safe);
            setNotice('Черновик восстановлен. Проверьте выбор и сохраните прогноз — сам по себе черновик не участвует.');
          }
        } catch { /* Storage may be unavailable in private browsing. */ }
      }
      setEntries(leaderboardData.entries || []);
      setCurrentUserId(leaderboardData.current_user_id);
      setRounds(leaderboardData.rounds || []);
      setLeaderboardSeason(leaderboardData.season || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить прогнозы");
    } finally {
      setLoading(false);
    }
  }, [guest]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (current?.round && tab === 'form') trackPrediction('prediction_view',current.season,current.round);
  }, [current?.season,current?.round,tab]);
  const editPrediction = (patch: Partial<Prediction>) => {
    if (current?.round) trackPrediction('prediction_start',current.season,current.round);
    setForm(value => ({...value,...patch}));
  };

  useEffect(() => {
    if (hasTelegramAuth()) return;
    let active = true;
    void getWebsiteUser().then((user) => {
      if (active) setShowTelegramReminder(Boolean(user && !user.telegram_id));
    });
    return () => { active = false; };
  }, []);

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
    if (guest && current) {
      try {
        sessionStorage.setItem(`prediction-draft:${current.season}:${current.round}`, JSON.stringify(form));
        window.location.assign('/account?returnTo=predictions');
      } catch { setError('Не удалось сохранить черновик в браузере. Войдите в аккаунт перед заполнением.'); }
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await apiRequest("/api/predictions/current", form, "POST");
      try { sessionStorage.removeItem(`prediction-draft:${current?.season}:${current?.round}`); } catch { /* optional browser storage */ }
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
  const editable = guest || Boolean(current?.is_open);
  const beforeOpening = Date.parse(current?.opens_at_utc || '') > Date.now();

  return (
    <main className="predictions-page">
      <BackButton>← <span>Назад</span></BackButton>
      <header className="predictions-hero">
        <div>
          <span className="predictions-kicker">F1 Forecast</span>
          <h2>Прогнозы</h2>
          <p><GlossaryText>Прогноз закрывается перед первой квалификацией. Чем точнее позиция — тем больше баллов.</GlossaryText></p>
        </div>
        {current?.status === "ok" && (
          <div className={`predictions-deadline ${current.is_open ? "is-open" : "is-closed"}`}>
            <span>{current.is_open ? "Приём открыт до" : beforeOpening ? "Приём откроется" : "Приём закрыт"}</span>
            <strong>{deadlineText(beforeOpening ? current.opens_at_utc : current.deadline_utc)}</strong>
          </div>
        )}
      </header>

      {guest && <aside className="predictions-message">
        <strong>Попробуйте прогноз без регистрации</strong>
        <p>Выберите пилотов и исходы этапа. После гонки получите личный разбор: ваш выбор, фактический результат и объяснение каждого балла. Вход понадобится только для сохранения.</p>
        <details><summary>Пример разбора</summary><p>Пример, не ваш результат: победитель угадан точно — 8 баллов. Если данных о первом сходе ещё нет, пункт ожидает подтверждения, а не считается ошибкой.</p></details>
        {window.location.hash.startsWith('#invite=') && <p>Вас пригласили в приватную лигу. <Link to={`/account?returnTo=leagues${window.location.hash}`}>Войдите, чтобы принять приглашение</Link>. Автоматически вступать в лигу вы не будете.</p>}
      </aside>}

      {showTelegramReminder && (
        <aside className="predictions-telegram-reminder">
          <div>
            <strong>Telegram не привязан</strong>
            <span>Прогнозы доступны полностью. Привяжите Telegram только если хотите получать уведомления о результатах.</span>
          </div>
          <Link to="/account">Привязать Telegram</Link>
        </aside>
      )}

      <div className="predictions-tabs" role="tablist">
        <button className={tab === "form" ? "active" : ""} onClick={() => setTab("form")}>Мой прогноз</button>
        {!guest && <button className={tab === "leaderboard" ? "active" : ""} onClick={() => setTab("leaderboard")}>Турнирная таблица</button>}
        {!guest && <button className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}>Мой сезон</button>}
        {!guest && <button className={tab === 'leagues' ? 'active' : ''} onClick={() => setTab('leagues')}>Лиги друзей</button>}
      </div>

      {tab === 'history' && <SeasonProgress />}
      {tab === 'leagues' && <LeaguePanel />}

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
                  <th><GlossaryText>{rule.label}</GlossaryText></th>
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
                {!guest && <button onClick={() => setCurrent({ ...current, profile: { ...current.profile, completed: false } })}>Изменить</button>}
              </div>

              <div className="prediction-grid">
                {driverFields.map(({ key, label, marker }) => (
                  <div key={key} className="prediction-field">
                    <span className="prediction-field-marker">{marker}</span>
                    <span className="prediction-field-copy">{label}</span>
                    <DriverPicker label={label} season={current.season}
                      value={String(form[key] ?? "")}
                      disabled={!editable}
                      onChange={(code) => editPrediction({ [key]: code })}
                      drivers={current.drivers.map((driver) => {
                        const isPlacement = ["winner_driver", "second_driver", "third_driver", "fourth_driver", "fifth_driver"].includes(key);
                        const disabled = isPlacement && selectedTopFive.has(driver.code) && form[key] !== driver.code;
                        return { ...driver, disabled };
                      })} />
                  </div>
                ))}

                <fieldset className="prediction-field prediction-safety-car" disabled={!editable}>
                  <span className="prediction-field-marker">SC</span>
                  <legend><GlossaryText>Машина безопасности</GlossaryText></legend>
                  <div>
                    <button type="button" className={form.safety_car ? "active" : ""} onClick={() => editPrediction({ safety_car: true })}>Да</button>
                    <button type="button" className={!form.safety_car ? "active" : ""} onClick={() => editPrediction({ safety_car: false })}>Нет</button>
                  </div>
                </fieldset>
              </div>

              <div className="prediction-submit-row">
                <p>{guest ? 'Это только черновик в вашем браузере. Для участия нужно войти и отправить прогноз в период приёма.' : current.is_open
                  ? `После старта ${current.has_sprint ? "спринт-квалификации" : "квалификации"} сервер заблокирует любые изменения.`
                  : "Прогноз доступен только для просмотра."}</p>
                <button disabled={!editable || (!guest && !formComplete) || saving || !current.round} onClick={() => void savePrediction()}>
                  {saving ? "Сохраняем…" : guest ? "Войти и сохранить черновик" : current.prediction ? "Обновить прогноз" : "Отправить прогноз"}
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {!loading && tab === "leaderboard" && (
        <section className="prediction-leaderboard">
          <label>Рейтинг этапа <select value={stageRound} onChange={e => setStageRound(Number(e.target.value))}>
            <option value={0}>Выберите этап</option>{rounds.map(r => <option key={r.round} value={r.round}>{r.event_name}</option>)}
          </select></label>
          {stageRound > 0 && <StageScores entries={entries} round={stageRound} />}
          <div className="prediction-leaderboard-title">
            <div>
              <span>Season standings · {leaderboardSeason ?? current?.season}</span>
              <h3>Турнирная таблица</h3>
            </div>
            <p>Прокрутите таблицу вправо, чтобы увидеть результаты каждого этапа.</p>
          </div>
          <div className="prediction-leaderboard-scroll">
            <p>Нажмите на очки в своей строке, чтобы открыть личный разбор прогноза. Другие участники его не видят.</p>
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
                    <tr key={entry.user_id}>
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
                            {entry.user_id === currentUserId && points !== undefined
                              ? <button className="prediction-own-score" aria-label={`Мой прогноз: ${roundInfo.event_name}, этап ${roundInfo.round}, ${points} баллов`} onClick={() => setReviewRound(roundInfo)}>{points}</button>
                              : points ?? "—"}
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
      {reviewRound && <PersonalReview key={`${reviewRound.season}-${reviewRound.round}`} season={reviewRound.season} round={reviewRound.round} onClose={() => setReviewRound(null)} />}
    </main>
  );
}
