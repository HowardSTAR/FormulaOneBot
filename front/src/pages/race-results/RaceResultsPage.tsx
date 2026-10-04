import { resultStatus } from '../../helpers/presentation';
import { useSessionFilters } from '../../helpers/sessionFilters';
import { ResultsSeasonFilter } from '../../components/ResultsSeasonFilter';
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { CustomSelect } from "../../components/CustomSelect";
import { apiAssetUrl, apiRequest } from "../../helpers/api";
import { ResultsFeedback } from "../../components/SessionResultsUI";
import { RaceImpact } from '../../components/RaceImpact';
import { useRaceRecap } from '../../helpers/useRaceRecap';

type Result = {
  position: number;
  code: string;
  name: string;
  team: string;
  points: number;
  time?: string | null;
  gap?: string | null;
  status?: string | null;
  is_favorite_driver?: boolean;
  is_favorite_team?: boolean;
};
type RaceResultsResponse = {
  results?: Result[];
  race_info?: { event_name: string };
  round?: number;
  season?: number;
  data_incomplete?: boolean;
};
type SeasonRace = {
  round: number;
  event_name?: string;
};
type DriverTeamInfo = {
  code: string;
  driverId?: string;
  constructorId?: string;
  constructorName?: string;
};
type DriversResponse = { drivers?: DriverTeamInfo[] };

function pilotPortraitUrl(code: string, fullName: string, season: number): string {
  return apiAssetUrl("/api/pilot-portrait", {
    season,
    code,
    name: fullName,
  });
}

function teamLogoUrl(teamId: string, teamName: string, season: number): string {
  return apiAssetUrl("/api/team-logo", {
    team: teamId || teamName,
    name: teamName,
    season,
  });
}

