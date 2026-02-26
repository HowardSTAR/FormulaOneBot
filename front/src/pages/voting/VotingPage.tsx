import { useState, useEffect, useCallback, useRef } from "react";
import { BackButton } from "../../components/BackButton";
import { apiRequest } from "../../helpers/api";
import { Chart, type ChartConfiguration, registerables } from "chart.js";
import { hapticSelection } from "../../helpers/telegram";

Chart.register(...registerables);

const currentRealYear = new Date().getFullYear();

type Race = { round: number; event_name: string; location: string; date: string };
type DriverOption = { code: string; name: string };
type SeasonResponse = { races?: Race[] };
type DriversResponse = { drivers?: DriverOption[] };
type VotesResponse = { race_votes: Record<number, number>; driver_votes: Record<number, string> };
type StatsResponse = { stats: { round: number; avg: number; count: number }[] };
type DriverStatsResponse = { stats: { driver_code: string; count: number }[] };

function VotingPage() {
  const [tab, setTab] = useState<"race" | "driver">("race");
  const year = currentRealYear;
  const [races, setRaces] = useState<Race[]>([]);
  const [drivers, setDrivers] = useState<DriverOption[]>([]);
  const [raceVotes, setRaceVotes] = useState<Record<number, number>>({});
  const [driverVotes, setDriverVotes] = useState<Record<number, string>>({});
  const [stats, setStats] = useState<StatsResponse["stats"]>([]);
  const [driverStats, setDriverStats] = useState<DriverStatsResponse["stats"]>([]);
  const [expandedRound, setExpandedRound] = useState<number | null>(null);
  const [chartExpanded, setChartExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const chartRaceRef = useRef<HTMLCanvasElement>(null);
  const chartDriverRef = useRef<HTMLCanvasElement>(null);
  const chartRaceInstanceRef = useRef<Chart | null>(null);
  const chartDriverInstanceRef = useRef<Chart | null>(null);

  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const finishedRaces = races.filter((r) => {
    const raceEnd = new Date(r.date);
    raceEnd.setDate(raceEnd.getDate() + 1);
    return raceEnd < now;
  });

  const loadData = useCallback(async (season: number) => {
    setLoading(true);
    try {
      const [seasonRes, votesRes, statsRes, driverStatsRes, driversRes] = await Promise.all([
        apiRequest<SeasonResponse>("/api/season", { season }),
        apiRequest<VotesResponse>("/api/votes/me", { season }).catch(() => ({
          race_votes: {},
          driver_votes: {},
        })),
        apiRequest<StatsResponse>("/api/votes/stats", { season }).catch(() => ({ stats: [] })),
        apiRequest<DriverStatsResponse>("/api/votes/driver-stats", { season }).catch(() => ({ stats: [] })),
        apiRequest<DriversResponse>("/api/drivers", { season }),
      ]);
      setRaces(seasonRes.races || []);
      setRaceVotes(votesRes.race_votes || {});
      setDriverVotes(votesRes.driver_votes || {});
      setStats(statsRes.stats || []);
      setDriverStats(driverStatsRes.stats || []);
      setDrivers(driversRes.drivers || []);
    } catch (e) {
      console.error(e);
      setRaces([]);
      setStats([]);
      setDriverStats([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(year);
  }, [year, loadData]);

  // График гонок: линия с точками (средняя оценка по этапам)
  useEffect(() => {
    const el = chartRaceRef.current;
    if (!el || tab !== "race") return;
    const ctx = el.getContext("2d");
    if (!ctx) return;

    chartRaceInstanceRef.current?.destroy();
    chartRaceInstanceRef.current = null;

    const statsMap = Object.fromEntries(stats.map((s) => [s.round, s.avg]));
    const labels = finishedRaces.map((r) => `R${r.round}`);
    const data = finishedRaces.map((r) => statsMap[r.round] ?? 0);

    const config: ChartConfiguration<"line"> = {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Средняя оценка",
            data,
            borderColor: "#e10600",
            backgroundColor: "rgba(225, 6, 0, 0.1)",
            fill: true,
            pointRadius: 5,
            pointHoverRadius: 8,
            tension: 0.3,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 24, right: 24, bottom: 24, left: 24 } },
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { color: "rgba(255,255,255,0.1)" },
            ticks: { color: "rgba(255,255,255,0.8)", padding: 8 },
          },
          y: {
            min: -0.3,
            max: 5.3,
            grid: { color: "rgba(255,255,255,0.1)" },
            ticks: { color: "rgba(255,255,255,0.8)", padding: 8 },
          },
        },
      },
    };
    chartRaceInstanceRef.current = new Chart(ctx, config);
    return () => chartRaceInstanceRef.current?.destroy();
  }, [stats, finishedRaces, tab, chartExpanded]);

  // График пилотов: столбцы (голоса за пилота дня)
  useEffect(() => {
    const el = chartDriverRef.current;
    if (!el || tab !== "driver") return;
    const ctx = el.getContext("2d");
    if (!ctx) return;

    chartDriverInstanceRef.current?.destroy();
    chartDriverInstanceRef.current = null;

    const labels = driverStats.map((s) => s.driver_code);
    const data = driverStats.map((s) => s.count);

    const config: ChartConfiguration<"bar"> = {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Голоса «Пилот дня»",
            data,
            backgroundColor: "rgba(225, 6, 0, 0.6)",
            borderColor: "#e10600",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 20, right: 24, bottom: 20, left: 24 } },
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "rgba(255,255,255,0.8)", maxRotation: 45 },
          },
          y: {
            min: 0,
            suggestedMax: (data.length ? Math.max(...data, 1) : 1) * 1.15,
            grid: { color: "rgba(255,255,255,0.1)" },
            ticks: { color: "rgba(255,255,255,0.8)", padding: 8 },
          },
        },
      },
    };
    chartDriverInstanceRef.current = new Chart(ctx, config);
    return () => chartDriverInstanceRef.current?.destroy();
  }, [driverStats, tab, chartExpanded]);

  const handleRaceVote = async (round: number, rating: number) => {
    hapticSelection();
    setSaving(round);
    try {
      await apiRequest("/api/votes/race", { season: year, round, rating }, "POST");
      setRaceVotes((prev) => ({ ...prev, [round]: rating }));
      const [statsRes] = await Promise.all([
        apiRequest<StatsResponse>("/api/votes/stats", { season: year }),
      ]);
      setStats(statsRes.stats || []);
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(null);
    }
  };

  const handleDriverVote = async (round: number, driverCode: string) => {
    hapticSelection();
    setSaving(round);
    try {
      await apiRequest("/api/votes/driver", { season: year, round, driver_code: driverCode }, "POST");
      setDriverVotes((prev) => ({ ...prev, [round]: driverCode }));
      const [driverStatsRes] = await Promise.all([
        apiRequest<DriverStatsResponse>("/api/votes/driver-stats", { season: year }),
      ]);
      setDriverStats(driverStatsRes.stats || []);
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(null);
    }
  };

  const toggleAccordion = (round: number) => {
    hapticSelection();
    setExpandedRound((prev) => (prev === round ? null : round));
  };

  return (
    <>
      <BackButton>← Главное меню</BackButton>
      <h2>Голосование</h2>
      <div className="voting-season-title">СЕЗОН {year}</div>

      <div className="segmented-tabs">
        <div
          className="segmented-slider"
          style={{ transform: tab === "race" ? "translateX(0)" : "translateX(100%)" }}
          aria-hidden
        />
        <button
          type="button"
          className={`segmented-tab ${tab === "race" ? "active" : ""}`}
          onClick={() => {
            hapticSelection();
            setTab("race");
          }}
        >
          Гонка
        </button>
        <button
          type="button"
          className={`segmented-tab ${tab === "driver" ? "active" : ""}`}
          onClick={() => {
            hapticSelection();
            setTab("driver");
          }}
        >
          Пилот дня
        </button>
      </div>

      {loading && <div className="loading full-width">Загрузка...</div>}

      {!loading && (
        <>
          {/* График — скрыт по умолчанию, раскрывается по клику */}
          {tab === "race" && (
            <div className="voting-chart-accordion">
              <button
                type="button"
                className={`voting-chart-toggle ${chartExpanded ? "expanded" : ""}`}
                onClick={() => {
                  hapticSelection();
                  setChartExpanded((v) => !v);
                }}
              >
                <span>📊 Средняя оценка гонок по этапам</span>
                <span className="voting-accordion-chevron">{chartExpanded ? "▼" : "▶"}</span>
              </button>
              <div className={`voting-chart-body ${chartExpanded ? "expanded" : ""}`}>
                <div className="voting-accordion-inner">
                  {chartExpanded && (
                    <div className="voting-chart">
                      <canvas ref={chartRaceRef} />
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          {tab === "driver" && (
            <div className="voting-chart-accordion">
              <button
                type="button"
                className={`voting-chart-toggle ${chartExpanded ? "expanded" : ""}`}
                onClick={() => {
                  hapticSelection();
                  setChartExpanded((v) => !v);
                }}
              >
                <span>📊 Голоса «Пилот дня» за сезон</span>
                <span className="voting-accordion-chevron">{chartExpanded ? "▼" : "▶"}</span>
              </button>
              <div className={`voting-chart-body ${chartExpanded ? "expanded" : ""}`}>
                <div className="voting-accordion-inner">
                  {chartExpanded && (
                    <div className="voting-chart">
                      <canvas ref={chartDriverRef} />
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="voting-accordion-list">
            {finishedRaces.map((race) => {
              const isExpanded = expandedRound === race.round;
              const myRaceVote = raceVotes[race.round];
              const myDriverVote = driverVotes[race.round];
              const isSaving = saving === race.round;
              const raceDate = new Date(race.date);
              raceDate.setHours(0, 0, 0, 0);
              const driverVotingEnds = new Date(raceDate);
              driverVotingEnds.setDate(driverVotingEnds.getDate() + 3);
              const driverVotingClosed = now >= driverVotingEnds;

              return (
                <div key={race.round} className="voting-accordion-item">
                  <button
                    type="button"
                    className={`voting-accordion-header ${isExpanded ? "expanded" : ""}`}
                    onClick={() => toggleAccordion(race.round)}
                  >
                    <span className="voting-accordion-title">
                      R{race.round} — {race.event_name}
                    </span>
                    <span className="voting-accordion-badge">
                      {tab === "race"
                        ? myRaceVote
                          ? `★ ${myRaceVote}`
                          : "—"
                        : myDriverVote
                          ? myDriverVote
                          : "—"}
                    </span>
                    <span className="voting-accordion-chevron">{isExpanded ? "▼" : "▶"}</span>
                  </button>
                  <div className={`voting-accordion-body ${isExpanded ? "expanded" : ""}`}>
                    <div className="voting-accordion-inner">
                      {tab === "race" && (
                        <div className="voting-stars">
                          {[1, 2, 3, 4, 5].map((r) => (
                            <button
                              key={r}
                              type="button"
                              className={`star-btn ${myRaceVote === r ? "active" : ""}`}
                              onClick={() => handleRaceVote(race.round, r)}
                              disabled={isSaving}
                            >
                              ★
                            </button>
                          ))}
                        </div>
                      )}
                      {tab === "driver" && (
                        <div className="voting-drivers">
                          {driverVotingClosed && (
                            <div className="voting-closed-msg">
                              Голосование закрыто (3 дня после гонки)
                            </div>
                          )}
                          {!driverVotingClosed &&
                            drivers.map((d) => (
                              <button
                                key={d.code}
                                type="button"
                                className={`driver-vote-btn ${myDriverVote === d.code ? "active" : ""}`}
                                onClick={() => handleDriverVote(race.round, d.code)}
                                disabled={isSaving}
                              >
                                {d.code} — {d.name}
                              </button>
                            ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {finishedRaces.length === 0 && !loading && (
            <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--text-secondary)" }}>
              Пока нет завершённых гонок для голосования
            </div>
          )}
        </>
      )}
    </>
  );
}

export default VotingPage;
