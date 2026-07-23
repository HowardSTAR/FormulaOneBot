import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { Chart, type ChartConfiguration, registerables } from "chart.js";
import { BackButton } from "../../components/BackButton";
import { YearSelect } from "../../components/YearSelect";
import { apiRequest } from "../../helpers/api";
import { hapticSelection } from "../../helpers/telegram";
import {
  assignDriverColors,
  rgbaFromHex,
  type ColoredCompareSeries,
  type CompareSeries,
  type DriverOption,
} from "./compareModel";

Chart.register(...registerables);

const currentRealYear = new Date().getFullYear();

type CompareTab = "drivers" | "teams";
type TeamOption = { name: string; is_favorite?: boolean };
type DriversResponse = { drivers?: DriverOption[] };
type ConstructorsResponse = { constructors?: TeamOption[] };
type MultiCompareResponse = {
  error?: string;
  labels?: string[];
  series?: CompareSeries[];
};
type PickerPosition = { top: number; left: number; width: number };

function teamShortCode(name: string): string {
  const meaningful = name
    .split(/\s+/)
    .filter((part) => !["f1", "team", "racing"].includes(part.toLocaleLowerCase("en")));
  const initials = meaningful.map((part) => part[0]).join("");
  return (initials.length >= 2 ? initials : name.slice(0, 3)).toUpperCase().slice(0, 3);
}

