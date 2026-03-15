import { useState, useEffect } from "react";
import { BackButton } from "../../components/BackButton";
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

function SprintQualiResultsPage() {
  const [data, setData] = useState<SprintQualiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await apiRequest<SprintQualiResponse>("/api/sprint-quali-results");
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
  }, []);

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
          <div className="empty-desc">Результаты спринт-квалификации пока недоступны.</div>
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
