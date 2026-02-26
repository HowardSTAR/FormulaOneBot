import { useState, useEffect, useRef, useCallback } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { Chart, type ChartConfiguration, registerables } from "chart.js";
import { CustomSelect } from "../../components/CustomSelect";
import { hapticSelection } from "../../helpers/telegram";

Chart.register(...registerables);

const currentRealYear = new Date().getFullYear();

type DriverOption = { code: string; name: string };
type TeamOption = { name: string };
type DriversResponse = { drivers?: DriverOption[] };
type ConstructorsResponse = { constructors?: TeamOption[] };
type CompareDataItem = { code: string; history: number[]; color?: string };
type CompareResponse = {
  error?: string;
  labels?: string[];
  data1?: CompareDataItem;
  data2?: CompareDataItem;
  q_score?: [number, number];
};

function ComparePage() {
  const [tab, setTab] = useState<"drivers" | "teams">("drivers");
  const [yearInput, setYearInput] = useState(String(currentRealYear));
  const [year, setYear] = useState(currentRealYear);
  const [drivers, setDrivers] = useState<DriverOption[]>([]);
  const [teams, setTeams] = useState<TeamOption[]>([]);
  const [d1, setD1] = useState("");
  const [d2, setD2] = useState("");
  const [t1, setT1] = useState("");
  const [t2, setT2] = useState("");
  const [loadingDrivers, setLoadingDrivers] = useState(true);
  const [loadingTeams, setLoadingTeams] = useState(true);
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

  const loadTeamsList = useCallback(async (season: number) => {
    setLoadingTeams(true);
    try {
      const data = await apiRequest<ConstructorsResponse>("/api/constructors", { season });
      const list = data.constructors || [];
      setTeams(list);
      if (list.length >= 2) {
        setT1(list[0].name);
        setT2(list[1].name);
      } else if (list.length === 1) {
        setT1(list[0].name);
        setT2("");
      } else {
        setT1("");
        setT2("");
      }
    } catch (e) {
      console.error(e);
      setTeams([]);
    } finally {
      setLoadingTeams(false);
    }
  }, []);

  useEffect(() => {
    loadDriversList(year);
  }, [year, loadDriversList]);

  useEffect(() => {
    loadTeamsList(year);
  }, [year, loadTeamsList]);

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
    if (tab === "drivers") {
      if (!d1 || !d2 || d1 === d2) {
        if (d1 === d2) alert("Выберите разных пилотов!");
        return;
      }
    } else {
      if (!t1 || !t2 || t1 === t2) {
        if (t1 === t2) alert("Выберите разные команды!");
        return;
      }
    }
    setComparing(true);
    setCompareError(null);
    try {
      const url = tab === "drivers" ? "/api/compare" : "/api/compare/teams";
      const params =
        tab === "drivers"
          ? { d1, d2, season: year }
          : { c1: t1, c2: t2, season: year };
      const res = await apiRequest<CompareResponse>(url, params);
      if (res.error) {
        setCompareError(res.error);
        setResults(null);
      } else if (res.labels && res.data1 && res.data2) {
        setResults(res);
        setTimeout(() => {
          chartRef.current?.scrollIntoView({ behavior: "smooth" });
        }, 100);
      } else {
        setCompareError(
          tab === "drivers"
            ? "Данные не найдены. Возможно, пилоты не выступали вместе в этом сезоне."
            : "Данные не найдены. Возможно, команды не выступали в этом сезоне."
        );
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

  const isDriversReady = tab === "drivers" && d1 && d2 && d1 !== d2;
  const isTeamsReady = tab === "teams" && t1 && t2 && t1 !== t2;
  const canCompare = (tab === "drivers" ? isDriversReady : isTeamsReady) && !comparing;

  return (
    <>
      <BackButton>← Главное меню</BackButton>
      <h2>Сравнение</h2>

      <div className="segmented-tabs">
        <div
          className="segmented-slider"
          style={{ transform: tab === "drivers" ? "translateX(0)" : "translateX(100%)" }}
          aria-hidden
        />
        <button
          type="button"
          className={`segmented-tab ${tab === "drivers" ? "active" : ""}`}
          onClick={() => {
            hapticSelection();
            setTab("drivers");
            setResults(null);
            setCompareError(null);
          }}
        >
          Пилоты
        </button>
        <button
          type="button"
          className={`segmented-tab ${tab === "teams" ? "active" : ""}`}
          onClick={() => {
            hapticSelection();
            setTab("teams");
            setResults(null);
            setCompareError(null);
          }}
        >
          Команды
        </button>
      </div>

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

      {tab === "drivers" && (
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
      )}

      {tab === "teams" && (
        <div className="selectors">
          <CustomSelect
            className="driver-select"
            options={
              loadingTeams
                ? [{ value: "", label: "Загрузка..." }]
                : teams.length === 0
                  ? [{ value: "", label: "Нет данных" }]
                  : teams.map((t) => ({ value: t.name, label: t.name }))
            }
            value={t1}
            onChange={(v) => setT1(String(v))}
            disabled={loadingTeams}
          />
          <span className="vs-badge">VS</span>
          <CustomSelect
            className="driver-select"
            options={
              loadingTeams
                ? [{ value: "", label: "Загрузка..." }]
                : teams.length === 0
                  ? [{ value: "", label: "Нет данных" }]
                  : teams.map((t) => ({ value: t.name, label: t.name }))
            }
            value={t2}
            onChange={(v) => setT2(String(v))}
            disabled={loadingTeams}
          />
        </div>
      )}

      <button
        type="button"
        className="btn-compare"
        onClick={loadComparison}
        disabled={!canCompare}
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
            {tab === "drivers" ? (
              <div className="stat-card">
                <div className="stat-title">Квалификации</div>
                <div className="stat-score">
                  <span className="s-d1">{results.q_score?.[0] ?? 0}</span> :{" "}
                  <span className="s-d2">{results.q_score?.[1] ?? 0}</span>
                </div>
              </div>
            ) : (
              <div className="stat-card">
                <div className="stat-title">Сумма очков</div>
                <div className="stat-score">
                  <span className="s-d1">{totalPts1}</span> : <span className="s-d2">{totalPts2}</span>
                </div>
              </div>
            )}
          </div>
          {tab === "drivers" && (
            <div className="stat-card" style={{ marginBottom: 20 }}>
              <div className="stat-title">Сумма очков</div>
              <div className="stat-score">
                <span className="s-d1">{totalPts1}</span> : <span className="s-d2">{totalPts2}</span>
              </div>
            </div>
          )}
          <div className="chart-container">
            <canvas ref={chartRef} />
          </div>
        </div>
      )}
    </>
  );
}

export default ComparePage;
