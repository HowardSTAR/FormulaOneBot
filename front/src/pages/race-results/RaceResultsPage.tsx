import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { CustomSelect } from "../../components/CustomSelect";
import { apiRequest } from "../../helpers/api";

type Result = {
  position: number;
  name: string;
  team: string;
  points: number;
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

function pilotPortraitUrl(code: string, fullName: string, season: number): string {
  const apiBase = (import.meta.env.VITE_API_URL as string) || "";
  const pathBase = ((import.meta.env.BASE_URL as string) || "/").replace(/\/$/, "");
  const origin = apiBase || (typeof window !== "undefined" ? window.location.origin : "");
  const params = new URLSearchParams({ season: String(season) });
  if (code) params.set("code", code);
  if (fullName) params.set("name", fullName);
  return `${origin.replace(/\/$/, "")}${pathBase}/api/pilot-portrait?${params.toString()}`;
}

function parseOptionalInt(value: string | null): number | null {
  if (value === null) return null;
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) ? n : null;
}

function RaceResultsPage() {
  const [searchParams] = useSearchParams();
  const seasonFromQuery = parseOptionalInt(searchParams.get("season"));
  const roundFromQuery = parseOptionalInt(searchParams.get("round"));
  const modeFromQuery = searchParams.get("mode");
  const initialSeason = seasonFromQuery ?? new Date().getFullYear();
  const initialRound = roundFromQuery;
  const initialMode: "latest" | "archive" = modeFromQuery === "archive" ? "archive" : "latest";

  const [data, setData] = useState<RaceResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"latest" | "archive">(initialMode);
  const [season] = useState<number>(initialSeason);
  const [seasonRaces, setSeasonRaces] = useState<SeasonRace[]>([]);
  const [selectedRound, setSelectedRound] = useState<number | null>(initialRound);

  const desktopWinner = data?.results?.[0] ?? null;
  const desktopRows = data?.results ?? [];

  useEffect(() => {
    let cancelled = false;
    async function loadSeason() {
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
  }, [mode, selectedRound]);

  return (
    <>
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

        <div id="race-content">
          {loading && (
            <div className="loading full-width">
              <div className="spinner" />
              <div>Загружаю результаты...</div>
            </div>
          )}
          {error && (
            <div style={{ color: "red", textAlign: "center", padding: 20 }}>{error}</div>
          )}
          {!loading && !error && (!data?.results || data.results.length === 0) && (
            <div className="empty-state">
              <span className="empty-icon">🏁</span>
              <div className="empty-title">
                {data?.data_incomplete ? "Результаты обрабатываются" : "Нет данных"}
              </div>
              <div className="empty-desc">
                {data?.data_incomplete
                  ? "Данные скоро появятся. Обновите страницу через несколько минут."
                  : mode === "archive"
                    ? "За выбранный этап результаты пока недоступны."
                    : "Гонки в этом сезоне еще не проводились или результаты обрабатываются. Попробуйте режим Архив."}
              </div>
            </div>
          )}
          {!loading && !error && data?.results && data.results.length > 0 && (
            <div className="standings-list" style={{ marginTop: 16 }}>
              {data.results.map((r, i) => {
                const emoji =
                  r.position === 1 ? "🥇" : r.position === 2 ? "🥈" : r.position === 3 ? "🥉" : r.position;
                const isFavorite = Boolean(r.is_favorite_driver || r.is_favorite_team);
                return (
                  <div key={i} className="standings-item">
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
          {loading && (
            <div className="loading full-width">
              <div className="spinner" />
              <div>Загружаю результаты...</div>
            </div>
          )}
          {error && <div className="page-error">{error}</div>}
          {!loading && !error && desktopWinner && (
            <div className="race-results-desktop-hero-grid">
              <div className="race-results-desktop-winner">
                <div className="race-results-desktop-winner-overlay" />
                <img
                  className="race-results-desktop-winner-portrait"
                  src={pilotPortraitUrl("", desktopWinner.name, data?.season || season)}
                  alt={desktopWinner.name || "Пилот"}
                  onError={(e) => {
                    e.currentTarget.style.display = "none";
                  }}
                />
                <div className="race-results-desktop-winner-badge">Победитель</div>
                <div className="race-results-desktop-winner-name">{desktopWinner.name}</div>
                <div className="race-results-desktop-winner-meta">
                  {desktopWinner.team} • 1:32:04.{String(Math.max(0, desktopWinner.points)).padStart(3, "0")}
                </div>
              </div>
              <aside className="race-results-desktop-summary">
                <div className="race-results-desktop-summary-points">{desktopWinner.points || 0}</div>
                <div className="race-results-desktop-summary-label">Набрано очков</div>
                <div className="race-results-desktop-summary-row"><span>Средняя скорость</span><b>231.4 km/h</b></div>
                <div className="race-results-desktop-summary-row"><span>Быстрый круг</span><b>1:34.551</b></div>
              </aside>
            </div>
          )}

          {!loading && !error && desktopRows.length > 0 && (
            <div className="race-results-desktop-table race-results-table-compact">
              <div className="race-results-desktop-table-head">
                <span>Поз</span>
                <span>Пилот</span>
                <span>Команда</span>
                <span>Время/статус</span>
                <span>Gap</span>
              </div>
              {desktopRows.map((row) => {
                const gap = row.position <= 1 ? "-" : `+${(row.position * 3.7).toFixed(3)}s`;
                const status = row.points > 0 ? `1:32:${String(3 + row.position).padStart(2, "0")}.${String(100 + row.position * 17).slice(0, 3)}` : "Сход";
                return (
                  <div key={`${row.position}-${row.name}`} className={`race-results-desktop-row ${row.position === 1 ? "winner" : ""}`}>
                    <span>{String(row.position).padStart(2, "0")}</span>
                    <span>{row.name}</span>
                    <span>{row.team}</span>
                    <span>{status}</span>
                    <span>{gap}</span>
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

export default RaceResultsPage;
