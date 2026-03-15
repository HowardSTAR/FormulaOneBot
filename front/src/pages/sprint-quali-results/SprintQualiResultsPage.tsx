import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { CustomSelect } from "../../components/CustomSelect";
import { apiRequest } from "../../helpers/api";

type Result = {
  position: number;
  name?: string;
  driver?: string;
  best?: string;
  segment?: "Q1" | "Q2" | "Q3";
  is_favorite_driver?: boolean;
};
type SprintQualiResponse = {
  results?: Result[];
  race_info?: { event_name: string };
  round?: number;
  season?: number;
};
type SeasonRace = {
  round: number;
  event_name?: string;
};

function parseOptionalInt(value: string | null): number | null {
  if (value === null) return null;
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) ? n : null;
}

function SprintQualiResultsPage() {
  const [searchParams] = useSearchParams();
  const seasonFromQuery = parseOptionalInt(searchParams.get("season"));
  const roundFromQuery = parseOptionalInt(searchParams.get("round"));
  const modeFromQuery = searchParams.get("mode");
  const initialSeason = seasonFromQuery ?? new Date().getFullYear();
  const initialRound = roundFromQuery;
  const initialMode: "latest" | "archive" = modeFromQuery === "archive" ? "archive" : "latest";

  const [data, setData] = useState<SprintQualiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"latest" | "archive">(initialMode);
  const [season] = useState<number>(initialSeason);
  const [seasonRaces, setSeasonRaces] = useState<SeasonRace[]>([]);
  const [selectedRound, setSelectedRound] = useState<number | null>(initialRound);

  useEffect(() => {
    let cancelled = false;
    async function loadSeason() {
      try {
        const seasonData = await apiRequest<{ races?: SeasonRace[] }>("/api/season", {
          season,
          completed_only: true,
          session_type: "sprint_quali",
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
        const res = await apiRequest<SprintQualiResponse>(
          "/api/sprint-quali-results",
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
      <BackButton>← <span>Главное меню</span></BackButton>
      <h2>
        {data?.race_info && data.round != null ? (
          <>
            <div>Спринт-квалификация · Этап {String(data.round).padStart(2, "0")}. {data.race_info.event_name}</div>
            <div
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: "var(--text-secondary)",
                marginTop: 4,
              }}
            >
              <span style={{ opacity: 0.7 }}>Сезон {data.season}</span>
            </div>
          </>
        ) : (
          "Спринт-квалификация"
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

      {loading && (
        <div className="loading full-width">
          <div className="spinner" />
          <div>Загружаю результаты...</div>
        </div>
      )}
      {error && <div style={{ color: "red", textAlign: "center", padding: 20 }}>{error}</div>}
      {!loading && !error && (!data?.results || data.results.length === 0) && (
        <div className="empty-state">
          <span className="empty-icon">⏱</span>
          <div className="empty-title">Нет данных</div>
          <div className="empty-desc">
            {mode === "archive"
              ? "За выбранный этап результаты спринт-квалификации пока недоступны."
              : "Результаты спринт-квалификации пока недоступны. Попробуйте режим Архив."}
          </div>
        </div>
      )}
      {!loading && !error && data?.results && data.results.length > 0 && (
        <div className="standings-list" style={{ marginTop: 16 }}>
          {data.results.map((r, i) => {
            const emoji =
              r.position === 1 ? "🥇" : r.position === 2 ? "🥈" : r.position === 3 ? "🥉" : r.position;
            return (
              <div key={i} className="standings-item">
                <div
                  className="standings-position"
                  style={{
                    width: 35,
                    color: r.position <= 3 ? "var(--text-primary)" : undefined,
                  }}
                >
                  {emoji}
                </div>
                <div className="standings-info">
                  <div className="standings-name">
                    {r.is_favorite_driver ? "⭐️ " : ""}
                    {r.name || r.driver}
                  </div>
                  <div className="standings-code" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {r.driver}
                    {r.segment && (
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          padding: "2px 6px",
                          borderRadius: 4,
                          background:
                            r.segment === "Q3"
                              ? "rgba(34, 197, 94, 0.25)"
                              : r.segment === "Q2"
                                ? "rgba(59, 130, 246, 0.25)"
                                : "rgba(156, 163, 175, 0.25)",
                          color:
                            r.segment === "Q3"
                              ? "rgb(34, 197, 94)"
                              : r.segment === "Q2"
                                ? "rgb(96, 165, 250)"
                                : "rgb(156, 163, 175)",
                        }}
                      >
                        {r.segment}
                      </span>
                    )}
                  </div>
                </div>
                <div
                  className="standings-time"
                  style={{
                    fontFamily: "monospace",
                    fontSize: 14,
                    background: "rgba(255,255,255,0.05)",
                    padding: "4px 8px",
                    borderRadius: 6,
                  }}
                >
                  {r.best || "—"}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

export default SprintQualiResultsPage;
