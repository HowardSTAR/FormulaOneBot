import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { getFlagUrlForNationality } from "../../constants/flags";

function pilotPortraitUrl(code: string, fullName: string, season: number): string {
  const apiBase = (import.meta.env.VITE_API_URL as string) || "";
  const pathBase = ((import.meta.env.BASE_URL as string) || "/").replace(/\/$/, "");
  const origin = apiBase || (typeof window !== "undefined" ? window.location.origin : "");
  const params = new URLSearchParams({ season: String(season) });
  if (code) params.set("code", code);
  if (fullName) params.set("name", fullName);
  return `${origin.replace(/\/$/, "")}${pathBase}/api/pilot-portrait?${params.toString()}`;
}

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
type DriversListItem = {
  code?: string;
  driverId?: string;
  constructorName?: string;
};
type DriversListResponse = { drivers?: DriversListItem[] };

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
  const [teamName, setTeamName] = useState<string>("Formula One Team");

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
        const [res, driversRes] = await Promise.all([
          apiRequest<DriverDetailsResponse>("/api/driver-details", params),
          apiRequest<DriversListResponse>("/api/drivers", { season }).catch(() => ({ drivers: [] })),
        ]);
        if (!cancelled) {
          setData(res);
          const match = (driversRes.drivers || []).find(
            (d) =>
              (res.code && d.code === res.code) ||
              (res.driverId && d.driverId && d.driverId === res.driverId) ||
              (code && d.code === code)
          );
          if (match?.constructorName) setTeamName(match.constructorName);
        }
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
  const nationalityFlagUrl = getFlagUrlForNationality(data.nationality);
  const ss = data.season_stats;
  const cs = data.career_stats;
  const firstName = data.givenName.toUpperCase();
  const lastName = data.familyName.toUpperCase();
  const teamLabel =
    teamName === "Formula One Team" && data.code === "ANT"
      ? "Mercedes-AMG Petronas F1 Team"
      : teamName;

  const formatHigh = (h: { position: number | string; count: number }) =>
    h.position === "-" ? "-" : `${h.position}${h.count > 1 ? ` (x${h.count})` : ""}`;

  return (
    <>
      <div className="driver-details-mobile">
        <BackButton fallback="/drivers">← <span>Личный зачет</span></BackButton>

        <div className="driver-card-header">
          <div className="driver-portrait-wrap">
            <img
              src={pilotPortraitUrl(data.code, fullName, season)}
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
              <div className="driver-nationality">
                {nationalityFlagUrl && (
                  <img
                    src={nationalityFlagUrl}
                    alt={data.nationality}
                    className="country-flag-svg"
                  />
                )}
                <span>{data.nationality}</span>
              </div>
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
      </div>

      <section className="driver-profile-desktop">
        <header className="driver-profile-desktop-hero">
          <div className="driver-profile-desktop-photo">
            <img src={pilotPortraitUrl(data.code, fullName, season)} alt={fullName} />
          </div>
          <div className="driver-profile-desktop-overlay" />
          <div className="driver-profile-desktop-content">
            <div className="driver-profile-desktop-number">{data.permanentNumber || "--"}</div>
            <h1>
              <span>{firstName}</span>
              <em>{lastName}</em>
            </h1>
            <div className="driver-profile-desktop-team">
              <b>{data.code}</b>
              <span>{teamLabel}</span>
            </div>
          </div>
          <aside className="driver-profile-desktop-rank">
            <div><span>Rank</span><strong>P{ss.position || 0}</strong></div>
            <div><span>Points</span><strong>{ss.points}</strong></div>
            <div><span>Wins</span><strong>{ss.grand_prix_wins}</strong></div>
          </aside>
        </header>

        <div className="driver-profile-desktop-grid">
          <section className="driver-profile-desktop-main">
            <h3 className="driver-profile-title">Performance Analytics</h3>
            <div className="driver-profile-season-cards">
              <article><span>Position</span><strong>{ss.position || "-"}</strong><small>Current standing</small></article>
              <article><span>Points</span><strong>{ss.points}</strong><small>Season total</small></article>
              <article><span>Podiums</span><strong>{ss.grand_prix_podiums}</strong><small>Grand Prix</small></article>
              <article><span>GPs entered</span><strong>{ss.grand_prix_races}</strong><small>{season} season</small></article>
            </div>
            <div className="driver-profile-career-grid">
              <article className="driver-profile-career-card">
                <h4>Career Summary</h4>
                <div><span>Grand Prix Entries</span><b>{cs.grand_prix_entered}</b></div>
                <div><span>Total Points</span><b>{Math.round(cs.career_points)}</b></div>
                <div><span>Best Finish</span><b>{formatHigh(cs.highest_race_finish)}</b></div>
              </article>
              <article className="driver-profile-accolades-card">
                <h4>Accolades</h4>
                <p>Highest Grid Pos: {formatHigh(cs.highest_grid)}</p>
                <small>Born: {data.dateOfBirth || "N/A"}</small>
              </article>
            </div>
          </section>
          <aside className="driver-profile-desktop-bio">
            <h3 className="driver-profile-title">Biography</h3>
            <div className="driver-profile-bio-card">
              <p>{data.bio || "Biography is not available yet."}</p>
              <div className="driver-profile-bio-meta">
                <div>
                  <span>Nationality</span>
                  <b>{data.nationality}</b>
                </div>
                <div>
                  <span>First GP</span>
                  <b>{String(Math.max(1950, season - 1))}</b>
                </div>
              </div>
            </div>
            <button type="button" className="driver-profile-records-btn">View all records</button>
          </aside>
        </div>

        <section className="driver-profile-desktop-recent">
          <h3 className="driver-profile-title">Recent Performance</h3>
          <div className="driver-profile-recent-strip">
            <article>
              <span>Latest Result</span>
              <b>{ss.position === 1 ? "Race Winner" : `P${ss.position}`}</b>
            </article>
            <article>
              <span>Best Grid</span>
              <b>{formatHigh(cs.highest_grid)}</b>
            </article>
            <article>
              <span>Points</span>
              <b>{ss.points}</b>
            </article>
          </div>
        </section>
      </section>
    </>
  );
}

export default DriverDetailsPage;
