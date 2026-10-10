import { timezoneName } from '../../helpers/presentation';
import { GlossaryText } from "../../components/GlossaryText";
import { useState, useEffect, useCallback } from "react";
import { Link, useSearchParams } from 'react-router-dom';
import { BackButton } from "../../components/BackButton";
import { AnimatedTrackMap } from "../../components/AnimatedTrackMap";
import { DetailedTrackMap } from "../../components/DetailedTrackMap";
import { apiRequest } from "../../helpers/api";
import { getDisplayTimezone } from "../../helpers/timezone";
import { getCircuitInsightsRu } from "../../assets/circuitInsightsRu";
import "./next-race-mobile.css";
import { CalendarDownload } from '../../components/CalendarDownload';

type NextRaceResponse = {
  status: string;
  event_name?: string;
  is_cancelled?: boolean;
  country?: string;
  location?: string;
  season?: number;
  round?: number;
  date?: string;
  sessions?: Session[];
};
type Session = { name: string; utc_iso?: string; utc?: string; _time?: string; _date?: string };
type ScheduleResponse = { sessions?: Session[] };
type RaceDetailsResponse = Omit<NextRaceResponse, 'status'> & ScheduleResponse & { event_format?: string };

function SessionSchedule({sessions}: {sessions: Session[]}) {
  return <ol className="weekend-session-list">
    {sessions.map((session, index) => <li className="weekend-session" key={`${session.name}-${index}`}>
      <div className="weekend-session-name">{session.name}</div>
      <div className="weekend-session-time"><strong>{session._time || 'Уточняется'}</strong>
        {session._date && <><span aria-hidden="true"> | </span><span>{session._date}</span></>}
      </div>
    </li>)}
  </ol>;
}

function StageResults({season, round, sessions}: {season: number | null; round: number | null; sessions: Session[]}) {
  if (!season || !round) return null;
  const sprint = sessions.some(session => /спринт|sprint/i.test(session.name));
  const query = `?mode=archive&season=${season}&round=${round}`;
  return <section className="weekend-results" aria-label="Результаты этапа">
    <h3>Результаты этапа</h3>
    <div className="weekend-results-links">
      <Link className="ui-action-link" to={`/race-results${query}`}>Гонка →</Link>
      <Link className="ui-action-link" to={`/quali-results${query}`}>Квалификация →</Link>
      {sprint && <><Link className="ui-action-link" to={`/sprint-results${query}`}>Спринт →</Link>
        <Link className="ui-action-link" to={`/sprint-quali-results${query}`}>Спринт-квалификация →</Link></>}
    </div>
  </section>;
}

