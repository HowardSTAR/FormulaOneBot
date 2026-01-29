import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";

const currentRealYear = new Date().getFullYear();

type Constructor = {
  position: number;
  name: string;
  points: number;
  is_favorite?: boolean;
};

type ConstructorsResponse = { constructors?: Constructor[] };

function ConstructorsPage() {
  const [year, setYear] = useState(currentRealYear);
  const [yearInput, setYearInput] = useState(String(currentRealYear));
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
      setError("Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTeams(year);
  }, [year, loadTeams]);

  const handleSearch = () => {
    const y = parseInt(yearInput, 10);
    if (!y) return;
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
    if (y < 1958) {
      setEmptyMessage({
        icon: "📜",
        title: "Исторический факт",
        desc: "Кубок Конструкторов разыгрывается только с 1958 года.",
      });
      setTeams([]);
      setLoading(false);
      return;
    }
    setYear(y);
  };

  const goCurrentYear = () => {
    setYear(currentRealYear);
    setYearInput(String(currentRealYear));
  };

  return (
    <>
      <Link to="/" className="btn-back">
        ← <span>Главное меню</span>
      </Link>
      <h2>Кубок конструкторов</h2>

      <div className="search-container">
        <input
          type="number"
          id="year-input"
          className="search-input"
          placeholder="Введи год"
          inputMode="numeric"
          value={yearInput}
          onChange={(e) => setYearInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />
        <button type="button" className="search-btn" onClick={handleSearch}>
          🔍
        </button>
        <button type="button" className="current-year-btn" onClick={goCurrentYear}>
          {currentRealYear}
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {loading && <div className="loading full-width">Загрузка...</div>}
        {error && <div style={{ color: "red", textAlign: "center", padding: 20 }}>{error}</div>}
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
            return (
              <div
                key={team.name}
                className={isChampion ? "team-card champion-card" : "team-card"}
              >
                {isChampion && <div className="champion-badge">Constructors Champion</div>}
                <div className={`pos-box ${posClass}`}>{team.position}</div>
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
