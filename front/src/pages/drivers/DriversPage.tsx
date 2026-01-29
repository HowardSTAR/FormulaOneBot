import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";

const currentRealYear = new Date().getFullYear();

type Driver = {
  position: number;
  name: string;
  code: string;
  points: number;
  is_favorite?: boolean;
};

type DriversResponse = { drivers?: Driver[] };

function DriversPage() {
  const [year, setYear] = useState(currentRealYear);
  const [yearInput, setYearInput] = useState(String(currentRealYear));
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [emptyMessage, setEmptyMessage] = useState<{ icon: string; title: string; desc: string } | null>(null);

  const loadDrivers = useCallback(async (season: number) => {
    setLoading(true);
    setError(null);
    setEmptyMessage(null);
    try {
      const data = await apiRequest<DriversResponse>("/api/drivers", { season });
      if (!data.drivers || data.drivers.length === 0) {
        if (season === currentRealYear) {
          setEmptyMessage({
            icon: "🏎️",
            title: "Сезон еще не начался",
            desc: "Первая гонка еще впереди. Таблица очков пуста.",
          });
        } else {
          setEmptyMessage({ icon: "", title: "Нет данных", desc: `Информация за ${season} год отсутствует.` });
        }
        setDrivers([]);
      } else {
        setDrivers(data.drivers);
      }
    } catch (e) {
      console.error(e);
      setError("Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDrivers(year);
  }, [year, loadDrivers]);

  const handleSearch = () => {
    const y = parseInt(yearInput, 10);
    if (!y) return;
    if (y > currentRealYear) {
      setEmptyMessage({
        icon: "🔮",
        title: "Будущее туманно",
        desc: `Мы пока не знаем, кто станет чемпионом в ${y} году.`,
      });
      setDrivers([]);
      setLoading(false);
      return;
    }
    if (y < 1950) {
      setEmptyMessage({
        icon: "🦖",
        title: "Слишком рано",
        desc: "Первый сезон Формулы-1 прошел в 1950 году.",
      });
      setDrivers([]);
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
      <h2>Личный зачет</h2>

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
            <div className="empty-desc">{emptyMessage.desc}</div>
          </div>
        )}
        {!loading && !error && !emptyMessage && drivers.length > 0 &&
          drivers.map((driver) => {
            const posClass =
              driver.position === 1 ? "pos-1" : driver.position === 2 ? "pos-2" : driver.position === 3 ? "pos-3" : "";
            const isChampion = driver.position === 1 && year < currentRealYear;
            return (
              <div
                key={driver.code}
                className={isChampion ? "driver-card champion-card" : "driver-card"}
              >
                {isChampion && <div className="champion-badge">World Champion</div>}
                <div className={`pos-box ${posClass}`}>{driver.position}</div>
                <div className="driver-info">
                  <div className="driver-name" style={isChampion ? { color: "#ffd700" } : undefined}>
                    {driver.name} {driver.is_favorite && <span style={{ fontSize: 14, marginLeft: 4 }}>⭐️</span>}
                  </div>
                  <div className="team-name" style={isChampion ? { color: "rgba(255,255,255,0.7)" } : undefined}>
                    {driver.code}
                  </div>
                </div>
                <div
                  className="driver-points"
                  style={isChampion ? { background: "#ffd700", color: "#000" } : undefined}
                >
                  {driver.points}
                </div>
              </div>
            );
          })}
      </div>
    </>
  );
}

export default DriversPage;