function RaceResultsPage() {
  const navigate = useNavigate();
  const {season, setSeason, mode, setMode, selectedRound, setSelectedRound} = useSessionFilters(1950);
  const [attempt, setAttempt] = useState(0);

  const [data, setData] = useState<RaceResultsResponse | null>(null);
  const [resultLoading, setLoading] = useState(true);
  const [resultError, setError] = useState<string | null>(null);
  const [seasonLoading, setSeasonLoading] = useState(true);
  const [seasonError, setSeasonError] = useState<string | null>(null);
  const loading = resultLoading || (mode === 'archive' && seasonLoading);
  const error = resultError || (mode === 'archive' ? seasonError : null);
  const [seasonRaces, setSeasonRaces] = useState<SeasonRace[]>([]);
  const [driverTeams, setDriverTeams] = useState<Record<string, DriverTeamInfo>>({});

  const desktopWinner = data?.results?.[0] ?? null;
  const desktopRows = data?.results ?? [];
  const resultSeason = data?.season || season;
  const recap = useRaceRecap(resultSeason, data?.round || 0, Boolean(!loading && !error && data?.round && data.results?.length));
  const driverInfo = (driver: Result) => driverTeams[(driver.code || "").toUpperCase()];
  const teamName = (driver: Result) => driver.team || driverInfo(driver)?.constructorName || "Команда не указана";
  const openDriver = (driver: Result) => {
    const details = driverInfo(driver);
    const driverId = details?.driverId ? `&driverId=${encodeURIComponent(details.driverId)}` : "";
    navigate(`/driver-details?code=${encodeURIComponent(driver.code || "")}&season=${resultSeason}${driverId}`);
  };

  useEffect(() => {
    let cancelled = false;
    async function loadDriverTeams() {
      try {
        const response = await apiRequest<DriversResponse>("/api/drivers", { season: resultSeason });
        if (cancelled) return;
        const byCode = Object.fromEntries(
          (response.drivers || [])
            .filter((driver) => driver.code)
            .map((driver) => [driver.code.toUpperCase(), driver])
        );
        setDriverTeams(byCode);
      } catch {
        if (!cancelled) setDriverTeams({});
      }
    }
    loadDriverTeams();
    return () => {
      cancelled = true;
    };
  }, [resultSeason]);

  useEffect(() => {
    let cancelled = false;
    async function loadSeason() {
      setSeasonLoading(true); setSeasonError(null);
      try {
        const seasonData = await apiRequest<{ races?: SeasonRace[] }>("/api/season", {
          season,
          completed_only: true,
          session_type: "race",
        });
        if (cancelled) return;
        const races = (seasonData.races || [])
          .filter((r) => Number.isFinite(r.round) && r.round > 0)
          .sort((a, b) => b.round - a.round);
        setSeasonRaces(races);
        if (races.length > 0) {
          setSelectedRound((prev) => (prev && races.some((r) => r.round === prev) ? prev : races[0].round));
        } else {
          setSelectedRound(null);
        }
      } catch {
        if (!cancelled) {
          setSeasonRaces([]);
          setSelectedRound(null);
          setSeasonError('Не удалось загрузить список этапов. Попробуйте повторить запрос.');
        }
      } finally {
        if (!cancelled) setSeasonLoading(false);
      }
    }
    loadSeason();
    return () => {
      cancelled = true;
    };
  }, [season, attempt, setSelectedRound]);

  useEffect(() => {
    if (mode === "archive" && !selectedRound) { setLoading(false); setData(null); return; }
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await apiRequest<RaceResultsResponse>(
          "/api/race-results",
          mode === "archive"
            ? { season, round: selectedRound ?? undefined }
            : { season }
        );
        if (cancelled) return;
        setData(res);
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          const message = e instanceof Error ? e.message : "Ошибка загрузки данных";
          setError(message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [mode, selectedRound, season, attempt]);

  return (
    <>
      <ResultsSeasonFilter season={season} onChange={setSeason} minYear={1950} />
      <div className="race-results-mobile">
        <BackButton>← <span>Главное меню</span></BackButton>
        <h2 id="race-title">
          {data?.race_info ? (
            <>
              <div>Результаты гонки</div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: "var(--text-secondary)",
                  marginTop: 4,
                }}
              >
                {data.race_info.event_name}
                <br />
                <span style={{ opacity: 0.7 }}>
                  Этап {data.round} • {data.season}
                </span>
              </div>
            </>
          ) : (
            "Результаты гонки"
          )}
        </h2>

        <div className="segmented-tabs" style={{ marginBottom: 12 }}>
          <div
            className="segmented-slider"
            style={{ transform: mode === "archive" ? "translateX(100%)" : "translateX(0%)" }}
          />
          <button className={`segmented-tab ${mode === "latest" ? "active" : ""}`} onClick={() => setMode("latest")}>
            Последние
          </button>
          <button className={`segmented-tab ${mode === "archive" ? "active" : ""}`} onClick={() => setMode("archive")}>
            Архив
          </button>
        </div>
        {mode === "archive" && selectedRound && (
          <div style={{ marginBottom: 12 }}>
            <CustomSelect ariaLabel="Этап"
              options={seasonRaces.map((r) => ({
                value: r.round,
                label: `Этап ${String(r.round).padStart(2, "0")} · ${r.event_name || "Grand Prix"}`,
              }))}
              value={selectedRound}
              onChange={(value) => setSelectedRound(Number(value))}
            />
          </div>
        )}
        {mode === "archive" && (
          <div className="archive-note">Выберите сезон и этап выше.</div>
        )}

        <div id="race-content">
          <nav className="ui-section-links" aria-label="Содержание результатов"><a href="#race-classification">Классификация ↓</a></nav>

          <ResultsFeedback
            loading={loading}
            error={error}
            retry={() => setAttempt(v => v + 1)}
            empty={!loading && !error && (!data?.results || data.results.length === 0)}
            icon="🏁"
            title={data?.data_incomplete ? "Результаты обрабатываются" : "Нет данных"}
            description={data?.data_incomplete
              ? "Данные скоро появятся. Обновите страницу через несколько минут."
              : mode === "archive"
                ? "За выбранный этап результаты пока недоступны."
                : "Гонки в этом сезоне еще не проводились или результаты обрабатываются. Попробуйте режим Архив."}
          />
          {!loading && !error && data?.results && data.results.length > 0 && (
            <div id="race-classification" tabIndex={-1} className="standings-list" style={{ marginTop: 16 }}>
              {data.results.map((r, i) => {
                const emoji =
                  r.position === 1 ? "🥇" : r.position === 2 ? "🥈" : r.position === 3 ? "🥉" : r.position;
                const isFavorite = Boolean(r.is_favorite_driver || r.is_favorite_team);
                return (
                  <div
                    key={i}
                    className="standings-item"
                    role="link"
                    tabIndex={0}
                    onClick={() => openDriver(r)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") openDriver(r);
                    }}
                  >
                    <div
                      className={`standings-position ${r.position <= 3 ? "podium" : ""}`}
                      style={{ width: 35 }}
                    >
                      {emoji}
                    </div>
                    <div className="standings-info">
                      <div className="standings-name">
                        {isFavorite ? "⭐️ " : ""}
                        {r.name}
                      </div>
                      <div className="standings-code">{r.team}</div>
                    </div>
                    <div className="standings-points" style={{ minWidth: 40, textAlign: "center" }}>
                      {r.points > 0 ? r.points : ""}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {!loading && !error && data?.round && data.results?.length ? <details className="race-recap-fold"><summary>Обзор гонки и главные события</summary><RaceImpact season={resultSeason} round={data.round} rows={data.results} recap={recap} /></details> : null}
        </div>
      </div>

      <section className="race-results-desktop">
        <header className="race-results-desktop-head">
          <div>
            <div className="race-results-desktop-kicker">Скорость</div>
            <h1>Результаты гонки</h1>
            <p>
              {data?.race_info?.event_name || "Grand Prix"}
              {data?.round ? `, Этап ${data.round}` : ""}
              {data?.season ? ` • ${data.season}` : ""}
            </p>
          </div>
          <div className="race-results-desktop-controls">
            {mode === "archive" && selectedRound && (
              <div className="race-results-desktop-round-select">
                <CustomSelect ariaLabel="Этап"
                  options={seasonRaces.map((r) => ({
                    value: r.round,
                    label: `Этап ${String(r.round).padStart(2, "0")} · ${r.event_name || "Grand Prix"}`,
                  }))}
                  value={selectedRound}
                  onChange={(value) => setSelectedRound(Number(value))}
                />
              </div>
            )}
            <div className="segmented-tabs race-results-desktop-tabs">
              <div
                className="segmented-slider"
                style={{ transform: mode === "archive" ? "translateX(100%)" : "translateX(0%)" }}
              />
              <button className={`segmented-tab ${mode === "latest" ? "active" : ""}`} onClick={() => setMode("latest")}>
                Последние
              </button>
              <button className={`segmented-tab ${mode === "archive" ? "active" : ""}`} onClick={() => setMode("archive")}>
                Архив
              </button>
            </div>
          </div>
        </header>

        <div className="race-results-desktop-content">
          <nav className="ui-section-links" aria-label="Содержание результатов"><a href="#race-classification-desktop">Классификация ↓</a></nav>

          <ResultsFeedback
            loading={loading}
            error={error}
            retry={() => setAttempt(v => v + 1)}
            empty={!loading && !error && desktopRows.length === 0}
            icon="🏁"
            title={data?.data_incomplete ? "Результаты обрабатываются" : "Результаты пока недоступны"}
            description={data?.data_incomplete
              ? "Данные скоро появятся. Обновите страницу через несколько минут."
              : mode === "archive"
                ? "За выбранный этап результаты пока недоступны."
                : "После финиша здесь появятся победитель, команды и полная таблица результатов."}
          />
          {!loading && !error && desktopWinner && (
            <div className="race-results-desktop-hero-grid">
              <div className="race-results-desktop-winner">
                <div className="race-results-desktop-winner-overlay" />
                <div className="race-results-desktop-winner-copy">
                  <div className="race-results-desktop-winner-badge">Победитель</div>
                  <button
                    type="button"
                    className="race-results-desktop-winner-name"
                    onClick={() => openDriver(desktopWinner)}
                    title={`Открыть профиль: ${desktopWinner.name}`}
                  >
                    {desktopWinner.name}
                  </button>
                  <div className="race-results-desktop-winner-meta">
                    {desktopWinner.time || resultStatus(desktopWinner.status)}
                  </div>
                </div>
                <div className="race-results-desktop-winner-team">
                  <img
                    src={teamLogoUrl(driverInfo(desktopWinner)?.constructorId || "", teamName(desktopWinner), resultSeason)}
                    alt=""
                    onError={(e) => {
                      e.currentTarget.style.display = "none";
                    }}
                  />
                  <span>Команда-победитель</span>
                  <strong>{teamName(desktopWinner)}</strong>
                </div>
                <button
                  type="button"
                  className="race-results-desktop-winner-portrait-link"
                  onClick={() => openDriver(desktopWinner)}
                  aria-label={`Открыть профиль пилота ${desktopWinner.name}`}
                >
                  <img
                    className="race-results-desktop-winner-portrait"
                    src={pilotPortraitUrl(desktopWinner.code, desktopWinner.name, resultSeason)}
                    alt={desktopWinner.name || "Пилот"}
                    onError={(e) => {
                      e.currentTarget.style.display = "none";
                    }}
                  />
                </button>
              </div>
              <aside className="race-results-desktop-summary">
                <div className="race-results-desktop-summary-points">{desktopWinner.points}</div>
                <div className="race-results-desktop-summary-label">Набрано очков</div>
                <div className="race-results-desktop-summary-row"><span>Этап</span><b>{data?.round ?? "—"}</b></div>
                <div className="race-results-desktop-summary-row"><span>Сезон</span><b>{resultSeason}</b></div>
              </aside>
            </div>
          )}

          {!loading && !error && desktopRows.length > 0 && (
            <div id="race-classification-desktop" tabIndex={-1} className="race-results-desktop-table race-results-table-compact">
              <div className="race-results-desktop-table-head">
                <span>Поз</span>
                <span>Пилот</span>
                <span>Команда</span>
                <span>Время/статус</span>
                <span>Отставание</span>
              </div>
              {desktopRows.map((row) => {
                const rowDriverInfo = driverInfo(row);
                const rowTeam = teamName(row);
                return (
                  <div key={`${row.position}-${row.name}`} className={`race-results-desktop-row ${row.position === 1 ? "winner" : ""}`}>
                    <span className="race-results-position">{String(row.position).padStart(2, "0")}</span>
                    <button
                      type="button"
                      className="race-results-driver-cell"
                      onClick={() => openDriver(row)}
                      title={`Открыть профиль: ${row.name}`}
                    >
                      <img
                        src={pilotPortraitUrl(row.code, row.name, resultSeason)}
                        alt=""
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                        }}
                      />
                      <span>
                        <strong>{row.name}</strong>
                        <small>{row.code || "F1"}</small>
                      </span>
                    </button>
                    <div className="race-results-team-cell">
                      <img
                        src={teamLogoUrl(rowDriverInfo?.constructorId || "", rowTeam, resultSeason)}
                        alt=""
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                        }}
                      />
                      <span>{rowTeam}</span>
                    </div>
                    <span className="race-results-time">{row.time || resultStatus(row.status)}</span>
                    <span className="race-results-gap">{row.gap || "—"}</span>
                  </div>
                );
              })}
            </div>
          )}
          {!loading && !error && data?.round && data.results?.length ? <details className="race-recap-fold"><summary>Обзор гонки и главные события</summary><RaceImpact season={resultSeason} round={data.round} rows={data.results} recap={recap} /></details> : null}
        </div>
      </section>
    </>
  );
}

export default RaceResultsPage;
