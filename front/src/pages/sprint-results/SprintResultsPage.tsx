import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { CustomSelect } from "../../components/CustomSelect";
import { apiAssetUrl, apiRequest } from "../../helpers/api";
import { ResultsFeedback, ResultsMobileRow } from "../../components/SessionResultsUI";

type Result = {
  position: number;
  code?: string;
  name: string;
  team: string;
  points: number;
  time?: string;
  gap?: string;
  status?: string;
  is_favorite_driver?: boolean;
  is_favorite_team?: boolean;
};
type SprintResultsResponse = {
  results?: Result[];
  race_info?: { event_name: string };
  round?: number;
  season?: number;
};
type SeasonRace = {
  round: number;
  event_name?: string;
  is_sprint_weekend?: boolean;
  sprint_start_utc?: string | null;
  sprint_quali_start_utc?: string | null;
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

function parseOptionalInt(value: string | null): number | null {
  if (value === null) return null;
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) ? n : null;
}

function SprintResultsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const seasonFromQuery = parseOptionalInt(searchParams.get("season"));
  const roundFromQuery = parseOptionalInt(searchParams.get("round"));
  const modeFromQuery = searchParams.get("mode");
  const initialSeason = seasonFromQuery ?? new Date().getFullYear();
  const initialRound = roundFromQuery;
  const initialMode: "latest" | "archive" = modeFromQuery === "archive" ? "archive" : "latest";

  const [data, setData] = useState<SprintResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"latest" | "archive">(initialMode);
  const [season] = useState<number>(initialSeason);
  const [seasonRaces, setSeasonRaces] = useState<SeasonRace[]>([]);
  const [selectedRound, setSelectedRound] = useState<number | null>(initialRound);
  const [driverTeams, setDriverTeams] = useState<Record<string, DriverTeamInfo>>({});
  const desktopWinner = data?.results?.[0] ?? null;
  const desktopRows = data?.results ?? [];
  const resultSeason = data?.season || season;
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
        setDriverTeams(Object.fromEntries(
          (response.drivers || [])
            .filter((driver) => driver.code)
            .map((driver) => [driver.code.toUpperCase(), driver]),
        ));
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
      try {
        const seasonData = await apiRequest<{ races?: SeasonRace[] }>("/api/season", {
          season,
          completed_only: true,
          session_type: "sprint",
        });
        if (cancelled) return;
        const races = (seasonData.races || [])
          .filter((r) => (
            Number.isFinite(r.round)
            && r.round > 0
            && Boolean(r.is_sprint_weekend || r.sprint_start_utc || r.sprint_quali_start_utc)
          ))
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
        }
      }
    }
    loadSeason();
    return () => {
      cancelled = true;
    };
  }, [season]);

  useEffect(() => {
    if (mode === "archive" && !selectedRound) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await apiRequest<SprintResultsResponse>(
          "/api/sprint-results",
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
          if (message.includes("время ожидания") || message.includes("timed out")) {
            setData({ results: [] });
            setError(null);
          } else {
            setError(message);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [mode, selectedRound, season]);

  return (
    <>
      <div className="sprint-results-mobile">
        <BackButton>← <span>Главное меню</span></BackButton>
        <h2>
          {data?.race_info ? (
            <>
              <div>Результаты спринта</div>
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
            "Результаты спринта"
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
            <CustomSelect
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
          <div className="archive-note">Результаты других ГП можно открыть в разделе Календарь.</div>
        )}

        <div id="sprint-content">
          <ResultsFeedback
            loading={loading}
            error={error}
            empty={!loading && !error && (!data?.results || data.results.length === 0)}
            icon="⚡"
            description={mode === "archive"
              ? "За выбранный этап результаты спринта пока недоступны."
              : "Результаты спринта пока недоступны. Попробуйте режим Архив."}
          />
          {!loading && !error && data?.results && data.results.length > 0 && (
            <div className="standings-list" style={{ marginTop: 16 }}>
              {data.results.map((r, i) => {
                const isFavorite = Boolean(r.is_favorite_driver || r.is_favorite_team);
                return (
                  <ResultsMobileRow
                    key={i}
                    position={r.position}
                    name={r.name}
                    code={r.code}
                    team={r.team}
                    favorite={isFavorite}
                    value={r.position === 1 ? (r.time || r.status || "—") : (r.gap || r.status || "—")}
                  />
                );
              })}
            </div>
          )}
        </div>
      </div>

      <section className="race-results-desktop">
        <header className="race-results-desktop-head">
          <div>
            <div className="race-results-desktop-kicker">Скорость</div>
            <h1>Результаты спринта</h1>
            <p>
              {data?.race_info?.event_name || "Grand Prix"}
              {data?.round ? `, Этап ${data.round}` : ""}
              {data?.season ? ` • ${data.season}` : ""}
            </p>
          </div>
          <div className="race-results-desktop-controls">
            {mode === "archive" && selectedRound && (
              <div className="race-results-desktop-round-select">
                <CustomSelect
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
              <div className="segmented-slider" style={{ transform: mode === "archive" ? "translateX(100%)" : "translateX(0%)" }} />
              <button className={`segmented-tab ${mode === "latest" ? "active" : ""}`} onClick={() => setMode("latest")}>Последние</button>
              <button className={`segmented-tab ${mode === "archive" ? "active" : ""}`} onClick={() => setMode("archive")}>Архив</button>
            </div>
          </div>
        </header>

        <div className="race-results-desktop-content">
          <ResultsFeedback
            loading={loading}
            error={error}
            empty={!loading && !error && desktopRows.length === 0}
            icon="⚡"
            title="Спринт ещё не завершён"
            description={mode === "archive" ? "За выбранный этап результаты пока недоступны." : "После финиша здесь появится полная классификация спринта."}
          />
          {!loading && !error && desktopWinner && (
            <div className="race-results-desktop-hero-grid">
              <div className="race-results-desktop-winner">
                <div className="race-results-desktop-winner-overlay" />
                <div className="race-results-desktop-winner-copy">
                  <div className="race-results-desktop-winner-badge">Победитель спринта</div>
                  <button
                    type="button"
                    className="race-results-desktop-winner-name"
                    onClick={() => openDriver(desktopWinner)}
                    title={`Открыть профиль: ${desktopWinner.name}`}
                  >
                    {desktopWinner.name}
                  </button>
                  <div className="race-results-desktop-winner-meta">
                    {desktopWinner.time || desktopWinner.status || "Классификация спринта"}
                  </div>
                </div>
                <div className="race-results-desktop-winner-team">
                  <img
                    src={teamLogoUrl(
                      driverInfo(desktopWinner)?.constructorId || "",
                      teamName(desktopWinner),
                      resultSeason,
                    )}
                    alt=""
                    onError={(event) => {
                      event.currentTarget.style.display = "none";
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
                    src={pilotPortraitUrl(desktopWinner.code || "", desktopWinner.name, resultSeason)}
                    alt={desktopWinner.name || "Пилот"}
                    onError={(event) => {
                      event.currentTarget.style.display = "none";
                    }}
                  />
                </button>
              </div>
              <aside className="race-results-desktop-summary">
                <div className="race-results-desktop-summary-points">{desktopWinner.points || 0}</div>
                <div className="race-results-desktop-summary-label">Набрано очков</div>
                <div className="race-results-desktop-summary-row"><span>Время победителя</span><b>{desktopWinner.time || "—"}</b></div>
                <div className="race-results-desktop-summary-row"><span>Статус</span><b>{desktopWinner.status || "Финишировал"}</b></div>
              </aside>
            </div>
          )}
          {!loading && !error && desktopRows.length > 0 && (
            <div className="race-results-desktop-table race-results-table-compact">
              <div className="race-results-desktop-table-head">
                <span>Поз</span>
                <span>Пилот</span>
                <span>Команда</span>
                <span>Время / Gap</span>
                <span>Очки</span>
              </div>
              {desktopRows.map((row) => {
                const rowDriverInfo = driverInfo(row);
                const rowTeam = teamName(row);
                return (
                  <div
                    key={`${row.position}-${row.name}`}
                    className={`race-results-desktop-row ${row.position === 1 ? "winner" : ""}`}
                  >
                    <span className="race-results-position">{String(row.position).padStart(2, "0")}</span>
                    <button
                      type="button"
                      className="race-results-driver-cell"
                      onClick={() => openDriver(row)}
                      title={`Открыть профиль: ${row.name}`}
                    >
                      <img
                        src={pilotPortraitUrl(row.code || "", row.name, resultSeason)}
                        alt=""
                        onError={(event) => {
                          event.currentTarget.style.display = "none";
                        }}
                      />
                      <span>
                        <strong>{(row.is_favorite_driver || row.is_favorite_team) ? "★ " : ""}{row.name}</strong>
                        <small>{row.code || "F1"}</small>
                      </span>
                    </button>
                    <div className="race-results-team-cell">
                      <img
                        src={teamLogoUrl(rowDriverInfo?.constructorId || "", rowTeam, resultSeason)}
                        alt=""
                        onError={(event) => {
                          event.currentTarget.style.display = "none";
                        }}
                      />
                      <span>{rowTeam}</span>
                    </div>
                    <span className="race-results-time">
                      {row.position === 1 ? (row.time || row.status || "—") : (row.gap || row.status || "—")}
                    </span>
                    <span className="race-results-points">{row.points}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </>
  );
}

export default SprintResultsPage;
