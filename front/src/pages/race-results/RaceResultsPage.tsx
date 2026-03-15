import { useState, useEffect } from "react";
import { BackButton } from "../../components/BackButton";
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

function RaceResultsPage() {
  const [data, setData] = useState<RaceResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"latest" | "archive">("latest");
  const [seasonRaces, setSeasonRaces] = useState<SeasonRace[]>([]);
  const [selectedRound, setSelectedRound] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadSeason() {
      try {
        const seasonData = await apiRequest<{ races?: SeasonRace[] }>("/api/season", {
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
  }, []);

  useEffect(() => {
    if (mode === "archive" && !selectedRound) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await apiRequest<RaceResultsResponse>(
          "/api/race-results",
          mode === "archive" ? { round: selectedRound ?? undefined } : {}
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

      <div className="segmented-control" style={{ marginBottom: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <button className={`btn ${mode === "latest" ? "active" : ""}`} onClick={() => setMode("latest")}>
          Последние
        </button>
        <button className={`btn ${mode === "archive" ? "active" : ""}`} onClick={() => setMode("archive")}>
          Архив
        </button>
        {mode === "archive" && (
          <select
            value={selectedRound ?? ""}
            onChange={(e) => setSelectedRound(Number(e.target.value))}
            style={{ minWidth: 220 }}
          >
            {seasonRaces.map((r) => (
              <option key={r.round} value={r.round}>
                Этап {String(r.round).padStart(2, "0")} · {r.event_name || "Grand Prix"}
              </option>
            ))}
          </select>
        )}
      </div>
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
    </>
  );
}

export default RaceResultsPage;
