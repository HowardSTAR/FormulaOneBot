import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { getNationalityWithFlag } from "../../constants/flags";

type SeasonStats = {
  position: number;
  points: number;
  grand_prix_races: number;
  grand_prix_points: number;
  grand_prix_wins: number;
  grand_prix_podiums: number;
  grand_prix_poles: number;
  grand_prix_top10s: number;
  fastest_laps: number;
  dnfs: number;
  sprint_races: number;
  sprint_points: number;
  sprint_wins: number;
  sprint_podiums: number;
  sprint_poles: number;
  sprint_top10s: number;
};

type CareerStats = {
  grand_prix_entered: number;
  career_points: number;
  highest_race_finish: { position: number | string; count: number };
  podiums: number;
  highest_grid: { position: number | string; count: number };
  pole_positions: number;
  world_championships: number;
  dnfs: number;
};

type DriverDetailsResponse = {
  driverId: string;
  code: string;
  givenName: string;
  familyName: string;
  permanentNumber: string;
  dateOfBirth: string;
  nationality: string;
  url: string;
  bio: string;
  headshot_url: string;
  season: number;
  season_stats: SeasonStats;
  career_stats: CareerStats;
};

function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="driver-stat-row">
      <span className="driver-stat-label">{label}</span>
      <span className="driver-stat-value">{value}</span>
    </div>
  );
}

function DriverDetailsPage() {
  const [searchParams] = useSearchParams();
  const code = searchParams.get("code");
  const driverId = searchParams.get("driverId");
  const seasonParam = searchParams.get("season");
  const season = seasonParam ? parseInt(seasonParam, 10) : new Date().getFullYear();

  const [data, setData] = useState<DriverDetailsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"stats" | "bio">("stats");

  useEffect(() => {
    const id = code || driverId;
    if (!id) {
      setError("Не указан пилот");
      setLoading(false);
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const params: Record<string, string | number> = { season };
        if (code) params.code = code;
        if (driverId) params.driverId = driverId;
        const res = await apiRequest<DriverDetailsResponse>("/api/driver-details", params);
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          setError("Ошибка загрузки карточки пилота");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [code, driverId, season]);

  if (error || (!code && !driverId)) {
    return (
      <>
        <BackButton fallback="/drivers">← <span>Личный зачет</span></BackButton>
        <div className="error">{error || "Не указан пилот"}</div>
      </>
    );
  }

  if (loading || !data) {
    return (
      <>
        <BackButton fallback="/drivers">← <span>Личный зачет</span></BackButton>
        <div className="loading full-width">
          <div className="spinner" />
          <div>Загрузка карточки пилота...</div>
        </div>
      </>
    );
  }

  const fullName = `${data.givenName} ${data.familyName}`;
  const ss = data.season_stats;
  const cs = data.career_stats;

  const formatHigh = (h: { position: number | string; count: number }) =>
    h.position === "-" ? "-" : `${h.position}${h.count > 1 ? ` (x${h.count})` : ""}`;

  return (
    <>
      <BackButton fallback="/drivers">← <span>Личный зачет</span></BackButton>

      <div className="driver-card-header">
        <div className="driver-portrait-wrap">
          <img
            src={data.headshot_url || "/api/pilot-portrait"}
            alt={fullName}
            className="driver-portrait"
            onError={(e) => {
              if (e.currentTarget.src !== window.location.origin + "/api/pilot-portrait") {
                e.currentTarget.src = "/api/pilot-portrait";
              }
            }}
          />
        </div>
        <div className="driver-card-info">
          <h2 className="driver-card-name">{fullName}</h2>
          <div className="driver-card-meta">
            {data.permanentNumber && <span className="driver-number-badge">#{data.permanentNumber}</span>}
            <span className="driver-code-badge">{data.code}</span>
          </div>
          {data.nationality && (
            <div className="driver-nationality">{getNationalityWithFlag(data.nationality)}</div>
          )}
        </div>
      </div>

      <div className="driver-tabs">
        <button
          type="button"
          className={`driver-tab ${tab === "stats" ? "active" : ""}`}
          onClick={() => setTab("stats")}
        >
          Статистика
        </button>
        <button
          type="button"
          className={`driver-tab ${tab === "bio" ? "active" : ""}`}
          onClick={() => setTab("bio")}
        >
          Биография
        </button>
      </div>

      {tab === "stats" && (
        <div className="driver-stats-grid">
          <div className="driver-stats-block">
            <h3 className="driver-stats-title">{data.season} СЕЗОН</h3>
            <StatRow label="Позиция в сезоне" value={ss.position || "-"} />
            <StatRow label="Очки сезона" value={ss.points} />
            <StatRow label="Гран-при (гонок)" value={ss.grand_prix_races} />
            <StatRow label="Очки в ГП" value={ss.grand_prix_points} />
            <StatRow label="Победы" value={ss.grand_prix_wins} />
            <StatRow label="Подиумы" value={ss.grand_prix_podiums} />
            <StatRow label="Поулы" value={ss.grand_prix_poles} />
            <StatRow label="Топ-10" value={ss.grand_prix_top10s} />
            <StatRow label="Быстрые круги" value={ss.fastest_laps} />
            <StatRow label="Сходы" value={ss.dnfs} />
            {ss.sprint_races > 0 && (
              <>
                <StatRow label="Спринты" value={ss.sprint_races} />
                <StatRow label="Очки в спринтах" value={ss.sprint_points} />
                <StatRow label="Победы в спринтах" value={ss.sprint_wins} />
                <StatRow label="Подиумы в спринтах" value={ss.sprint_podiums} />
                <StatRow label="Поулы в спринтах" value={ss.sprint_poles} />
                <StatRow label="Топ-10 в спринтах" value={ss.sprint_top10s} />
              </>
            )}
          </div>
          <div className="driver-stats-block">
            <h3 className="driver-stats-title">КАРЬЕРА</h3>
            <StatRow label="Гран-при (всего)" value={cs.grand_prix_entered} />
            <StatRow label="Карьерные очки" value={Math.round(cs.career_points)} />
            <StatRow label="Лучший финиш" value={formatHigh(cs.highest_race_finish)} />
            <StatRow label="Подиумы" value={cs.podiums} />
            <StatRow label="Лучшая позиция на старте" value={formatHigh(cs.highest_grid)} />
            <StatRow label="Поулы" value={cs.pole_positions} />
            <StatRow label="Чемпионства" value={cs.world_championships} />
            <StatRow label="Сходы" value={cs.dnfs} />
          </div>
        </div>
      )}

      {tab === "bio" && (
        <div className="driver-bio-block">
          {data.bio ? (
            <p className="driver-bio-text">{data.bio}</p>
          ) : (
            <p className="driver-bio-empty">Биография пока недоступна.</p>
          )}
          {data.url && (
            <a
              href={data.url}
              target="_blank"
              rel="noopener noreferrer"
              className="driver-bio-link"
            >
              Открыть в Wikipedia →
            </a>
          )}
        </div>
      )}
    </>
  );
}

export default DriverDetailsPage;
