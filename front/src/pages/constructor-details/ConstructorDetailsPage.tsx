import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { NATIONALITY_FLAGS } from "../../constants/flags";

function teamLogoUrl(teamId: string, teamName: string, season: number): string {
  const apiBase = (import.meta.env.VITE_API_URL as string) || "";
  const pathBase = ((import.meta.env.BASE_URL as string) || "/").replace(/\/$/, "");
  const origin = apiBase || (typeof window !== "undefined" ? window.location.origin : "");
  const team = teamId || teamName;
  const params = new URLSearchParams({ team, season: String(season) });
  if (teamName) params.set("name", teamName);
  return `${origin.replace(/\/$/, "")}${pathBase}/api/team-logo?${params}`;
}

function carImageUrl(teamName: string, season: number): string {
  const apiBase = (import.meta.env.VITE_API_URL as string) || "";
  const pathBase = ((import.meta.env.BASE_URL as string) || "/").replace(/\/$/, "");
  const origin = apiBase || (typeof window !== "undefined" ? window.location.origin : "");
  const params = new URLSearchParams({ team: teamName, season: String(season) });
  return `${origin.replace(/\/$/, "")}${pathBase}/api/car-image?${params}`;
}

type SeasonStats = {
  position: number | string;
  points: number;
  grand_prix_races: number;
  grand_prix_wins: number;
  grand_prix_podiums: number;
  grand_prix_poles: number;
};

type CareerStats = {
  grand_prix_entered: number;
  career_points: number;
  highest_race_finish: { position: number | string; count: number };
  podiums: number;
  pole_positions: number;
  world_championships: number;
};

type SeasonDriver = {
  driverId: string;
  code: string;
  givenName: string;
  familyName: string;
  permanentNumber: string;
  nationality: string;
  headshot_url?: string;
};

type ConstructorDetailsResponse = {
  constructorId: string;
  name: string;
  nationality: string;
  url: string;
  bio: string;
  drivers?: SeasonDriver[];
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

function ConstructorDetailsPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const constructorId = searchParams.get("constructorId");
  const seasonParam = searchParams.get("season");
  const season = seasonParam ? parseInt(seasonParam, 10) : new Date().getFullYear();

  const [data, setData] = useState<ConstructorDetailsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"stats" | "bio">("stats");

  useEffect(() => {
    if (!constructorId) {
      setError("Не указана команда");
      setLoading(false);
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const res = await apiRequest<ConstructorDetailsResponse>("/api/constructor-details", {
          constructorId,
          season,
        });
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          setError("Ошибка загрузки карточки команды");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [constructorId, season]);

  if (error || !constructorId) {
    return (
      <>
        <BackButton fallback="/constructors">← <span>Кубок конструкторов</span></BackButton>
        <div className="error">{error || "Не указана команда"}</div>
      </>
    );
  }

  if (loading || !data) {
    return (
      <>
        <BackButton fallback="/constructors">← <span>Кубок конструкторов</span></BackButton>
        <div className="loading full-width">Загрузка карточки...</div>
      </>
    );
  }

  const ss = data.season_stats;
  const cs = data.career_stats;

  const formatHigh = (h: { position: number | string; count: number }) =>
    h.position === "-" ? "-" : `${h.position}${h.count > 1 ? ` (x${h.count})` : ""}`;

  const logoUrl = teamLogoUrl(data.constructorId, data.name, season);
  const carUrl = carImageUrl(data.name, season);
  const drivers = data.drivers || [];

  return (
    <>
      <BackButton fallback="/constructors">← <span>Кубок конструкторов</span></BackButton>

      <div className="constructor-hero">
        <div className="constructor-car-wrap">
          <img
            src={carUrl}
            alt={data.name}
            className="constructor-car-img"
            onError={(e) => { e.currentTarget.style.display = "none"; }}
          />
        </div>
        <div className="constructor-hero-title">{data.name.toUpperCase()}</div>
        {drivers.length > 0 && (
          <div className="constructor-hero-drivers">
            {drivers.map((d) => `${d.givenName} ${d.familyName}`).join("  |  ")}
          </div>
        )}
        <div className="constructor-hero-logo">
          <img src={logoUrl} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} />
        </div>
      </div>

      {drivers.length > 0 && (
        <div className="constructor-drivers-section">
          <h3 className="constructor-drivers-title">ПИЛОТЫ</h3>
          <div className="constructor-drivers-grid">
            {drivers.map((d) => {
              const fullName = `${d.givenName} ${d.familyName}`;
              const toDriver = `/driver-details?code=${encodeURIComponent(d.code)}&driverId=${encodeURIComponent(d.driverId)}&season=${season}`;
              return (
                <div
                  key={d.driverId}
                  className="constructor-driver-card"
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(toDriver)}
                  onKeyDown={(e) => e.key === "Enter" && navigate(toDriver)}
                >
                  <div className="constructor-driver-card-bg" />
                  <div className="constructor-driver-card-content">
                    <div className="constructor-driver-name">
                      <span className="driver-first">{d.givenName}</span>{" "}
                      <span className="driver-last">{d.familyName}</span>
                    </div>
                    <div className="constructor-driver-team">{data.name}</div>
                    {d.permanentNumber && (
                      <div className="constructor-driver-number">#{d.permanentNumber}</div>
                    )}
                    <div className="constructor-driver-portrait">
                      {d.headshot_url ? (
                        <img src={d.headshot_url} alt={fullName} />
                      ) : (
                        <span className="driver-initials">{d.code?.slice(0, 2) || "?"}</span>
                      )}
                    </div>
                    {d.nationality && (
                      <span className="constructor-driver-flag">
                        {NATIONALITY_FLAGS[d.nationality] || ""}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

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
            <StatRow label="Позиция в сезоне" value={ss.position ?? "-"} />
            <StatRow label="Очки сезона" value={ss.points} />
            <StatRow label="Гран-при (гонок)" value={ss.grand_prix_races} />
            <StatRow label="Победы" value={ss.grand_prix_wins} />
            <StatRow label="Подиумы" value={ss.grand_prix_podiums} />
            <StatRow label="Поулы" value={ss.grand_prix_poles} />
          </div>
          <div className="driver-stats-block">
            <h3 className="driver-stats-title">КАРЬЕРА</h3>
            <StatRow label="Гран-при (всего)" value={cs.grand_prix_entered} />
            <StatRow label="Карьерные очки" value={Math.round(cs.career_points)} />
            <StatRow label="Лучший финиш" value={formatHigh(cs.highest_race_finish)} />
            <StatRow label="Подиумы" value={cs.podiums} />
            <StatRow label="Поулы" value={cs.pole_positions} />
            <StatRow label="Чемпионства" value={cs.world_championships} />
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

export default ConstructorDetailsPage;
