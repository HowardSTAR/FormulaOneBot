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
type SprintResultsResponse = {
  results?: Result[];
  race_info?: { event_name: string };
  round?: number;
  season?: number;
};

function SprintResultsPage() {
  const [data, setData] = useState<SprintResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await apiRequest<SprintResultsResponse>("/api/sprint-results");
        if (cancelled) return;
        setData(res);
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          setError(e instanceof Error ? e.message : "Ошибка загрузки данных");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
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

      {loading && (
        <div className="loading full-width">
          <div className="spinner" />
          <div>Загружаю результаты...</div>
        </div>
      )}
      {error && <div style={{ color: "red", textAlign: "center", padding: 20 }}>{error}</div>}
      {!loading && !error && (!data?.results || data.results.length === 0) && (
        <div className="empty-state">
          <span className="empty-icon">⚡</span>
          <div className="empty-title">Нет данных</div>
          <div className="empty-desc">Результаты спринта пока недоступны.</div>
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
                <div className={`standings-position ${r.position <= 3 ? "podium" : ""}`} style={{ width: 35 }}>
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
    </>
  );
}

export default SprintResultsPage;
