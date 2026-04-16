import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { getFlagUrlForNationality } from "../../constants/flags";

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
        <div className="loading full-width">
          <div className="spinner" />
          <div>Загрузка карточки команды...</div>
        </div>
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
  const teamCountry = data.constructorId === "mercedes" ? "Brackley, United Kingdom" : data.nationality || "Неизвестно";
  const foundedLabel = data.constructorId === "mercedes" ? "Осн. 1954 / 2010" : `Осн. ${Math.max(1950, season - 20)}`;
  const managementName = data.constructorId === "mercedes" ? "Toto Wolff" : "Team Principal";
  const managementRole = data.constructorId === "mercedes" ? "Team Principal & CEO" : "Руководство команды";
  const heroTitleMain = data.constructorId === "mercedes"
    ? "MERCEDES-AMG"
    : data.name.toUpperCase().includes("PETRONAS")
    ? data.name.toUpperCase().replace(/\s*PETRONAS\s*/g, " ").trim()
    : data.name.toUpperCase();
  const heroTitleAccent = data.constructorId === "mercedes"
    ? "PETRONAS"
    : data.name.toUpperCase().includes("PETRONAS") ? "PETRONAS" : "";
  const sortedDrivers = [...drivers].sort((a, b) => Number(b.permanentNumber || 0) - Number(a.permanentNumber || 0));

  return (
    <>
      <div className="constructor-details-mobile">
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
                const driverFlagUrl = getFlagUrlForNationality(d.nationality);
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
                        <img
                          src={pilotPortraitUrl(d.code, fullName, season)}
                          alt={fullName}
                          onError={(e) => {
                            if (e.currentTarget.src !== window.location.origin + "/api/pilot-portrait") {
                              e.currentTarget.src = "/api/pilot-portrait";
                            }
                          }}
                        />
                      </div>
                      {d.nationality && driverFlagUrl && (
                        <img
                          src={driverFlagUrl}
                          alt={d.nationality}
                          className="constructor-driver-flag"
                        />
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
      </div>

      <section className="constructor-profile-desktop">
        <BackButton fallback="/constructors">← <span>Кубок конструкторов</span></BackButton>
        <header className="constructor-profile-desktop-hero">
          <img
            src={carUrl}
            alt={data.name}
            className="constructor-profile-desktop-car"
            onError={(e) => { e.currentTarget.style.display = "none"; }}
          />
          <div className="constructor-profile-desktop-brand">
            <img src={logoUrl} alt="" className="constructor-profile-desktop-logo" onError={(e) => { e.currentTarget.style.display = "none"; }} />
            <div>
              <h1>
                <span>{heroTitleMain}</span>
                {heroTitleAccent && <em>{heroTitleAccent}</em>}
              </h1>
              <div className="constructor-profile-desktop-meta">
                <span>{foundedLabel}</span>
                <span>{teamCountry}</span>
              </div>
            </div>
          </div>
        </header>

        <div className="constructor-profile-desktop-grid">
          <aside className="constructor-profile-desktop-left">
            <div className="constructor-profile-drivers-panel">
              <h3>Действующие пилоты</h3>
              {sortedDrivers.slice(0, 2).map((d, idx) => {
                const fullName = `${d.givenName} ${d.familyName}`;
                const toDriver = `/driver-details?code=${encodeURIComponent(d.code)}&driverId=${encodeURIComponent(d.driverId)}&season=${season}`;
                return (
                  <div
                    key={`desktop-driver-${d.driverId}`}
                    className="constructor-profile-driver-row"
                    role="button"
                    tabIndex={0}
                    onClick={() => navigate(toDriver)}
                    onKeyDown={(e) => e.key === "Enter" && navigate(toDriver)}
                  >
                    <img src={pilotPortraitUrl(d.code, fullName, season)} alt={fullName} />
                    <div>
                      <b>{fullName}</b>
                      <span>{d.nationality || "Пилот"}</span>
                    </div>
                    <i>#{d.permanentNumber || "--"}</i>
                    <u>{idx === 0 ? "↗" : "★"}</u>
                  </div>
                );
              })}
            </div>
            <div className="constructor-profile-management">
              <h3>Руководство</h3>
              <div className="constructor-profile-management-avatar" />
              <p>{managementName}</p>
              <span>{managementRole}</span>
            </div>
          </aside>

          <div className="constructor-profile-desktop-right">
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
              <>
                <div className="driver-stats-grid constructor-profile-stats-grid">
                  <div className="driver-stats-block constructor-season-block">
                    <div className="constructor-season-head">
                      <h3 className="driver-stats-title">{data.season} СЕЗОН</h3>
                      <strong>{ss.position ?? "-"}</strong>
                    </div>
                    <div className="constructor-season-points-row">
                      <span>ОЧКИ СЕЗОНА</span>
                      <b>{ss.points}</b>
                    </div>
                    <div className="constructor-season-metrics">
                      <div>
                        <span>ГРАН-ПРИ</span>
                        <b>{ss.grand_prix_races}</b>
                      </div>
                      <div className="accent">
                        <span>ПОБЕДЫ</span>
                        <b>{ss.grand_prix_wins}</b>
                      </div>
                      <div>
                        <span>ПОДИУМЫ</span>
                        <b>{ss.grand_prix_podiums}</b>
                      </div>
                      <div>
                        <span>ПОУЛЫ</span>
                        <b>{ss.grand_prix_poles}</b>
                      </div>
                    </div>
                  </div>
                  <div className="driver-stats-block constructor-career-block">
                    <h3 className="driver-stats-title">СТАТИСТИКА КАРЬЕРЫ</h3>
                    <StatRow label="Гран-при всего" value={cs.grand_prix_entered} />
                    <StatRow label="Очки за карьеру" value={Math.round(cs.career_points)} />
                    <StatRow label="Лучший финиш" value={formatHigh(cs.highest_race_finish)} />
                    <StatRow label="Подиумы" value={cs.podiums} />
                    <StatRow label="Поулы" value={cs.pole_positions} />
                    <div className="constructor-career-championships">
                      <span>ЧЕМПИОНСТВА</span>
                      <b>{String(cs.world_championships).padStart(2, "0")}</b>
                    </div>
                  </div>
                </div>
              </>
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
        </div>
      </section>
    </>
  );
}

export default ConstructorDetailsPage;
