import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import { Chart, type ChartConfiguration, registerables } from "chart.js";

Chart.register(...registerables);

const currentRealYear = new Date().getFullYear();

type DriverOption = { code: string; name: string };
type DriversResponse = { drivers?: DriverOption[] };
type CompareResponse = {
  status: string;
  data?: {
    labels: string[];
    driver1: { history: number[] };
    driver2: { history: number[] };
    score: { race: Record<string, number>; quali: Record<string, number> };
  };
};

function ComparePage() {
  const [yearInput, setYearInput] = useState(String(currentRealYear));
  const [year, setYear] = useState(currentRealYear);
  const [drivers, setDrivers] = useState<DriverOption[]>([]);
  const [d1, setD1] = useState("");
  const [d2, setD2] = useState("");
  const [loadingDrivers, setLoadingDrivers] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [results, setResults] = useState<CompareResponse["data"] | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);
  const chartRef = useRef<HTMLCanvasElement>(null);
  const chartInstanceRef = useRef<Chart | null>(null);

  const loadDriversList = useCallback(async (season: number) => {
    setLoadingDrivers(true);
    try {
      const data = await apiRequest<DriversResponse>("/api/drivers", { season });
      const list = data.drivers || [];
      setDrivers(list);
      if (list.length >= 2) {
        setD1(list[0].code);
        setD2(list[1].code);
      } else if (list.length === 1) {
        setD1(list[0].code);
        setD2("");
      } else {
        setD1("");
        setD2("");
      }
    } catch (e) {
      console.error(e);
      setDrivers([]);
    } finally {
      setLoadingDrivers(false);
    }
  }, []);

  useEffect(() => {
    loadDriversList(year);
  }, [year, loadDriversList]);

  const handleSearch = () => {
    const y = parseInt(yearInput, 10);
    if (!y || y < 1950 || y > currentRealYear + 1) {
      alert("Пожалуйста, введите корректный год (с 1950)");
      return;
    }
    setYear(y);
    setResults(null);
  };

  const goCurrentYear = () => {
    setYear(currentRealYear);
    setYearInput(String(currentRealYear));
    setResults(null);
  };

  const loadComparison = async () => {
    if (!d1 || !d2 || d1 === d2) {
      if (d1 === d2) alert("Выберите разных пилотов!");
      return;
    }
    setComparing(true);
    setCompareError(null);
    try {
      const res = await apiRequest<CompareResponse>("/api/compare", {
        d1,
        d2,
        season: String(year),
      });
      if (res.status === "ok" && res.data) {
        setResults(res.data);
        setTimeout(() => {
          chartRef.current?.scrollIntoView({ behavior: "smooth" });
        }, 100);
      } else {
        setCompareError("Данные не найдены. Возможно, пилоты не выступали вместе в этом сезоне.");
      }
    } catch (e) {
      console.error(e);
      setCompareError("Ошибка загрузки данных");
    } finally {
      setComparing(false);
    }
  };

  useEffect(() => {
    if (!results || !chartRef.current) return;
    const ctx = chartRef.current.getContext("2d");
    if (!ctx) return;

    chartInstanceRef.current?.destroy();
    chartInstanceRef.current = null;
    const gradient1 = ctx.createLinearGradient(0, 0, 0, 400);
    gradient1.addColorStop(0, "rgba(54, 162, 235, 0.5)");
    gradient1.addColorStop(1, "rgba(54, 162, 235, 0.0)");
    const gradient2 = ctx.createLinearGradient(0, 0, 0, 400);
    gradient2.addColorStop(0, "rgba(255, 99, 132, 0.5)");
    gradient2.addColorStop(1, "rgba(255, 99, 132, 0.0)");

    const config: ChartConfiguration<"line"> = {
      type: "line",
      data: {
        labels: results.labels,
        datasets: [
          {
            label: d1,
            data: results.driver1.history,
            borderColor: "#0033ff",
            backgroundColor: gradient1,
            fill: true,
            pointRadius: 3,
            pointHoverRadius: 6,
            tension: 0.2,
            borderWidth: 2,
          },
          {
            label: d2,
            data: results.driver2.history,
            borderColor: "#ff0000",
            backgroundColor: gradient2,
            fill: true,
            pointRadius: 3,
            pointHoverRadius: 6,
            tension: 0.2,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: "#fff", font: { size: 12, family: "Jost" } } },
          tooltip: {
            backgroundColor: "rgba(20, 20, 20, 0.9)",
            titleColor: "#fff",
            bodyColor: "#ccc",
            borderColor: "#444",
            borderWidth: 1,
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${ctx.raw} оч.`,
              afterBody: (items) => {
                const v1 = items[0]?.parsed?.y ?? 0;
                const v2 = items[1]?.parsed?.y ?? 0;
                const diff = Math.abs(v1 - v2);
                const leader = v1 > v2 ? items[0]?.dataset.label : items[1]?.dataset.label;
                return leader ? `\nЛидер: ${leader} (+${diff})` : "";
              },
            },
          },
        },
        scales: {
          y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#888" } },
          x: {
            grid: { display: false },
            ticks: { color: "#aaa", autoSkip: false, maxRotation: 90, minRotation: 90, font: { size: 10 } },
          },
        },
      },
    };
    chartInstanceRef.current = new Chart(ctx, config);
    return () => {
      chartInstanceRef.current?.destroy();
    };
  }, [results, d1, d2]);

  return (
    <>
      <Link to="/" className="btn-back">
        ← Главное меню
      </Link>
      <h2>Сравнение</h2>

      <div className="search-container">
        <input
          type="number"
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

      <div className="selectors">
        <select
          className="driver-select"
          value={d1}
          onChange={(e) => setD1(e.target.value)}
          disabled={loadingDrivers}
        >
          {loadingDrivers && <option>Загрузка...</option>}
          {!loadingDrivers && drivers.length === 0 && <option value="">Нет данных</option>}
          {drivers.map((d) => (
            <option key={d.code} value={d.code}>
              {d.name}
            </option>
          ))}
        </select>
        <span className="vs-badge">VS</span>
        <select
          className="driver-select"
          value={d2}
          onChange={(e) => setD2(e.target.value)}
          disabled={loadingDrivers}
        >
          {loadingDrivers && <option>Загрузка...</option>}
          {!loadingDrivers && drivers.length === 0 && <option value="">Нет данных</option>}
          {drivers.map((d) => (
            <option key={d.code} value={d.code}>
              {d.name}
            </option>
          ))}
        </select>
      </div>

      <button
        type="button"
        className="btn-compare"
        onClick={loadComparison}
        disabled={comparing || !d1 || !d2}
      >
        {comparing ? "Анализируем..." : "Сравнить"}
      </button>

      {compareError && (
        <div style={{ color: "#ff6b6b", marginBottom: 16, fontSize: 14 }}>{compareError}</div>
      )}

      {results && (
        <div style={{ animation: "fadeIn 0.3s ease-out" }}>
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-title">Гонки</div>
              <div className="stat-score">
                <span className="s-d1">{results.score.race[d1] ?? 0}</span> :{" "}
                <span className="s-d2">{results.score.race[d2] ?? 0}</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-title">Квалификации</div>
              <div className="stat-score">
                <span className="s-d1">{results.score.quali[d1] ?? 0}</span> :{" "}
                <span className="s-d2">{results.score.quali[d2] ?? 0}</span>
              </div>
            </div>
          </div>
          <div className="chart-container">
            <canvas ref={chartRef} />
          </div>
        </div>
      )}
    </>
  );
}

export default ComparePage;
