import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
} from "react";
import { Chart, type ChartConfiguration, registerables } from "chart.js";
import { CompareParticipantPicker } from "./CompareParticipantPicker";
import { TeamLogo } from "../../components/TeamLogo";
import { HomeIcon } from "../index/HomeIcon";
import "../index/glass-switch.css";
import { DriverPortrait } from "../../components/DriverPortrait";
import { getTheme, subscribeTheme } from "../../helpers/theme";
import { homeTeamIdentity } from "../index/team-identity";
import "../index/home-team-colors.css";
import "../../assets/entrant-highlight.css";
import "./compare.css";
import { YearSelect } from "../../components/YearSelect";
import { Link } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import { hapticSelection } from "../../helpers/telegram";
import {
  assignDriverColors,
  chartSeriesColor,
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

function ComparePage() {
  const theme = useSyncExternalStore(subscribeTheme, getTheme);
  const [retry, setRetry] = useState(0);
  const [driverError, setDriverError] = useState<string | null>(null);
  const [teamError, setTeamError] = useState<string | null>(null);
  const seasonRef = useRef(currentRealYear);
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
  const chartRef = useRef<HTMLCanvasElement>(null);
  const chartInstanceRef = useRef<Chart | null>(null);
  const selectionRef = useRef<HTMLElement>(null);
  const pickerButtonRef = useRef<HTMLButtonElement>(null);
  const requestSequenceRef = useRef(0);

  const loadDriversList = useCallback(async (season: number) => {
    setLoadingDrivers(true);
    setDriverError(null);
    try {
      const data = await apiRequest<DriversResponse>("/api/drivers", { season });
      if (season !== seasonRef.current) return;
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
      if (season !== seasonRef.current) return;
      setDrivers([]);
      setSelectedDriverCodes([]);
      setDriverError("Не удалось загрузить пилотов выбранного сезона.");
    } finally {
      if (season === seasonRef.current) setLoadingDrivers(false);
    }
  }, []);

  const loadTeamsList = useCallback(async (season: number) => {
    setLoadingTeams(true);
    setTeamError(null);
    try {
      const data = await apiRequest<ConstructorsResponse>("/api/constructors", { season });
      if (season !== seasonRef.current) return;
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
      if (season !== seasonRef.current) return;
      setTeams([]);
      setSelectedTeams([]);
      setTeamError("Не удалось загрузить команд выбранного сезона.");
    } finally {
      if (season === seasonRef.current) setLoadingTeams(false);
    }
  }, []);

  useEffect(() => {
    void loadDriversList(year);
    void loadTeamsList(year);
  }, [year, loadDriversList, loadTeamsList]);

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
  }, [tab, year, loadingDrivers, selectedDriverCodes, retry]);

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
  }, [tab, year, loadingTeams, selectedTeams, retry]);

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

  const visibleSeries = useMemo<ColoredCompareSeries[]>(() => {
    if (tab === "drivers") {
      const responseSeries = driverResults?.series || [];
      return responseSeries.map((series) => {
        const driver = drivers.find((item) => item.code === series.code);
        return {
          ...series,
          color: chartSeriesColor(driverColors[series.code] || "#E10600", theme === "dark"),
          name: driver?.name || series.code,
          teamName: driver?.constructorName || "Команда не указана",
        };
      });
    }

    return (teamResults?.series || []).map((series) => ({
      ...series,
      color: chartSeriesColor(teamColors[series.code] || "#E10600", theme === "dark"),
      name: series.code,
      teamName: series.code,
    }));
  }, [tab, driverResults, drivers, driverColors, teamResults, teamColors, theme]);

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
    const tokens = getComputedStyle(document.documentElement);
    const ink = tokens.getPropertyValue("--design-ink").trim();
    const muted = tokens.getPropertyValue("--design-muted").trim();
    const surface = tokens.getPropertyValue("--design-surface").trim();
    const grid = tokens.getPropertyValue("--design-line").trim();
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const participantsCount = visibleSeries.length;
    const lineWidth = participantsCount <= 4 ? 2.7 : participantsCount <= 10 ? 1.9 : 1.25;
    const pointRadius = participantsCount <= 5 ? 2.6 : participantsCount <= 10 ? 1.5 : 0;

    const config: ChartConfiguration<"line"> = {
      type: "line",
      data: {
        labels,
        datasets: visibleSeries.map((series, index) => ({
          label: series.name,
          data: series.history,
          borderColor: series.color,
          borderDash: index === 0 ? [] : index === 1 ? [8,4] : [2,4],
          backgroundColor: rgbaFromHex(series.color, 0.16),
          pointBackgroundColor: series.color,
          pointBorderColor: surface,
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
        animation: { duration: reduceMotion || participantsCount > 10 ? 0 : 260 },
        interaction: { mode: "index", intersect: false },
        layout: { padding: { top: 8, right: 8, bottom: 4, left: 2 } },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: surface,
            borderColor: grid,
            borderWidth: 1,
            titleColor: ink,
            bodyColor: ink,
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
            grid: { color: grid },
            ticks: {
              color: muted,
              padding: 8,
              precision: 0,
            },
            border: { color: grid },
          },
          x: {
            grid: { color: grid },
            ticks: {
              color: muted,
              autoSkip: true,
              maxTicksLimit: 12,
              maxRotation: 0,
              minRotation: 0,
            },
            border: { color: grid },
          },
        },
      },
    };

    chartInstanceRef.current = new Chart(context, config);
    return () => {
      chartInstanceRef.current?.destroy();
      chartInstanceRef.current = null;
    };
  }, [labels, visibleSeries, theme]);

  const handleYearChange = (nextYear: number) => {
    if (nextYear === year || nextYear < 1950 || nextYear > currentRealYear + 1) return;
    requestSequenceRef.current += 1;
    seasonRef.current = nextYear;
    setLoadingDrivers(true);
    setLoadingTeams(true);
    setYear(nextYear);
    setSelectedDriverCodes([]);
    setSelectedTeams([]);
    setDriverResults(null);
    setTeamResults(null);
    setCompareError(null);
    setPickerOpen(false);
  };

  const switchTab = (nextTab: CompareTab) => {
    if (nextTab === tab) return;
    hapticSelection();
    requestSequenceRef.current += 1;
    setTab(nextTab);
    setCompareError(null);
    setPickerOpen(false);
  };

  const closePicker = () => {
    setPickerOpen(false);
    requestAnimationFrame(() => {
      const trigger = pickerButtonRef.current;
      if (trigger && !trigger.disabled) trigger.focus();
      else selectionRef.current?.focus();
    });
  };

  const addParticipants = (codes: string[]) => {
    hapticSelection();
    if (tab === "drivers") setSelectedDriverCodes(current => [...new Set([...current, ...codes])]);
    else setSelectedTeams(current => [...new Set([...current, ...codes])]);
    closePicker();
  };

  const removeDriver = (code: string) => {
    hapticSelection();
    setSelectedDriverCodes((current) => current.filter((item) => item !== code));
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

  const optionsError = tab === "drivers" ? driverError : teamError;
  const error = optionsError || compareError;
  const participants = tab === "drivers"
    ? selectedDrivers.map(driver => ({ code: driver.code, name: driver.name, team: driver.constructorName || "Команда не указана", color: driverColors[driver.code], src: driver.imageUrl }))
    : selectedTeamOptions.map(team => ({ code: team.name, name: team.name, team: `Сезон ${year}`, color: teamColors[team.name], src: undefined }));
  const availableCount = tab === "drivers" ? drivers.length - selectedCount : teams.length - selectedCount;

  return (
    <div className="comparison-page">
      <header className="comparison-heading">
        <div>
          <h1>{tab === "drivers" ? "Сравнение пилотов" : "Сравнение команд"}</h1>
          <p>Сопоставьте результаты за сезон: гонки, квалификации и очки.</p>
        </div>
        <div className="comparison-tools">
          <YearSelect value={year} onChange={handleYearChange} minYear={1950} maxYear={currentRealYear + 1} showCurrentYearBtn={false} />
          <Link to="/history" className="comparison-history">История сезонов<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M8 5h11v11M19 5 5 19" /></svg></Link>
        </div>
      </header>

      <section ref={selectionRef} tabIndex={-1} className="comparison-controls" aria-labelledby="comparison-selection-title">
        <div className="comparison-section-top">
          <div className="comparison-selection-heading"><h2 id="comparison-selection-title">Участники</h2><span>{isLoadingOptions ? "Загрузка…" : `${selectedCount} из ${tab === "drivers" ? drivers.length : teams.length}`}</span></div>
          <div className="comparison-switch" role="group" aria-label="Кого сравнить" style={{ "--section-position": tab === "drivers" ? 0 : 1, "--section-count": 2 } as CSSProperties}>
            <span className="home-section-light" aria-hidden="true" />
            <span className="home-section-lens" aria-hidden="true" />
            <button type="button" aria-pressed={tab === "drivers"} onClick={() => switchTab("drivers")}><HomeIcon name="drivers" /><span>Пилоты</span></button>
            <button type="button" aria-pressed={tab === "teams"} onClick={() => switchTab("teams")}><HomeIcon name="teams" /><span>Команды</span></button>
          </div>
        </div>
        <div className="comparison-participants" aria-busy={isLoadingOptions}>
          {isLoadingOptions && [0,1].map(index => <div className="comparison-skeleton comparison-participant" key={index} />)}
          {!isLoadingOptions && participants.map(person => <article className="comparison-participant entrant-highlight" key={person.code} data-team={homeTeamIdentity("", tab === "drivers" ? person.team : person.name)}>
            {tab === "drivers" ? <DriverPortrait key={`${year}-${person.code}`} code={person.code} name={person.name} season={year} src={person.src} /> : <TeamLogo key={`${year}:${person.name}`} name={person.name} season={year} />}
            <div className="comparison-person-copy"><span className="comparison-code"><i style={{ background: person.color }} aria-hidden="true" />{tab === "drivers" ? person.code : "Команда"}</span><h3>{person.name}</h3><p>{person.team}</p></div>
            <button type="button" className="comparison-remove" onClick={() => tab === "drivers" ? removeDriver(person.code) : removeTeam(person.code)} aria-label={`Удалить ${person.name} из сравнения`}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button>
          </article>)}
        </div>
        <div className="comparison-selection-actions">
          {!isLoadingOptions && <button ref={pickerButtonRef} type="button" className="comparison-add" disabled={availableCount === 0} aria-haspopup="dialog" aria-expanded={pickerOpen} onClick={() => { hapticSelection(); setPickerOpen(true); }}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>{tab === "drivers" ? "Добавить пилотов" : "Добавить команды"}</button>}
          {pickerOpen && <CompareParticipantPicker
            season={year} teamMode={tab === "teams"}
            options={tab === "drivers"
              ? drivers.filter(driver => !selectedDriverCodes.includes(driver.code)).map(driver => ({ ...driver, team: driver.constructorName }))
              : teams.filter(team => !selectedTeams.includes(team.name)).map(team => ({ code: team.name, name: team.name }))}
            onAdd={addParticipants} onClose={closePicker}
          />}
          {!isLoadingOptions && selectedCount > 0 && <button type="button" className="comparison-clear" onClick={clearParticipants}>Удалить всех</button>}
          <span className="comparison-auto-status" role="status">{comparing ? "Обновляем сравнение…" : "Сравнение обновляется автоматически"}</span>
        </div>
      </section>

      {error && <div className="comparison-error" role="alert"><p>{error}</p><button type="button" onClick={() => { if (optionsError) { if (tab === "drivers") void loadDriversList(year); else void loadTeamsList(year); } else setRetry(value => value + 1); }}>Повторить</button></div>}
      <section className="comparison-results" aria-label="Результаты сравнения" aria-busy={comparing}>
        {(isLoadingOptions || comparing) && !hasResults && <div className="comparison-loading" role="status"><div className="comparison-skeleton" /><p>Загружаем результаты…</p></div>}
        {hasResults && !isLoadingOptions && <>
          <div className="comparison-summary">
            <div><h2>{pointsLead === 0 && runnerUp ? "Равенство по очкам" : "Лидер сравнения"}</h2><p className="comparison-leader">{pointsLead === 0 && runnerUp ? `${leader.name} и ${runnerUp.name}` : leader?.name}</p><p>{runnerUp ? `Разрыв между первыми двумя: ${pointsLead.toFixed(pointsLead % 1 ? 1 : 0)} очк.` : "Индивидуальная аналитика сезона"}</p></div>
            <dl className="comparison-facts"><div><dt>Гонок в выборке</dt><dd>{labels.length}</dd></div><div><dt>Средний разрыв</dt><dd>{averageGap.toFixed(1)} <span>очк. / гонку</span></dd></div></dl>
          </div>
          <section className="comparison-ranking" aria-labelledby="comparison-table-title">
            <h2 id="comparison-table-title">Сводная таблица</h2>
            <p id="comparison-metrics-note" className="comparison-note">Лидерство в гонке и квалификации — лучший результат среди выбранных участников, включая ничьи. Очки чемпионата включают спринты и корректировки; среднее — только основные гонки.</p>
            <div className="comparison-table-scroll" role="region" aria-label="Сводная таблица участников" tabIndex={0}>
              <table aria-describedby="comparison-metrics-note"><thead><tr><th scope="col">{tab === "drivers" ? "Пилот" : "Команда"}</th><th scope="col">Лидерство<br />в гонках</th><th scope="col">Лидерство<br />в квалификациях</th><th scope="col">Средние очки<br />за гонку</th><th scope="col">Очки<br />чемпионата</th></tr></thead>
                <tbody>{rankedSeries.map((series, index) => <tr key={series.code}><th scope="row"><div className="comparison-table-identity"><span className="comparison-rank">{index + 1}</span><i style={{ background: series.color }} aria-hidden="true" /><span>{series.name}<small>{tab === "drivers" ? series.code : series.teamName}</small></span></div></th><td>{series.race_wins}</td><td>{series.quali_samples ? `${series.quali_wins} из ${series.quali_samples}` : "—"}</td><td>{series.average_points.toFixed(1)}</td><td><strong>{series.total_points.toFixed(series.total_points % 1 ? 1 : 0)}</strong></td></tr>)}</tbody>
              </table>
            </div>
          </section>
          <section className="comparison-chart" aria-labelledby="comparison-chart-title">
            <h2 id="comparison-chart-title">Очки по этапам</h2><p className="comparison-note">Основные гонки сезона {year}, без спринтов.</p>
            <div className="comparison-chart-canvas"><canvas ref={chartRef} role="img" aria-label="Очки участников по Гран-при. Точные значения доступны в раскрывающейся таблице ниже." /></div>
            <div className="comparison-legend" aria-label="Легенда графика">{visibleSeries.map((series,index) => <span key={series.code}><svg width="24" height="12" viewBox="0 0 24 12" aria-hidden="true"><path d="M0 6h24" stroke={series.color} strokeWidth="3" strokeDasharray={index === 0 ? undefined : index === 1 ? "8 4" : "2 4"} /></svg><strong>{series.name}</strong></span>)}</div>
            <details className="comparison-exact"><summary>Точные очки по этапам</summary><div className="comparison-table-scroll" role="region" aria-label="Очки по этапам" tabIndex={0}><table><caption>Основные гонки сезона {year}, без спринтов</caption><thead><tr><th scope="col">Этап</th>{visibleSeries.map(series => <th scope="col" key={series.code}>{series.name}</th>)}</tr></thead><tbody>{labels.map((label, index) => <tr key={`${index}-${label}`}><th scope="row">{label}</th>{visibleSeries.map(series => <td key={series.code}>{series.history[index] ?? "—"}</td>)}</tr>)}</tbody></table></div></details>
          </section>
        </>}
        {!isLoadingOptions && !comparing && !hasResults && !error && <div className="comparison-empty"><svg width="64" height="64" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M7 10v28h34M12 31l8-8 7 5 12-15M12 21l8 5 7-9 12 6" /></svg><h2>{selectedCount ? "Пока нет результатов" : (tab === "drivers" ? drivers.length : teams.length) ? "Добавьте участника" : "В этом сезоне пока нет участников"}</h2><p>{selectedCount ? "Сравнение появится после публикации результатов гонок." : (tab === "drivers" ? drivers.length : teams.length) ? "Выберите пилотов или команды выше — сравнение появится автоматически." : "Выберите другой сезон."}</p></div>}
      </section>
    </div>
  );
}

export default ComparePage;
