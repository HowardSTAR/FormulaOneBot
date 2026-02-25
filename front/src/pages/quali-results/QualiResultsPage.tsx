import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";

type Result = { position: number; name?: string; driver?: string; best?: string };
type QualiResponse = {
  results?: Result[];
  race_info?: { event_name: string };
  round?: number;
  season?: number;
};

function QualiResultsPage() {
  const [data, setData] = useState<QualiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await apiRequest<QualiResponse>("/api/quali-results");
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
      <Link to="/" className="btn-back">
        ← <span>Главное меню</span>
      </Link>
      <h2 id="quali-title">
        {data?.race_info ? (
          <>
            <div>Квалификация</div>
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
          "Квалификация"
        )}
      </h2>

      <div id="quali-content">
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
            <span className="empty-icon">⏱</span>
            <div className="empty-title">Нет данных</div>
            <div className="empty-desc">Результаты квалификации пока недоступны.</div>
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
                    <div className="standings-name">{r.name || r.driver}</div>
                    <div className="standings-code">{r.driver}</div>
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
      </div>
    </>
  );
}

export default QualiResultsPage;
