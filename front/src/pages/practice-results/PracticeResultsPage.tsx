import { useSessionFilters } from '../../helpers/sessionFilters';
import { ResultsSeasonFilter } from '../../components/ResultsSeasonFilter';
import { useEffect, useMemo, useState } from "react";
import { Link } from 'react-router-dom';
import { BackButton } from "../../components/BackButton";
import { CustomSelect } from "../../components/CustomSelect";
import { apiRequest } from "../../helpers/api";
import { ResultsDesktopTable, ResultsFeedback, ResultsMobileRow } from "../../components/SessionResultsUI";
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
  requested_round?: number | null;
  session: PracticeSession;
  available_sessions: PracticeSession[];
  is_sprint_weekend: boolean;
  data_fallback?: boolean;
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

function sessionsForRace(race: SeasonRace | undefined): PracticeSession[] {
  const configured = race?.available_practice_sessions?.filter(
    (session): session is PracticeSession => session === 1 || session === 2 || session === 3,
  );
  if (configured?.length) return configured;
  return race?.is_sprint_weekend ? [1] : [1, 2, 3];
}

export default function PracticeResultsPage() {
  const {season, setSeason, mode, setMode, selectedRound, setSelectedRound, selectedSession, setSelectedSession} = useSessionFilters(2018);
  const [attempt, setAttempt] = useState(0);
  const [seasonRaces, setSeasonRaces] = useState<SeasonRace[]>([]);
  const [seasonError, setSeasonError] = useState<string | null>(null);
  const [seasonLoading, setSeasonLoading] = useState(true);
  const [requestState, setRequestState] = useState<PracticeRequestState>({
    key: "",
    data: null,
    error: null,
  });
  const requestKey = `${attempt}:${season}:${mode}:${selectedRound ?? "latest"}:${selectedSession}`;
  const loading = requestState.key !== requestKey || (mode === 'archive' && seasonLoading);
  const data = loading ? null : requestState.data;
  const error = loading ? null : requestState.error || (mode === 'archive' ? seasonError : null);

  useEffect(() => {
    let cancelled = false;
    setSeasonLoading(true); setSeasonError(null);
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
        if (!cancelled) { setSeasonRaces([]); setSeasonError('Не удалось загрузить список этапов. Попробуйте повторить запрос.'); }
      }).finally(() => { if (!cancelled) setSeasonLoading(false); });
    return () => {
      cancelled = true;
    };
  }, [season, attempt]);

  useEffect(() => {
    if (mode === "archive" && selectedRound === null) { setRequestState({key: requestKey, data: null, error: null}); return; }
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
    setSelectedRound(round, sessions.includes(selectedSession) ? undefined : sessions[0] ?? 1);
  };

  return (
    <div className="practice-page">
      <ResultsSeasonFilter season={season} onChange={setSeason} minYear={2018} />
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
          {data?.data_fallback && (
            <span
              className="practice-format-badge"
              title={data.requested_round ? `Данные этапа ${data.requested_round} ещё недоступны` : undefined}
            >
              Показан последний доступный этап
            </span>
          )}
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
            Выберите сезон и этап выше. В спринт-уикенд доступна только первая практика.
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

        <ResultsFeedback
          loading={loading}
          error={error}
          retry={() => setAttempt(v => v + 1)}
          empty={!loading && !error && (!data || data.results.length === 0)}
          icon="⏱"
          title={`Нет данных P${selectedSession}`}
          description={`Результаты практики ${selectedSession} пока недоступны.`}
        />
        {!loading && !error && data && data.results.length > 0 && (
          <>
            <div className="practice-mobile-results standings-list">
              {data.results.map((result) => (
                <ResultsMobileRow
                  season={data.season || season}
                  key={`${result.position}-${result.driver}`}
                  position={result.position}
                  name={result.name || result.driver}
                  code={result.driver}
                  team={result.team}
                  favorite={result.is_favorite_driver}
                  value={result.position === 1 ? (result.best || "—") : (result.gap || "—")}
                />
              ))}
            </div>
            <ResultsDesktopTable
              className="practice-unified-table"
              columns={["Поз", "Пилот", "Команда", "Лучший круг / отрыв", "Круги"]}
              rows={data.results.map((result) => ({
                key: `${result.position}-${result.driver}`,
                winner: result.position === 1,
                values: [
                  String(result.position).padStart(2, "0"),
                  <Link className="ui-profile-link" to={`/driver-details?code=${encodeURIComponent(result.driver)}&season=${data.season || season}`}>{result.is_favorite_driver ? '★ ' : ''}{result.name || result.driver} · {result.driver}</Link>,
                  result.team || "—",
                  result.position === 1 ? (result.best || "—") : (result.gap || "—"),
                  result.laps,
                ],
              }))}
            />
          </>
        )}
      </section>
    </div>
  );
}