function ComparePage() {
  const [tab, setTab] = useState<CompareTab>("drivers");
  const [year, setYear] = useState(currentRealYear);
  const [drivers, setDrivers] = useState<DriverOption[]>([]);
  const [teams, setTeams] = useState<TeamOption[]>([]);
  const [selectedDriverCodes, setSelectedDriverCodes] = useState<string[]>([]);
  const [selectedTeams, setSelectedTeams] = useState<string[]>([]);
  const [loadingDrivers, setLoadingDrivers] = useState(true);
  const [loadingTeams, setLoadingTeams] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [driverResults, setDriverResults] = useState<MultiCompareResponse | null>(null);
  const [teamResults, setTeamResults] = useState<MultiCompareResponse | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerSearch, setPickerSearch] = useState("");
  const [pickerPosition, setPickerPosition] = useState<PickerPosition | null>(null);
  const chartRef = useRef<HTMLCanvasElement>(null);
  const chartInstanceRef = useRef<Chart | null>(null);
  const pickerRef = useRef<HTMLDivElement>(null);
  const pickerButtonRef = useRef<HTMLButtonElement>(null);
  const requestSequenceRef = useRef(0);

  const loadDriversList = useCallback(async (season: number) => {
    setLoadingDrivers(true);
    try {
      const data = await apiRequest<DriversResponse>("/api/drivers", { season });
      const list = (data.drivers || []).filter((driver) => Boolean(driver.code));
      setDrivers(list);
      setSelectedDriverCodes((current) => {
        const available = new Set(list.map((driver) => driver.code));
        const retained = current.filter((code) => available.has(code));
        return retained.length > 0
          ? retained
          : list.slice(0, Math.min(2, list.length)).map((driver) => driver.code);
      });
    } catch {
      setDrivers([]);
      setSelectedDriverCodes([]);
      setCompareError("Не удалось загрузить пилотов выбранного сезона.");
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
      setSelectedTeams((current) => {
        const available = new Set(list.map((team) => team.name));
        const retained = current.filter((name) => available.has(name));
        return retained.length > 0
          ? retained
          : list.slice(0, Math.min(2, list.length)).map((team) => team.name);
      });
    } catch {
      setTeams([]);
      setSelectedTeams([]);
      setCompareError("Не удалось загрузить команды выбранного сезона.");
    } finally {
      setLoadingTeams(false);
    }
  }, []);

  useEffect(() => {
    void loadDriversList(year);
    void loadTeamsList(year);
  }, [year, loadDriversList, loadTeamsList]);

  useEffect(() => {
    const closePicker = (event: PointerEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setPickerOpen(false);
      }
    };
    const closePickerOnViewportChange = () => setPickerOpen(false);
    document.addEventListener("pointerdown", closePicker);
    window.addEventListener("resize", closePickerOnViewportChange);
    window.addEventListener("scroll", closePickerOnViewportChange, true);
    return () => {
      document.removeEventListener("pointerdown", closePicker);
      window.removeEventListener("resize", closePickerOnViewportChange);
      window.removeEventListener("scroll", closePickerOnViewportChange, true);
    };
  }, []);

  useEffect(() => {
    if (tab !== "drivers" || loadingDrivers) return;
    if (selectedDriverCodes.length === 0) {
      requestSequenceRef.current += 1;
      setDriverResults(null);
      setComparing(false);
      setCompareError(null);
      return;
    }
    const requestId = ++requestSequenceRef.current;
    setComparing(true);
    setCompareError(null);

    void apiRequest<MultiCompareResponse>("/api/compare/multi", {
      drivers: selectedDriverCodes.join(","),
      season: year,
    })
      .then((response) => {
        if (requestId !== requestSequenceRef.current) return;
        if (response.error || !response.series || !response.labels) {
          setDriverResults(null);
          setCompareError(response.error || "Данные для сравнения пока недоступны.");
          return;
        }
        setDriverResults(response);
      })
      .catch((error: unknown) => {
        if (requestId !== requestSequenceRef.current) return;
        setDriverResults(null);
        setCompareError(error instanceof Error ? error.message : "Ошибка загрузки сравнения.");
      })
      .finally(() => {
        if (requestId === requestSequenceRef.current) setComparing(false);
      });

    return () => {
      if (requestSequenceRef.current === requestId) requestSequenceRef.current += 1;
    };
  }, [tab, year, loadingDrivers, selectedDriverCodes]);

  useEffect(() => {
    if (tab !== "teams" || loadingTeams) {
      return;
    }
    if (selectedTeams.length === 0) {
      requestSequenceRef.current += 1;
      setTeamResults(null);
      setComparing(false);
      setCompareError(null);
      return;
    }
    const requestId = ++requestSequenceRef.current;
    setComparing(true);
    setCompareError(null);

    void apiRequest<MultiCompareResponse>("/api/compare/teams/multi", {
      teams: selectedTeams.join(","),
      season: year,
    })
      .then((response) => {
        if (requestId !== requestSequenceRef.current) return;
        if (response.error || !response.series || !response.labels) {
          setTeamResults(null);
          setCompareError(response.error || "Данные для сравнения пока недоступны.");
          return;
        }
        setTeamResults(response);
      })
      .catch((error: unknown) => {
        if (requestId !== requestSequenceRef.current) return;
        setTeamResults(null);
        setCompareError(error instanceof Error ? error.message : "Ошибка загрузки сравнения.");
      })
      .finally(() => {
        if (requestId === requestSequenceRef.current) setComparing(false);
      });

    return () => {
      if (requestSequenceRef.current === requestId) requestSequenceRef.current += 1;
    };
  }, [tab, year, loadingTeams, selectedTeams]);

  const selectedDrivers = useMemo(
    () =>
      selectedDriverCodes
        .map((code) => drivers.find((driver) => driver.code === code))
        .filter((driver): driver is DriverOption => Boolean(driver)),
    [drivers, selectedDriverCodes]
  );

  const driverColors = useMemo(
    () => assignDriverColors(selectedDrivers),
    [selectedDrivers]
  );

  const availableDrivers = useMemo(() => {
    const selected = new Set(selectedDriverCodes);
    const query = pickerSearch.trim().toLocaleLowerCase("ru");
    return drivers.filter((driver) => {
      if (selected.has(driver.code)) return false;
      if (!query) return true;
      return `${driver.name} ${driver.code} ${driver.constructorName || ""}`
        .toLocaleLowerCase("ru")
        .includes(query);
    });
  }, [drivers, pickerSearch, selectedDriverCodes]);

  const selectedTeamOptions = useMemo(
    () =>
      selectedTeams
        .map((name) => teams.find((team) => team.name === name))
        .filter((team): team is TeamOption => Boolean(team)),
    [teams, selectedTeams]
  );

  const teamColors = useMemo(
    () =>
      assignDriverColors(
        selectedTeamOptions.map((team) => ({
          code: team.name,
          name: team.name,
          constructorName: team.name,
        }))
      ),
    [selectedTeamOptions]
  );

  const availableTeams = useMemo(() => {
    const selected = new Set(selectedTeams);
    const query = pickerSearch.trim().toLocaleLowerCase("ru");
    return teams.filter((team) => {
      if (selected.has(team.name)) return false;
      return !query || team.name.toLocaleLowerCase("ru").includes(query);
    });
  }, [teams, pickerSearch, selectedTeams]);

  const visibleSeries = useMemo<ColoredCompareSeries[]>(() => {
    if (tab === "drivers") {
      const responseSeries = driverResults?.series || [];
      return responseSeries.map((series) => {
        const driver = drivers.find((item) => item.code === series.code);
        return {
          ...series,
          color: driverColors[series.code] || "#E10600",
          name: driver?.name || series.code,
          teamName: driver?.constructorName || "Команда не указана",
        };
      });
    }

    return (teamResults?.series || []).map((series) => ({
      ...series,
      color: teamColors[series.code] || "#E10600",
      name: series.code,
      teamName: series.code,
    }));
  }, [tab, driverResults, drivers, driverColors, teamResults, teamColors]);

  const labels = useMemo(
    () => (tab === "drivers" ? driverResults?.labels || [] : teamResults?.labels || []),
    [tab, driverResults?.labels, teamResults?.labels]
  );
  const rankedSeries = useMemo(
    () =>
      [...visibleSeries].sort(
        (left, right) =>
          right.total_points - left.total_points ||
          right.race_wins - left.race_wins ||
          left.name.localeCompare(right.name, "ru")
      ),
    [visibleSeries]
  );

  useEffect(() => {
    if (!chartRef.current || visibleSeries.length === 0 || labels.length === 0) return;
    const context = chartRef.current.getContext("2d");
    if (!context) return;

    chartInstanceRef.current?.destroy();
    const participantsCount = visibleSeries.length;
    const lineWidth = participantsCount <= 4 ? 2.7 : participantsCount <= 10 ? 1.9 : 1.25;
    const pointRadius = participantsCount <= 5 ? 2.6 : participantsCount <= 10 ? 1.5 : 0;

    const config: ChartConfiguration<"line"> = {
      type: "line",
      data: {
        labels,
        datasets: visibleSeries.map((series) => ({
          label: series.name,
          data: series.history,
          borderColor: series.color,
          backgroundColor: rgbaFromHex(series.color, 0.16),
          pointBackgroundColor: series.color,
          pointBorderColor: "#111216",
          pointBorderWidth: participantsCount <= 8 ? 1.5 : 0,
          pointRadius,
          pointHoverRadius: 4.5,
          borderWidth: lineWidth,
          tension: participantsCount <= 8 ? 0.28 : 0.18,
          cubicInterpolationMode: "monotone",
          fill: false,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        normalized: true,
        animation: { duration: participantsCount > 10 ? 0 : 260 },
        interaction: { mode: "index", intersect: false },
        layout: { padding: { top: 8, right: 8, bottom: 4, left: 2 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(13, 14, 17, 0.96)",
            borderColor: "rgba(255,255,255,0.12)",
            borderWidth: 1,
            titleColor: "#ffffff",
            bodyColor: "#e7e3e1",
            padding: 12,
            boxPadding: 5,
            usePointStyle: true,
            itemSort: (left, right) => (right.parsed.y ?? 0) - (left.parsed.y ?? 0),
            callbacks: {
              label: (item) => `${item.dataset.label}: ${item.parsed.y ?? 0} оч.`,
              labelColor: (item) => {
                const color = String(item.dataset.borderColor || "#ffffff");
                return {
                  borderColor: color,
                  backgroundColor: color,
                  borderWidth: 2,
                  borderRadius: 4,
                };
              },
            },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            grace: 1,
            grid: { color: "rgba(255,255,255,0.075)" },
            ticks: {
              color: "rgba(227,226,227,0.62)",
              padding: 8,
              precision: 0,
            },
            border: { color: "rgba(255,255,255,0.06)" },
          },
          x: {
            grid: { color: "rgba(255,255,255,0.06)" },
            ticks: {
              color: "rgba(227,226,227,0.62)",
              autoSkip: true,
              maxTicksLimit: 12,
              maxRotation: 0,
              minRotation: 0,
            },
            border: { color: "rgba(255,255,255,0.06)" },
          },
        },
      },
    };

    chartInstanceRef.current = new Chart(context, config);
    return () => {
      chartInstanceRef.current?.destroy();
      chartInstanceRef.current = null;
    };
  }, [labels, visibleSeries]);

  const handleYearChange = (nextYear: number) => {
    if (nextYear < 1950 || nextYear > currentRealYear + 1) return;
    requestSequenceRef.current += 1;
    setYear(nextYear);
    setSelectedDriverCodes([]);
    setSelectedTeams([]);
    setDriverResults(null);
    setTeamResults(null);
    setCompareError(null);
    setPickerOpen(false);
  };

  const switchTab = (nextTab: CompareTab) => {
    hapticSelection();
    requestSequenceRef.current += 1;
    setTab(nextTab);
    setCompareError(null);
    setPickerOpen(false);
  };

  const togglePicker = () => {
    hapticSelection();
    if (pickerOpen) {
      setPickerOpen(false);
      return;
    }
    const anchor = pickerButtonRef.current?.getBoundingClientRect();
    const viewportPadding = 12;
    const width = Math.min(390, window.innerWidth - viewportPadding * 2);
    const desiredLeft = anchor?.left ?? viewportPadding;
    const left = Math.max(
      viewportPadding,
      Math.min(desiredLeft, window.innerWidth - width - viewportPadding)
    );
    const estimatedHeight = Math.min(500, window.innerHeight * 0.66);
    const belowTop = (anchor?.bottom ?? viewportPadding) + 8;
    const top =
      belowTop + estimatedHeight <= window.innerHeight - viewportPadding
        ? belowTop
        : Math.max(viewportPadding, (anchor?.top ?? viewportPadding) - estimatedHeight - 8);
    setPickerPosition({ top, left, width });
    setPickerOpen(true);
  };

  const addDriver = (code: string) => {
    hapticSelection();
    setSelectedDriverCodes((current) =>
      current.includes(code) ? current : [...current, code]
    );
    setPickerSearch("");
    setPickerOpen(false);
  };

  const addAllDrivers = () => {
    hapticSelection();
    setSelectedDriverCodes(drivers.map((driver) => driver.code));
    setPickerSearch("");
    setPickerOpen(false);
  };

  const removeDriver = (code: string) => {
    hapticSelection();
    setSelectedDriverCodes((current) => current.filter((item) => item !== code));
  };

  const addTeam = (name: string) => {
    hapticSelection();
    setSelectedTeams((current) => (current.includes(name) ? current : [...current, name]));
    setPickerSearch("");
    setPickerOpen(false);
  };

  const addAllTeams = () => {
    hapticSelection();
    setSelectedTeams(teams.map((team) => team.name));
    setPickerSearch("");
    setPickerOpen(false);
  };

  const removeTeam = (name: string) => {
    hapticSelection();
    setSelectedTeams((current) => current.filter((item) => item !== name));
  };

  const clearParticipants = () => {
    hapticSelection();
    requestSequenceRef.current += 1;
    if (tab === "drivers") {
      setSelectedDriverCodes([]);
      setDriverResults(null);
    } else {
      setSelectedTeams([]);
      setTeamResults(null);
    }
    setComparing(false);
    setCompareError(null);
    setPickerSearch("");
    setPickerOpen(false);
  };

  const leader = rankedSeries[0];
  const runnerUp = rankedSeries[1];
  const pointsLead = leader && runnerUp
    ? Math.max(0, leader.total_points - runnerUp.total_points)
    : 0;
  const averageGap = labels.length > 0 ? pointsLead / labels.length : 0;
  const hasResults = visibleSeries.length > 0 && labels.length > 0;
  const isLoadingOptions = tab === "drivers" ? loadingDrivers : loadingTeams;
  const selectedCount = tab === "drivers" ? selectedDriverCodes.length : selectedTeams.length;

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
        <section className="compare-controls-panel compare-controls-panel-redesign">
          <div className="compare-controls-topline">
            <div className="compare-controls-header">
              <div className="compare-controls-kicker">Состав сравнения</div>
              <div className="compare-controls-caption">
                {tab === "drivers"
                  ? `Выбрано: ${selectedDriverCodes.length} из ${drivers.length || "—"}`
                  : `Выбрано: ${selectedTeams.length} из ${teams.length || "—"}`}
              </div>
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
                onClick={() => switchTab("drivers")}
              >
                Пилоты
              </button>
              <button
                type="button"
                className={`segmented-tab ${tab === "teams" ? "active" : ""}`}
                onClick={() => switchTab("teams")}
              >
                Команды
              </button>
            </div>
          </div>

          <div
            className="compare-driver-selector"
            aria-busy={tab === "drivers" ? loadingDrivers : loadingTeams}
          >
            <div
              className="compare-driver-chips"
              aria-label={tab === "drivers" ? "Выбранные пилоты" : "Выбранные команды"}
            >
              {isLoadingOptions &&
                Array.from({ length: 2 }, (_, index) => (
                  <span className="compare-chip-skeleton" key={index} />
                ))}

              {!isLoadingOptions &&
                tab === "drivers" &&
                selectedDrivers.map((driver) => (
                  <div
                    className="compare-driver-chip"
                    key={driver.code}
                    style={{ "--pilot-color": driverColors[driver.code] } as CSSProperties}
                  >
                    <span className="compare-driver-chip-code">{driver.code}</span>
                    <span className="compare-driver-chip-copy">
                      <strong>{driver.name}</strong>
                      <small>{driver.constructorName || "Команда не указана"}</small>
                    </span>
                    <button
                      type="button"
                      className="compare-driver-remove"
                      onClick={() => removeDriver(driver.code)}
                      aria-label={`Удалить ${driver.name} из сравнения`}
                      title={`Удалить ${driver.name}`}
                    >
                      ×
                    </button>
                  </div>
                ))}

              {!isLoadingOptions &&
                tab === "teams" &&
                selectedTeamOptions.map((team) => (
                  <div
                    className="compare-driver-chip compare-team-chip"
                    key={team.name}
                    style={{ "--pilot-color": teamColors[team.name] } as CSSProperties}
                  >
                    <span className="compare-driver-chip-code">{teamShortCode(team.name)}</span>
                    <span className="compare-driver-chip-copy">
                      <strong>{team.name}</strong>
                      <small>{team.is_favorite ? "Избранная команда" : `Сезон ${year}`}</small>
                    </span>
                    <button
                      type="button"
                      className="compare-driver-remove"
                      onClick={() => removeTeam(team.name)}
                      aria-label={`Удалить ${team.name} из сравнения`}
                      title={`Удалить ${team.name}`}
                    >
                      ×
                    </button>
                  </div>
                ))}

              {!isLoadingOptions &&
                (tab === "drivers" ? availableDrivers.length > 0 : availableTeams.length > 0) && (
                  <div className="compare-add-driver-wrap" ref={pickerRef}>
                    <button
                      ref={pickerButtonRef}
                      type="button"
                      className="compare-add-driver"
                      onClick={togglePicker}
                      aria-expanded={pickerOpen}
                      aria-haspopup="listbox"
                    >
                      <span aria-hidden>+</span>
                      {tab === "drivers" ? "Добавить пилота" : "Добавить команду"}
                    </button>

                    {pickerOpen && pickerPosition && (
                      <div className="compare-driver-picker" style={pickerPosition}>
                        <label className="compare-driver-search">
                          <span>{tab === "drivers" ? "Поиск пилота" : "Поиск команды"}</span>
                          <input
                            autoFocus
                            value={pickerSearch}
                            onChange={(event) => setPickerSearch(event.target.value)}
                            placeholder={
                              tab === "drivers" ? "Имя, код или команда" : "Название команды"
                            }
                          />
                        </label>
                        <div className="compare-driver-options" role="listbox">
                          {tab === "drivers" &&
                            availableDrivers.length > 1 &&
                            !pickerSearch && (
                              <button
                                type="button"
                                className="compare-driver-option compare-driver-option-all"
                                onClick={addAllDrivers}
                              >
                                <span className="compare-option-plus">+</span>
                                <span>
                                  <strong>Добавить всех</strong>
                                  <small>{availableDrivers.length} доступных пилотов</small>
                                </span>
                              </button>
                            )}
                          {tab === "teams" && availableTeams.length > 1 && !pickerSearch && (
                            <button
                              type="button"
                              className="compare-driver-option compare-driver-option-all"
                              onClick={addAllTeams}
                            >
                              <span className="compare-option-plus">+</span>
                              <span>
                                <strong>Добавить все команды</strong>
                                <small>{availableTeams.length} доступных команд</small>
                              </span>
                            </button>
                          )}
                          {tab === "drivers" &&
                            availableDrivers.map((driver) => (
                              <button
                                type="button"
                                className="compare-driver-option"
                                key={driver.code}
                                onClick={() => addDriver(driver.code)}
                                role="option"
                                aria-selected={false}
                              >
                                <span className="compare-driver-option-code">{driver.code}</span>
                                <span>
                                  <strong>{driver.name}</strong>
                                  <small>{driver.constructorName || "Команда не указана"}</small>
                                </span>
                              </button>
                            ))}
                          {tab === "teams" &&
                            availableTeams.map((team) => (
                              <button
                                type="button"
                                className="compare-driver-option"
                                key={team.name}
                                onClick={() => addTeam(team.name)}
                                role="option"
                                aria-selected={false}
                              >
                                <span className="compare-driver-option-code">
                                  {teamShortCode(team.name)}
                                </span>
                                <span>
                                  <strong>{team.name}</strong>
                                  <small>{team.is_favorite ? "Избранная команда" : `Сезон ${year}`}</small>
                                </span>
                              </button>
                            ))}
                          {(tab === "drivers"
                            ? availableDrivers.length === 0
                            : availableTeams.length === 0) && (
                            <div className="compare-driver-no-options">
                              {tab === "drivers"
                                ? "Пилоты по запросу не найдены"
                                : "Команды по запросу не найдены"}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}

              {!isLoadingOptions && selectedCount > 0 && (
                <button
                  type="button"
                  className="compare-clear-all"
                  onClick={clearParticipants}
                >
                  Удалить всех
                </button>
              )}
            </div>
            {!isLoadingOptions &&
              selectedCount > 0 &&
              selectedCount === (tab === "drivers" ? drivers.length : teams.length) && (
                <div className="compare-selection-complete">
                  {tab === "drivers"
                    ? "Все пилоты сезона добавлены"
                    : "Все команды сезона добавлены"}
                </div>
              )}
          </div>

          <div className={`compare-auto-status ${comparing ? "is-loading" : ""}`}>
            <span className="compare-auto-status-dot" />
            {comparing
              ? "Обновляем аналитику…"
              : "Данные пересчитываются автоматически при изменении состава"}
          </div>
          {compareError && <div className="page-error page-error-soft">{compareError}</div>}
        </section>

        <section className="compare-results-panel compare-results-panel-redesign">
          {comparing && !hasResults && (
            <div className="compare-results-skeleton" aria-label="Загрузка сравнения">
              <div className="compare-skeleton-line wide" />
              <div className="compare-skeleton-cards">
                <span />
                <span />
                <span />
              </div>
              <div className="compare-skeleton-chart" />
            </div>
          )}

          {!comparing && hasResults && (
            <div className="compare-result-shell">
              <div className="compare-multi-summary">
                <div>
                  <span>Лидер сравнения</span>
                  <strong style={{ color: leader?.color }}>{leader?.name || "—"}</strong>
                  <small>
                    {runnerUp
                      ? `Преимущество ${pointsLead.toFixed(pointsLead % 1 ? 1 : 0)} очк.`
                      : "Индивидуальная аналитика сезона"}
                  </small>
                </div>
                <div className="compare-summary-count">
                  <strong>{visibleSeries.length}</strong>
                  <span>
                    {tab === "drivers"
                      ? visibleSeries.length === 1
                        ? "пилот"
                        : "пилотов"
                      : visibleSeries.length === 1
                        ? "команда"
                        : "команд"}
                  </span>
                </div>
              </div>

              <div className="compare-ranking-panel">
                <div className="compare-section-head">
                  <div>
                    <h3>Сводная таблица</h3>
                    <p>Все показатели обновляются вместе с составом сравнения</p>
                  </div>
                </div>
                <div className="compare-ranking-scroll">
                  <table className="compare-ranking-table">
                    <thead>
                      <tr>
                        <th>{tab === "drivers" ? "Пилот" : "Команда"}</th>
                        <th>Этапы</th>
                        <th>Квалификации</th>
                        <th>Среднее</th>
                        <th>Очки</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rankedSeries.map((series, index) => (
                        <tr key={series.code}>
                          <td>
                            <span className="compare-rank">{String(index + 1).padStart(2, "0")}</span>
                            <span
                              className="compare-series-marker"
                              style={{ backgroundColor: series.color }}
                            />
                            <span className="compare-table-driver">
                              <strong>{series.name}</strong>
                              <small>{series.code}</small>
                            </span>
                          </td>
                          <td>{series.race_wins}</td>
                          <td>{series.quali_wins}</td>
                          <td>{series.average_points.toFixed(1)}</td>
                          <td>
                            <strong style={{ color: series.color }}>
                              {series.total_points.toFixed(series.total_points % 1 ? 1 : 0)}
                            </strong>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="chart-container compare-chart-container">
                <div className="compare-chart-head">
                  <div>
                    <h3>Очки по этапам</h3>
                    <p>Динамические серии для всех выбранных участников</p>
                  </div>
                </div>
                <div className="compare-chart-canvas-wrap">
                  <canvas ref={chartRef} />
                </div>
                <div className="compare-chart-legend" aria-label="Легенда графика">
                  {visibleSeries.map((series) => (
                    <div className="compare-legend-item" key={series.code}>
                      <span style={{ backgroundColor: series.color }} />
                      <strong>{series.code}</strong>
                      <small>{series.name}</small>
                    </div>
                  ))}
                </div>
              </div>

              <div className="compare-facts-grid">
                <article>
                  <span>Этапов в выборке</span>
                  <strong>{labels.length}</strong>
                  <small>завершённых гонок</small>
                </article>
                <article>
                  <span>Средний разрыв</span>
                  <strong>{averageGap.toFixed(1)}</strong>
                  <small>очка за этап между лидерами</small>
                </article>
                <article>
                  <span>Состав</span>
                  <strong>{visibleSeries.length}</strong>
                  <small>активных серий на графике</small>
                </article>
              </div>
            </div>
          )}

          {!comparing && !hasResults && !compareError && (
            <div className="empty-state compare-empty-state">
              <svg className="empty-icon" viewBox="0 0 48 48" aria-hidden>
                <path d="M7 38V10M7 38h34M12 31l8-8 7 5 12-15" />
                <circle cx="20" cy="23" r="2.5" />
                <circle cx="27" cy="28" r="2.5" />
                <circle cx="39" cy="13" r="2.5" />
              </svg>
              <div className="empty-title">
                {isLoadingOptions ? "Загружаем участников" : "Добавьте участника"}
              </div>
              <div className="empty-desc">
                Аналитика и график появятся автоматически после выбора.
              </div>
            </div>
          )}
        </section>
      </div>
    </>
  );
}

export default ComparePage;
