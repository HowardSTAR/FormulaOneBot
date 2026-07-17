import { useState, useEffect, useRef, useCallback } from "react";
import { BackButton } from "../../components/BackButton";
import { YearSelect } from "../../components/YearSelect";
import { apiRequest } from "../../helpers/api";
import { Chart, type ChartConfiguration, registerables } from "chart.js";
import { CustomSelect } from "../../components/CustomSelect";
import { hapticSelection } from "../../helpers/telegram";

Chart.register(...registerables);

const currentRealYear = new Date().getFullYear();

type DriverOption = { code: string; name: string; is_favorite?: boolean };
type TeamOption = { name: string; is_favorite?: boolean };
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

  const selectedName1 =
    tab === "drivers"
      ? drivers.find((d) => d.code === d1)?.name || d1 || "—"
      : teams.find((t) => t.name === t1)?.name || t1 || "—";
  const selectedName2 =
    tab === "drivers"
      ? drivers.find((d) => d.code === d2)?.name || d2 || "—"
      : teams.find((t) => t.name === t2)?.name || t2 || "—";

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

  const handleYearChange = (y: number) => {
    if (y < 1950 || y > currentRealYear + 1) return;
    setYear(y);
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
        // Не делаем автоскролл: страница может резко "скачить" вниз.
        // Пусть пользователь остаётся на месте, а контент появится без движения.
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

    const focusIndex = Math.min(1, Math.max(0, (results.labels?.length ?? 1) - 1));
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
            fill: false,
            pointRadius: d1Info.history.map((_, i) => (i === focusIndex ? 4 : 2)),
            pointHoverRadius: 5,
            pointBackgroundColor: d1Info.history.map((_, i) => (i === focusIndex ? "#ffffff" : color1)),
            pointBorderColor: color1,
            pointBorderWidth: 3,
            tension: 0.28,
            borderWidth: 2.4,
            cubicInterpolationMode: "monotone",
          },
          {
            label: d2Info.code,
            data: d2Info.history,
            borderColor: color2,
            backgroundColor: gradient2,
            fill: false,
            pointRadius: 2,
            pointHoverRadius: 5,
            tension: 0.28,
            borderWidth: 2.4,
            cubicInterpolationMode: "monotone",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        // Доп. отступы, чтобы крайние значения (0 и максимум) не обрезались.
        layout: {
          padding: {
            top: 6,
            bottom: 4,
            left: 2,
            right: 4,
          },
        },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "top",
            align: "end",
            labels: {
              color: "rgba(227,226,227,0.85)",
              font: { family: "Space Grotesk", size: 10, weight: 700 },
              boxWidth: 18,
              boxHeight: 4,
              padding: 12,
            },
          },
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
          y: {
            beginAtZero: true,
            // "+1 запас" по высоте от минимального и максимального значений.
            grace: 1,
            grid: { color: "rgba(255,255,255,0.08)" },
            ticks: {
              color: "rgba(227,226,227,0.65)",
              padding: 8,
              precision: 0,
            },
            border: { color: "rgba(255,255,255,0.06)" },
          },
          x: {
            grid: { color: "rgba(255,255,255,0.08)" },
            ticks: {
              color: "rgba(227,226,227,0.65)",
              autoSkip: true,
              maxTicksLimit: 10,
              maxRotation: 0,
              minRotation: 0,
            },
            border: { color: "rgba(255,255,255,0.06)" },
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
  const averageGap = results?.labels?.length ? Math.abs(totalPts1 - totalPts2) / results.labels.length : 0;
  const pointsLead = Math.abs(totalPts1 - totalPts2);
  const comparisonLeader = totalPts1 === totalPts2 ? "Равенство" : totalPts1 > totalPts2 ? selectedName1 : selectedName2;
  const comparedRounds = results?.labels?.length ?? 0;

  const isDriversReady = tab === "drivers" && d1 && d2 && d1 !== d2;
  const isTeamsReady = tab === "teams" && t1 && t2 && t1 !== t2;
  const canCompare = (tab === "drivers" ? isDriversReady : isTeamsReady) && !comparing;

  return (
    <>
      <BackButton className="btn-back compare-back-button">← Главное меню</BackButton>
      <div className="page-head-row page-head-row-compare">
        <h2 className="page-head-title">
          {tab === "drivers" ? "Сравнение пилотов" : "Сравнение команд"}
        </h2>
        <div className="page-head-controls">
          <YearSelect
            value={year}
            onChange={handleYearChange}
            minYear={1950}
            maxYear={currentRealYear + 1}
            placeholder="Введи год"
            showCurrentYearBtn={false}
          />
        </div>
      </div>

      <div className="compare-layout compare-layout-redesign">
        <div className="compare-controls-panel compare-controls-panel-redesign">
          <div className="compare-controls-topline">
            <div className="compare-controls-header">
              <div className="compare-controls-kicker">Новое сравнение</div>
              <div className="compare-controls-caption">Выберите двух участников сезона</div>
            </div>

            <div className="segmented-tabs compare-redesign-tabs">
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
          </div>

          <div className="selectors compare-redesign-selectors">
            <div className="compare-participant-field">
              <span>Участник 1</span>
              <CustomSelect
                className="driver-select"
                options={
                  tab === "drivers"
                    ? loadingDrivers
                      ? [{ value: "", label: "Загрузка..." }]
                      : drivers.length === 0
                        ? [{ value: "", label: "Нет данных" }]
                        : drivers.map((d) => ({
                            value: d.code,
                            label: d.is_favorite ? `⭐ ${d.name}` : d.name,
                          }))
                    : loadingTeams
                      ? [{ value: "", label: "Загрузка..." }]
                      : teams.length === 0
                        ? [{ value: "", label: "Нет данных" }]
                        : teams.map((t) => ({
                            value: t.name,
                            label: t.is_favorite ? `⭐ ${t.name}` : t.name,
                          }))
                }
                value={tab === "drivers" ? d1 : t1}
                onChange={(v) => (tab === "drivers" ? setD1(String(v)) : setT1(String(v)))}
                disabled={tab === "drivers" ? loadingDrivers : loadingTeams}
              />
            </div>
            <span className="vs-badge">VS</span>
            <div className="compare-participant-field">
              <span>Участник 2</span>
              <CustomSelect
                className="driver-select"
                options={
                  tab === "drivers"
                    ? loadingDrivers
                      ? [{ value: "", label: "Загрузка..." }]
                      : drivers.length === 0
                        ? [{ value: "", label: "Нет данных" }]
                        : drivers.map((d) => ({
                            value: d.code,
                            label: d.is_favorite ? `⭐ ${d.name}` : d.name,
                          }))
                    : loadingTeams
                      ? [{ value: "", label: "Загрузка..." }]
                      : teams.length === 0
                        ? [{ value: "", label: "Нет данных" }]
                        : teams.map((t) => ({
                            value: t.name,
                            label: t.is_favorite ? `⭐ ${t.name}` : t.name,
                          }))
                }
                value={tab === "drivers" ? d2 : t2}
                onChange={(v) => (tab === "drivers" ? setD2(String(v)) : setT2(String(v)))}
                disabled={tab === "drivers" ? loadingDrivers : loadingTeams}
              />
            </div>
            <button
              type="button"
              className="btn-compare"
              onClick={loadComparison}
              disabled={!canCompare}
            >
              {comparing ? "Анализируем..." : "Сравнить"}
            </button>
          </div>

          {comparing && (
            <div className="loading" style={{ padding: "20px 0" }}>
              <div className="spinner" />
              <div>Анализируем данные...</div>
            </div>
          )}

          {compareError && (
            <div className="page-error page-error-soft">{compareError}</div>
          )}
        </div>

        <div className="compare-results-panel compare-results-panel-redesign">
          {!comparing && results && results.labels && results.labels.length > 0 && (
            <div className="compare-result-shell" style={{ animation: "fadeIn 0.3s ease-out" }}>
              <div className="compare-result-summary">
                <div className="compare-summary-participant red">
                  <span>{results.data1?.code || "P1"}</span>
                  <strong>{selectedName1}</strong>
                </div>
                <div className="compare-summary-outcome">
                  <span>Лидер по очкам</span>
                  <strong>{comparisonLeader}</strong>
                  <small>{pointsLead > 0 ? `Преимущество ${pointsLead} очк.` : "Результат равный"}</small>
                </div>
                <div className="compare-summary-participant cyan">
                  <span>{results.data2?.code || "P2"}</span>
                  <strong>{selectedName2}</strong>
                </div>
              </div>
              <div className="stats-grid compare-stats-grid">
                <div className="stat-card">
                  <div className="stat-title">Гонки</div>
                  <div className="stat-score">
                    <span className="s-d1">{raceScore1}</span> : <span className="s-d2">{raceScore2}</span>
                  </div>
                  <div className="compare-stat-caption">Выигранные этапы</div>
                </div>
                <div className="stat-card">
                  <div className="stat-title">{tab === "drivers" ? "Квалификации" : "Лидирование"}</div>
                  <div className="stat-score">
                    <span className="s-d1">{tab === "drivers" ? (results.q_score?.[0] ?? 0) : raceScore1}</span> :{" "}
                    <span className="s-d2">{tab === "drivers" ? (results.q_score?.[1] ?? 0) : raceScore2}</span>
                  </div>
                  <div className="compare-stat-caption">Очное преимущество</div>
                </div>
                <div className="stat-card">
                  <div className="stat-title">Сумма очков</div>
                  <div className="stat-score">
                    <span className="s-d1">{totalPts1}</span> : <span className="s-d2">{totalPts2}</span>
                  </div>
                  <div className="compare-stat-caption">За выбранный сезон</div>
                </div>
              </div>
              <div className="chart-container compare-chart-container">
                <div className="compare-chart-head">
                  <div>
                    <h3>Очки по этапам</h3>
                    <p>Фактический результат каждого совместного этапа сезона</p>
                  </div>
                </div>
                <div className="chart-container compare-chart-canvas-wrap">
                  <canvas ref={chartRef} />
                </div>
              </div>
              <div className="compare-facts-grid">
                <article>
                  <span>Итог сравнения</span>
                  <strong>{comparisonLeader}</strong>
                  <small>{pointsLead ? `+${pointsLead} очков` : "равенство по очкам"}</small>
                </article>
                <article>
                  <span>Средний разрыв</span>
                  <strong>{averageGap.toFixed(1)}</strong>
                  <small>очка за этап</small>
                </article>
                <article>
                  <span>Этапов в выборке</span>
                  <strong>{comparedRounds}</strong>
                  <small>совместных результатов</small>
                </article>
              </div>
            </div>
          )}
          {!comparing && (!results || !results.labels || results.labels.length === 0) && !compareError && (
            <div className="empty-state compare-empty-state">
              <span className="empty-icon">📈</span>
              <div className="empty-title">Выберите участников</div>
              <div className="empty-desc">Укажите двух пилотов или две команды, затем нажмите "Сравнить".</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default ComparePage;
