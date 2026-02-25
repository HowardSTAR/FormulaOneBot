import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import { Chart, type ChartConfiguration, registerables } from "chart.js";
import { CustomSelect } from "../../components/CustomSelect";

Chart.register(...registerables);

const currentRealYear = new Date().getFullYear();

type DriverOption = { code: string; name: string };
type DriversResponse = { drivers?: DriverOption[] };
type CompareDataItem = { code: string; history: number[]; color?: string };
type CompareResponse = {
  error?: string;
  labels?: string[];
  data1?: CompareDataItem;
  data2?: CompareDataItem;
  q_score?: [number, number];
};

function ComparePage() {
  const [yearInput, setYearInput] = useState(String(currentRealYear));
  const [year, setYear] = useState(currentRealYear);
  const [drivers, setDrivers] = useState<DriverOption[]>([]);
  const [d1, setD1] = useState("");
  const [d2, setD2] = useState("");
  const [loadingDrivers, setLoadingDrivers] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [results, setResults] = useState<CompareResponse | null>(null);
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
        season: year,
      });
      if (res.error) {
        setCompareError(res.error);
        setResults(null);
      } else if (res.labels && res.data1 && res.data2) {
        setResults(res);
        setTimeout(() => {
          chartRef.current?.scrollIntoView({ behavior: "smooth" });
        }, 100);
      } else {
        setCompareError("Данные не найдены. Возможно, пилоты не выступали вместе в этом сезоне.");
        setResults(null);
      }
    } catch (e) {
      console.error(e);
      setCompareError(e instanceof Error ? e.message : "Ошибка загрузки данных");
      setResults(null);
    } finally {
      setComparing(false);
    }
  };

  useEffect(() => {
    if (!results || !results.labels?.length || !chartRef.current) return;
    const ctx = chartRef.current.getContext("2d");
    if (!ctx) return;

    const color1 = "#e10600";
    const color2 = "#00d2be";
    const d1Info = results.data1 ?? { code: d1, history: [] };
    const d2Info = results.data2 ?? { code: d2, history: [] };

    chartInstanceRef.current?.destroy();
    chartInstanceRef.current = null;
    const gradient1 = ctx.createLinearGradient(0, 0, 0, 400);
    gradient1.addColorStop(0, "rgba(225, 6, 0, 0.4)");
    gradient1.addColorStop(1, "rgba(225, 6, 0, 0)");
    const gradient2 = ctx.createLinearGradient(0, 0, 0, 400);
    gradient2.addColorStop(0, "rgba(0, 210, 190, 0.4)");
    gradient2.addColorStop(1, "rgba(0, 210, 190, 0)");

    const config: ChartConfiguration<"line"> = {
      type: "line",
      data: {
        labels: results.labels,
        datasets: [
          {
            label: d1Info.code,
            data: d1Info.history,
            borderColor: color1,
            backgroundColor: gradient1,
            fill: true,
            pointRadius: 3,
            pointHoverRadius: 6,
            tension: 0.4,
            borderWidth: 3,
          },
          {
            label: d2Info.code,
            data: d2Info.history,
            borderColor: color2,
            backgroundColor: gradient2,
            fill: true,
            pointRadius: 3,
            pointHoverRadius: 6,
            tension: 0.4,
            borderWidth: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: "white" } },
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
          y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.1)" }, ticks: { color: "white" } },
          x: {
            grid: { color: "rgba(255,255,255,0.1)" },
            ticks: { color: "white", autoSkip: false, maxRotation: 90, minRotation: 90 },
          },
        },
      },
    };
    chartInstanceRef.current = new Chart(ctx, config);
    return () => {
      chartInstanceRef.current?.destroy();
    };
  }, [results, d1, d2]);

  const raceScore1 = results
    ? results.data1!.history.reduce(
        (acc, pts1, i) => acc + (pts1 > (results.data2!.history[i] ?? 0) ? 1 : 0),
        0
      )
    : 0;
  const raceScore2 = results
    ? results.data2!.history.reduce(
        (acc, pts2, i) => acc + (pts2 > (results.data1!.history[i] ?? 0) ? 1 : 0),
        0
      )
    : 0;
  const totalPts1 = results?.data1?.history.reduce((a, b) => a + b, 0) ?? 0;
  const totalPts2 = results?.data2?.history.reduce((a, b) => a + b, 0) ?? 0;

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
        <CustomSelect
          className="driver-select"
          options={
            loadingDrivers
              ? [{ value: "", label: "Загрузка..." }]
              : drivers.length === 0
                ? [{ value: "", label: "Нет данных" }]
                : drivers.map((d) => ({ value: d.code, label: d.name }))
          }
          value={d1}
          onChange={(v) => setD1(String(v))}
          disabled={loadingDrivers}
        />
        <span className="vs-badge">VS</span>
        <CustomSelect
          className="driver-select"
          options={
            loadingDrivers
              ? [{ value: "", label: "Загрузка..." }]
              : drivers.length === 0
                ? [{ value: "", label: "Нет данных" }]
                : drivers.map((d) => ({ value: d.code, label: d.name }))
          }
          value={d2}
          onChange={(v) => setD2(String(v))}
          disabled={loadingDrivers}
        />
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

      {results && results.labels && results.labels.length > 0 && (
        <div style={{ animation: "fadeIn 0.3s ease-out" }}>
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-title">Гонки</div>
              <div className="stat-score">
                <span className="s-d1">{raceScore1}</span> : <span className="s-d2">{raceScore2}</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-title">Квалификации</div>
              <div className="stat-score">
                <span className="s-d1">{results.q_score?.[0] ?? 0}</span> :{" "}
                <span className="s-d2">{results.q_score?.[1] ?? 0}</span>
              </div>
            </div>
          </div>
          <div className="stat-card" style={{ marginBottom: 20 }}>
            <div className="stat-title">Сумма очков</div>
            <div className="stat-score">
              <span className="s-d1">{totalPts1}</span> : <span className="s-d2">{totalPts2}</span>
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
