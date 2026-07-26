import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { CustomSelect } from "../../components/CustomSelect";
import { apiRequest } from "../../helpers/api";
import "./practice-results.css";

type PracticeSession = 1 | 2 | 3;

type PracticeResult = {
  position: number;
  driver: string;
  name: string;
  team: string;
  best: string;
  gap: string;
  laps: number;
  sector1?: string;
  sector2?: string;
  sector3?: string;
  is_favorite_driver?: boolean;
};

type PracticeResponse = {
  season: number;
  round: number | null;
  session: PracticeSession;
  available_sessions: PracticeSession[];
  is_sprint_weekend: boolean;
  race_info?: { event_name?: string; location?: string } | null;
  results: PracticeResult[];
};

type SeasonRace = {
  round: number;
  event_name?: string;
  available_practice_sessions?: PracticeSession[];
  is_sprint_weekend?: boolean;
};

type PracticeRequestState = {
  key: string;
  data: PracticeResponse | null;
  error: string | null;
};

function optionalInt(value: string | null): number | null {
  if (!value) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function sessionsForRace(race: SeasonRace | undefined): PracticeSession[] {
  const configured = race?.available_practice_sessions?.filter(
    (session): session is PracticeSession => session === 1 || session === 2 || session === 3,
  );
  if (configured?.length) return configured;
  return race?.is_sprint_weekend ? [1] : [1, 2, 3];
}

export default function PracticeResultsPage() {
  const [searchParams] = useSearchParams();
  const season = optionalInt(searchParams.get("season")) ?? new Date().getFullYear();
  const queryRound = optionalInt(searchParams.get("round"));
  const querySession = optionalInt(searchParams.get("session"));
  const initialSession: PracticeSession =
    querySession === 2 || querySession === 3 ? querySession : 1;

  const [mode, setMode] = useState<"latest" | "archive">(
    searchParams.get("mode") === "archive" ? "archive" : "latest",
  );
  const [selectedRound, setSelectedRound] = useState<number | null>(queryRound);
  const [selectedSession, setSelectedSession] = useState<PracticeSession>(initialSession);
  const [seasonRaces, setSeasonRaces] = useState<SeasonRace[]>([]);
  const [requestState, setRequestState] = useState<PracticeRequestState>({
    key: "",
    data: null,
    error: null,
  });
  const requestKey = `${season}:${mode}:${selectedRound ?? "latest"}:${selectedSession}`;
  const loading = requestState.key !== requestKey;
  const data = loading ? null : requestState.data;
  const error = loading ? null : requestState.error;

  useEffect(() => {
    let cancelled = false;
    apiRequest<{ races?: SeasonRace[] }>("/api/season", {
      season,
      completed_only: true,
      session_type: "practice",
    })
      .then((response) => {
        if (cancelled) return;
        const races = (response.races || [])
          .filter((race) => Number.isFinite(race.round) && race.round > 0)
          .sort((left, right) => right.round - left.round);
        setSeasonRaces(races);
        setSelectedRound((current) => {
          if (current && races.some((race) => race.round === current)) return current;
          return races[0]?.round ?? null;
        });
      })
      .catch(() => {
        if (!cancelled) setSeasonRaces([]);
      });
    return () => {
      cancelled = true;
    };
  }, [season]);

  useEffect(() => {
    if (mode === "archive" && selectedRound === null) return;
    let cancelled = false;
    apiRequest<PracticeResponse>("/api/practice-results", {
      season,
      session: selectedSession,
      round: mode === "archive" ? selectedRound ?? undefined : undefined,
    })
      .then((response) => {
        if (cancelled) return;
        setRequestState({ key: requestKey, data: response, error: null });
        if (
          response.available_sessions.length > 0
          && !response.available_sessions.includes(selectedSession)
        ) {
          setSelectedSession(response.available_sessions[0]);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setRequestState({
            key: requestKey,
            data: null,
            error: reason instanceof Error ? reason.message : "Не удалось загрузить практику",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, requestKey, season, selectedRound, selectedSession]);

  const availableSessions = useMemo<PracticeSession[]>(() => {
    if (mode === "archive") {
      const archiveRace = seasonRaces.find((race) => race.round === selectedRound);
      return sessionsForRace(archiveRace);
    }
    if (data?.available_sessions?.length) return data.available_sessions;
    return [1, 2, 3];
  }, [data, mode, seasonRaces, selectedRound]);
  const eventName = data?.race_info?.event_name || "Grand Prix";
  const selectArchiveRound = (round: number) => {
    const sessions = sessionsForRace(seasonRaces.find((race) => race.round === round));
    setSelectedRound(round);
    if (!sessions.includes(selectedSession)) setSelectedSession(sessions[0] ?? 1);
  };

  return (
    <div className="practice-page">
      <BackButton fallback="/">← <span>Главное меню</span></BackButton>

      <header className="practice-hero">
        <div>
          <span className="practice-kicker">Тайминг уикенда</span>
          <h1>Свободные заезды</h1>
          <p>
            {data?.round ? `Этап ${String(data.round).padStart(2, "0")} · ` : ""}
            {eventName} · сезон {data?.season || season}
          </p>
        </div>
        <div className="practice-hero-aside">
          {data?.is_sprint_weekend && (
            <span className="practice-format-badge">Спринт-уикенд · только FP1</span>
          )}
          <div className="practice-mode-controls race-results-desktop-controls">
          <div className="segmented-tabs race-results-desktop-tabs">
            <div
              className="segmented-slider"
              style={{ transform: mode === "archive" ? "translateX(100%)" : "translateX(0%)" }}
            />
            <button
              type="button"
              className={`segmented-tab ${mode === "latest" ? "active" : ""}`}
              onClick={() => setMode("latest")}
            >
              Последние
            </button>
            <button
              type="button"
              className={`segmented-tab ${mode === "archive" ? "active" : ""}`}
              onClick={() => setMode("archive")}
            >
              Архив
            </button>
          </div>
          {mode === "archive" && selectedRound !== null && (
            <div className="practice-round-select race-results-desktop-round-select">
              <CustomSelect
                options={seasonRaces.map((race) => ({
                  value: race.round,
                  label: `Этап ${String(race.round).padStart(2, "0")} · ${race.event_name || "Grand Prix"}`,
                }))}
                value={selectedRound}
                onChange={(value) => selectArchiveRound(Number(value))}
              />
            </div>
          )}
          </div>
        </div>
      </header>

      <section className="practice-controls" aria-label="Выбор сессии практики">
        <div className="practice-session-tabs" role="tablist" aria-label="Сессия">
          {availableSessions.map((session) => (
            <button
              type="button"
              role="tab"
              aria-selected={selectedSession === session}
              className={selectedSession === session ? "active" : ""}
              onClick={() => setSelectedSession(session)}
              key={session}
            >
              P{session}
            </button>
          ))}
        </div>
        {mode === "archive" && (
          <div className="archive-note practice-archive-note">
            Результаты других ГП можно открыть в разделе Календарь.
          </div>
        )}
      </section>

      <section className="practice-results-panel">
        <div className="practice-results-heading">
          <div>
            <span>Классификация</span>
            <h2>Практика {selectedSession}</h2>
          </div>
          <small>{data?.results.length || 0} пилотов</small>
        </div>

        {loading && (
          <div className="practice-state">
            <div className="spinner" />
            Загружаем результаты…
          </div>
        )}
        {!loading && error && <div className="practice-state error">{error}</div>}
        {!loading && !error && (!data || data.results.length === 0) && (
          <div className="practice-state">
            Результаты P{selectedSession} пока недоступны.
          </div>
        )}
        {!loading && !error && data && data.results.length > 0 && (
          <div className="practice-table">
            <div className="practice-table-row practice-table-head">
              <span>Поз</span><span>Пилот</span><span>Команда</span>
              <span>Лучший круг</span><span>Отставание</span><span>Круги</span>
            </div>
            {data.results.map((result) => (
              <div
                className={`practice-table-row${result.position === 1 ? " leader" : ""}`}
                key={`${result.position}-${result.driver}`}
              >
                <span className="practice-position">{String(result.position).padStart(2, "0")}</span>
                <span className="practice-driver">
                  <b>{result.is_favorite_driver ? "★ " : ""}{result.name || result.driver}</b>
                  <small>{result.driver}</small>
                </span>
                <span className="practice-team">{result.team || "—"}</span>
                <span className="practice-time">{result.best || "—"}</span>
                <span className="practice-gap">{result.gap || "—"}</span>
                <span className="practice-laps">{result.laps}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
