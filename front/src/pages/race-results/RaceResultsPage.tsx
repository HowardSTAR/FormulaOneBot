import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
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
};

function RaceResultsPage() {
  const [data, setData] = useState<RaceResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await apiRequest<RaceResultsResponse>("/api/race-results");
        if (cancelled) return;
        setData(res);
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          setError(true);
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
      <Link to="/" className="btn-back">
        ← <span>Главное меню</span>
      </Link>
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

      <div id="race-content">
        {loading && (
          <div className="loading full-width">
            <div className="spinner" />
            <div>Загружаю результаты...</div>
          </div>
        )}
        {error && (
          <div style={{ color: "red", textAlign: "center", padding: 20 }}>Ошибка загрузки данных</div>
        )}
        {!loading && !error && (!data?.results || data.results.length === 0) && (
          <div className="empty-state">
            <span className="empty-icon">🏁</span>
            <div className="empty-title">Нет данных</div>
            <div className="empty-desc">
              Гонки в этом сезоне еще не проводились или результаты обрабатываются.
            </div>
          </div>
        )}
        {!loading && !error && data?.results && data.results.length > 0 && (
          <div className="standings-list" style={{ marginTop: 16 }}>
            {data.results.map((r, i) => {
              const emoji =
                r.position === 1 ? "🥇" : r.position === 2 ? "🥈" : r.position === 3 ? "🥉" : r.position;
              const favStyle =
                r.is_favorite_driver || r.is_favorite_team
                  ? { border: "1px solid rgba(255, 215, 0, 0.4)", background: "rgba(255, 215, 0, 0.05)" }
                  : {};
              return (
                <div key={i} className="standings-item" style={favStyle}>
                  <div
                    className={`standings-position ${r.position <= 3 ? "podium" : ""}`}
                    style={{ width: 35 }}
                  >
                    {emoji}
                  </div>
                  <div className="standings-info">
                    <div className="standings-name">
                      {r.is_favorite_driver ? "⭐️ " : ""}
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
