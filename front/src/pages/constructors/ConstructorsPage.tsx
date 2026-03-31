import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { YearSelect } from "../../components/YearSelect";
import { apiRequest } from "../../helpers/api";

const currentRealYear = new Date().getFullYear();

function teamLogoUrl(teamId: string, teamName: string, season: number): string {
  const apiBase = (import.meta.env.VITE_API_URL as string) || "";
  const pathBase = ((import.meta.env.BASE_URL as string) || "/").replace(/\/$/, "");
  const origin = apiBase || (typeof window !== "undefined" ? window.location.origin : "");
  const team = teamId || teamName;
  const params = new URLSearchParams({ team, season: String(season) });
  if (teamName) params.set("name", teamName);
  return `${origin.replace(/\/$/, "")}${pathBase}/api/team-logo?${params}`;
}

type Constructor = {
  position: number;
  name: string;
  points: number;
  is_favorite?: boolean;
  constructorId?: string;
};

type ConstructorsResponse = { constructors?: Constructor[] };

const minConstructorYear = 1958;

function ConstructorsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const yearFromUrl = parseInt(searchParams.get("year") || "", 10);
  const [year, setYear] = useState(
    yearFromUrl && yearFromUrl >= minConstructorYear && yearFromUrl <= currentRealYear ? yearFromUrl : currentRealYear
  );
  const [teams, setTeams] = useState<Constructor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyMessage, setEmptyMessage] = useState<{ icon: string; title: string; desc?: string } | null>(null);

  const loadTeams = useCallback(async (season: number) => {
    setLoading(true);
    setError(null);
    setEmptyMessage(null);
    try {
      const data = await apiRequest<ConstructorsResponse>("/api/constructors", { season });
      if (!data.constructors || data.constructors.length === 0) {
        if (season === currentRealYear) {
          setEmptyMessage({
            icon: "🏎️",
            title: "Сезон еще не начался",
            desc: "Ни одна команда еще не заработала очки.",
          });
        } else {
          setEmptyMessage({ icon: "", title: "Нет данных" });
        }
        setTeams([]);
      } else {
        setTeams(data.constructors);
      }
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTeams(year);
  }, [year, loadTeams]);

  const updateYear = useCallback((y: number) => {
    setYear(y);
    setSearchParams(y === currentRealYear ? {} : { year: String(y) }, { replace: true });
  }, [setSearchParams]);

  const handleYearChange = (y: number) => {
    if (y > currentRealYear) {
      setEmptyMessage({
        icon: "🛠️",
        title: "Машина времени сломалась",
        desc: `Инженеры еще не спроектировали болиды ${y} года.`,
      });
      setTeams([]);
      setLoading(false);
      return;
    }
    if (y < minConstructorYear) {
      setEmptyMessage({
        icon: "📜",
        title: "Исторический факт",
        desc: "Кубок Конструкторов разыгрывается только с 1958 года.",
      });
      setTeams([]);
      setLoading(false);
      return;
    }
    updateYear(y);
  };

  return (
    <>
      <BackButton>← <span>Главное меню</span></BackButton>
      <div className="page-head-row">
        <h2 className="page-head-title">Кубок конструкторов</h2>
        <div className="page-head-controls">
          <YearSelect
            value={year}
            onChange={handleYearChange}
            minYear={minConstructorYear}
            maxYear={currentRealYear}
            placeholder="Введи год"
          />
        </div>
      </div>

      <div className="standings-cards-grid">
        {loading && <div className="loading full-width"><div className="spinner" /><div>Загрузка команд...</div></div>}
        {error && <div className="page-error">{error}</div>}
        {!loading && !error && emptyMessage && (
          <div className="empty-state">
            {emptyMessage.icon && <span className="empty-icon">{emptyMessage.icon}</span>}
            <div className="empty-title">{emptyMessage.title}</div>
            {emptyMessage.desc && <div className="empty-desc">{emptyMessage.desc}</div>}
          </div>
        )}
        {!loading && !error && !emptyMessage && teams.length > 0 &&
          teams.map((team) => {
            const posClass =
              team.position === 1 ? "pos-1" : team.position === 2 ? "pos-2" : team.position === 3 ? "pos-3" : "";
            const isChampion = team.position === 1 && year < currentRealYear;
            const toTeam = `/constructor-details?constructorId=${encodeURIComponent(team.constructorId || team.name)}&season=${year}`;
            return (
              <div
                key={team.name}
                role="button"
                tabIndex={0}
                className={isChampion ? "team-card champion-card team-card-clickable" : "team-card team-card-clickable"}
                onClick={() => navigate(toTeam)}
                onKeyDown={(e) => e.key === "Enter" && navigate(toTeam)}
              >
                {isChampion && <div className="champion-badge">Constructors Champion</div>}
                <div className={`pos-box ${posClass}`}>{team.position}</div>
                {(team.constructorId || team.name) && (
                  <img
                    src={teamLogoUrl(team.constructorId || "", team.name, year)}
                    alt=""
                    className="constructor-logo"
                    onError={(e) => (e.currentTarget.style.display = "none")}
                  />
                )}
                <div className="team-info">
                  <div className="team-name-main" style={isChampion ? { color: "#ffd700" } : undefined}>
                    {team.name} {team.is_favorite && <span style={{ fontSize: 14, marginLeft: 4 }}>⭐️</span>}
                  </div>
                </div>
                <div
                  className="team-points"
                  style={isChampion ? { background: "#ffd700", color: "#000" } : undefined}
                >
                  {team.points}
                </div>
              </div>
            );
          })}
      </div>
    </>
  );
}

export default ConstructorsPage;