function NextRacePage() {
  const [searchParams] = useSearchParams();
  const selectedSeason = searchParams.get('season');
  const selectedRound = searchParams.get('round');
  const [title, setTitle] = useState("Загрузка...");
  const [location, setLocation] = useState("...");
  const [eventName, setEventName] = useState<string | null>(null);
  const [isCancelled, setIsCancelled] = useState(false);
  const [raceCountry, setRaceCountry] = useState("");
  const [raceCity, setRaceCity] = useState("");
  const [raceDateText, setRaceDateText] = useState("--");
  const [raceTimeText, setRaceTimeText] = useState("--:--");
  const [displayTimezone, setDisplayTimezone] = useState("Локальное время");
  const [raceRound, setRaceRound] = useState<number | null>(null);
  const [raceSeason, setRaceSeason] = useState<number | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [expandedFactIndex, setExpandedFactIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [layoutPhase, setLayoutPhase] = useState<"draw" | "split">("draw");
  const [trackRevealed, setTrackRevealed] = useState(false);
  const handleTrackRevealed = useCallback(() => setTrackRevealed(true), []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      setEventName(null);
      setSessions([]);
      setTitle('Загрузка...');
      setLocation('...');
      setLayoutPhase('draw');
      setTrackRevealed(false);
      try {
        const selected = selectedSeason !== null || selectedRound !== null;
        if (selected && (!/^\d{4}$/.test(selectedSeason ?? '') || !/^\d{1,2}$/.test(selectedRound ?? '')
          || Number(selectedSeason) < 1950 || Number(selectedSeason) > 2100
          || Number(selectedRound) < 1 || Number(selectedRound) > 30)) {
          throw new Error('Некорректный сезон или номер этапа');
        }
        const raceData = selected
          ? await apiRequest<RaceDetailsResponse>('/api/race-details', {season: selectedSeason, round: selectedRound})
            .then(data => ({...data, status: 'ok', season: Number(selectedSeason), round: Number(selectedRound)}))
          : await apiRequest<NextRaceResponse>("/api/next-race");
        const userTz = getDisplayTimezone();

        if (cancelled) return;
        setDisplayTimezone(timezoneName(userTz));
        if (raceData.status !== "ok") {
          setTitle(raceData.status === "season_finished" ? "Сезон завершен" : "Нет данных");
          setSessions([]);
          setLoading(false);
          return;
        }

        setTitle(raceData.event_name || "Загрузка...");
        setEventName(raceData.event_name || null);
        setIsCancelled(Boolean(raceData.is_cancelled));
        setRaceCountry(raceData.country || "");
        setRaceCity(raceData.location || "");
        setRaceRound(raceData.round ?? null);
        setRaceSeason(raceData.season ?? null);
        setLocation(`${raceData.country || ""}, ${raceData.location || ""}`);

        const scheduleData: ScheduleResponse = selected
          ? {sessions: raceData.sessions || []}
          : await apiRequest<ScheduleResponse>("/api/weekend-schedule", {
          season: raceData.season!,
          round_number: raceData.round!,
        });
        if (cancelled) return;

        const raceSession =
          scheduleData.sessions?.find((s) => s.name === "Гонка" || s.name === "Race");
        if (raceSession?.utc_iso && Number.isFinite(Date.parse(raceSession.utc_iso))) {
          const dateObj = new Date(raceSession.utc_iso);
          setRaceDateText(
            dateObj.toLocaleDateString("ru-RU", {
              timeZone: userTz,
              day: "numeric",
              month: "long",
            }).toUpperCase()
          );
          setRaceTimeText(
            dateObj.toLocaleTimeString("ru-RU", {
              timeZone: userTz,
              hour: "2-digit",
              minute: "2-digit",
            })
          );
        } else {
          setRaceDateText(raceData.date || "Уточняется");
          setRaceTimeText("--:--");
        }

        if (scheduleData.sessions?.length) {
          setSessions(
            scheduleData.sessions.map((s) => {
              let time = "Уточняется";
              let date = "";
              if (s.utc_iso && Number.isFinite(Date.parse(s.utc_iso))) {
                try {
                  const d = new Date(s.utc_iso);
                  time = d.toLocaleTimeString("ru-RU", {
                    timeZone: userTz,
                    hour: "2-digit",
                    minute: "2-digit",
                  });
                  date = d.toLocaleDateString("ru-RU", {
                    timeZone: userTz,
                    day: "2-digit",
                    month: "2-digit",
                  });
                } catch {
                  time = "Уточняется";
                }
              }
              return { ...s, _time: time, _date: date };
            })
          );
        } else {
          setSessions([]);
        }
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          const msg = e instanceof Error ? e.message : "Ошибка загрузки";
          setError(msg);
          setTitle(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [selectedSeason, selectedRound]);

  useEffect(() => {
    if (loading) return;
    // Reveal after drawing; do not hide the date forever if the asset request stalls.
    const delay = trackRevealed || window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 3500;
    const t = setTimeout(() => setLayoutPhase("split"), delay);
    return () => clearTimeout(t);
  }, [trackRevealed, loading]);

  useEffect(() => {
    setExpandedFactIndex(0);
  }, [eventName]);

  const insights = getCircuitInsightsRu({
    season: raceSeason ?? undefined,
    eventName: eventName || "",
    country: raceCountry,
    location: raceCity,
    sessionsCount: sessions.length,
  });

  if (error || (!loading && !eventName)) return <>
    <BackButton fallback="/season" />
    <div className={error ? 'error' : 'loading'} role={error ? 'alert' : 'status'}>{error || title}</div>
  </>;

  return (
    <>
      <div className="next-race-mobile">
        <BackButton fallback="/season" />
        <h2>{title}</h2>
        <p style={{ marginBottom: 20, opacity: 0.7 }}>{location}</p>

        {(eventName || loading) && (
        <div className={`next-race-hero ${layoutPhase}`}>
          <div className="next-race-start-reveal" aria-hidden={layoutPhase === 'draw'}>
            <div className="next-race-start-block">
              <div className="next-race-start-copy">
                <div className="next-race-start-label">{isCancelled ? "СТАТУС ЭТАПА" : "СТАРТ ГОНКИ"}</div>
                <div className="next-race-date">{isCancelled ? "ОТМЕНЕН" : raceDateText}</div>
                <div className="next-race-time">{isCancelled ? "Организатор отменил проведение этапа" : raceTimeText}</div>
              </div>
            </div>
          </div>
          <div className="next-race-dash" aria-hidden />
          <div className="next-race-track-wrap">
            {eventName ? (
              <DetailedTrackMap key={`${eventName}:${raceSeason}`} eventName={eventName} location={raceCity} season={raceSeason ?? 0} preview={<AnimatedTrackMap
                eventName={eventName}
                location={raceCity}
                season={raceSeason ?? undefined}
                className="track-map-container next-race"
                svgClassName="next-race-mobile-track-svg"
                loadingClassName="next-race-track-loading"
                onRevealComplete={handleTrackRevealed}
              />} />
            ) : (
              !loading && <div className="no-map-placeholder">🏁</div>
            )}
          </div>
        </div>
        )}
        <h3 style={{ marginLeft: 4 }}>Расписание уикенда</h3>
        {!loading && !isCancelled && eventName && <CalendarDownload title={eventName} season={raceSeason ?? 0} round={raceRound ?? 0} sessions={sessions} />}
        <div className="standings-list">
          {loading && (
            <div className="loading">
              <div className="spinner" />
              <div>Загружаем расписание...</div>
            </div>
          )}
          {!loading && sessions.length === 0 && !error && (
            <div style={{ padding: 20, textAlign: "center" }}>Нет расписания</div>
          )}
          {!loading && <SessionSchedule sessions={sessions} />}
        </div>

        {!loading && eventName && (
          <>
            <StageResults season={raceSeason} round={raceRound} sessions={sessions} />
            <section className="next-race-stage-data-section">
              <div className="circuit-insights-card">
                <div className="circuit-insights-title">Данные по этапу</div>
                <div className="circuit-insights-stats">
                  {insights.stats.map((item) => (
                    <div className="circuit-stat-box" key={item.label}>
                      <div className="circuit-stat-label">{item.label}</div>
                      <div className="circuit-stat-value">{item.value}</div>
                      {item.hint ? <div className="circuit-stat-hint">{item.hint}</div> : null}
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <div className="circuit-insights-card">
              <div className="circuit-insights-title">Что знать перед этапом</div>
              <div className="circuit-facts-list">
                {insights.facts.map((fact, idx) => {
                  const expanded = expandedFactIndex === idx;
                  return (
                    <div className="circuit-fact-item" key={fact.title}>
                      <button
                        type="button"
                        className={`circuit-fact-header ${expanded ? "expanded" : ""}`}
                        onClick={() => setExpandedFactIndex(expanded ? -1 : idx)}
                      >
                        <span className="circuit-fact-title">{fact.title}</span>
                        <span className="circuit-fact-chevron">{expanded ? "▲" : "▼"}</span>
                      </button>
                      <div className={`circuit-fact-body ${expanded ? "expanded" : ""}`}>
                        <div className="circuit-fact-text"><GlossaryText>{fact.text}</GlossaryText></div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>

      {!loading && (eventName || title) && (
        <section className="next-race-desktop">
          <div className="next-race-desktop-main">
            <BackButton fallback="/season" />
            <header className="next-race-desktop-hero">
              <div className="next-race-desktop-left">
                <div className="next-race-desktop-round">
                  ЭТАП {String(raceRound || 0).padStart(2, "0")}
                </div>
                <h1>{(eventName || title).replace(/\s+Grand Prix$/i, "\nGrand Prix")}</h1>
                <div className="next-race-desktop-location">
                  <b>{raceCity || raceCountry}</b>
                  <span>{raceCountry || "Formula 1"}</span>
                </div>
                <div className="next-race-desktop-start">
                  <div>
                    <span>{isCancelled ? "Статус этапа" : "Дата гонки"}</span>
                    <strong>{isCancelled ? "Отменён" : raceDateText}</strong>
                  </div>
                  <div className="accent">
                    <span>{isCancelled ? "Решение организатора" : "Старт"}</span>
                    <strong>{isCancelled ? "—" : raceTimeText}</strong>
                  </div>
                </div>
              </div>
              <div className="next-race-desktop-track">
                <div
                  className={`next-race-desktop-track-panel ${eventName ? "track-panel-appear" : ""}`}
                >
                  <div className="next-race-desktop-track-caption">
                    <span>Схема трассы</span>
                    <b>{raceCity || eventName}</b>
                  </div>
                  {eventName ? (
                    <DetailedTrackMap key={`${eventName}:${raceSeason}`} eventName={eventName} location={raceCity} season={raceSeason ?? 0} preview={<AnimatedTrackMap
                      eventName={eventName}
                      location={raceCity}
                      season={raceSeason ?? undefined}
                      className="next-race-desktop-track-map"
                      svgClassName="next-race-desktop-track-svg"
                      loadingClassName="next-race-track-loading"
                    />} />
                  ) : (
                    <div className="no-map-placeholder">🏁</div>
                  )}
                </div>
              </div>
            </header>

            <div className="next-race-desktop-stats">
              {insights.stats.slice(0, 4).map((item) => (
                <article className="next-race-desktop-stat" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </article>
              ))}
            </div>

            <section className="next-race-desktop-schedule">
              <div className="next-race-desktop-schedule-head">
                <h2>Расписание</h2>
                <span>Время: {displayTimezone}</span>
              </div>
              {!isCancelled && eventName && <CalendarDownload title={eventName} season={raceSeason ?? 0} round={raceRound ?? 0} sessions={sessions} />}
              {sessions.length ? <SessionSchedule sessions={sessions} /> : <p>Нет расписания</p>}
            </section>
            <StageResults season={raceSeason} round={raceRound} sessions={sessions} />

            <section className="next-race-desktop-facts">
              <article className="next-race-desktop-overview">
                <div>
                  <h3>Обзор трассы</h3>
                  <p><GlossaryText>{insights.facts[0]?.text || "Подробности трассы появятся позже."}</GlossaryText></p>
                </div>
              </article>
              <div className="next-race-desktop-facts-list">
                {insights.facts.slice(1, 4).map((fact) => (
                  <div key={fact.title} className="next-race-desktop-fact-item">
                    <div className="next-race-desktop-fact-head">
                      <h6>{fact.title}</h6>
                      <span>⌄</span>
                    </div>
                    <p><GlossaryText>{fact.text}</GlossaryText></p>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </section>
      )}
    </>
  );
}

export default NextRacePage;
