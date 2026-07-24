import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatedTrackMap } from "../../components/AnimatedTrackMap";
import { getDisplayTimezone } from "../../helpers";
import type { NextRaceResponse, SessionItem } from "../../context/HeroDataContext";

const SESSION_DURATION_MS = 90 * 60 * 1000;

type HeroProps = {
  nextRace: NextRaceResponse | null;
  schedule: SessionItem[];
  userTz: string;
  showTrackMap?: boolean;
};

type HeroView = {
  status: "future" | "running" | "completed";
  timerText: string;
  dateText: string;
  subLabel: string;
  showTimer: boolean;
};

function formatCountdown(targetMs: number, nowMs: number): string {
  const distance = Math.max(0, targetMs - nowMs);
  const days = Math.floor(distance / (1000 * 60 * 60 * 24));
  const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((distance % (1000 * 60)) / 1000);
  return `${days > 0 ? `${days}д ` : ""}${hours.toString().padStart(2, "0")}:${minutes
    .toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

function formatSessionDate(value: string, timeZone: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("ru-RU", {
    timeZone,
    day: "numeric",
    month: "long",
  }).toUpperCase();
}

function Hero({ nextRace, schedule, userTz, showTrackMap = false }: HeroProps) {
  const [now, setNow] = useState(() => Date.now());
  const displayTz = getDisplayTimezone(userTz);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const view: HeroView = (() => {
    for (const session of schedule) {
      if (!session.utc_iso) continue;
      const start = new Date(session.utc_iso).getTime();
      if (!Number.isFinite(start)) continue;
      if (now < start) {
        return {
          status: "future",
          timerText: formatCountdown(start, now),
          dateText: formatSessionDate(session.utc_iso, displayTz),
          subLabel: session.name,
          showTimer: true,
        };
      }
      if (now <= start + SESSION_DURATION_MS) {
        return {
          status: "running",
          timerText: "СЕССИЯ ИДЕТ",
          dateText: formatSessionDate(session.utc_iso, displayTz),
          subLabel: `LIVE: ${session.name}`,
          showTimer: true,
        };
      }
    }
    if (schedule.length > 0) {
      return { status: "completed", timerText: "", dateText: "", subLabel: "УИК-ЭНД ЗАВЕРШЕН", showTimer: false };
    }

    const targetIso = nextRace?.next_session_iso || nextRace?.race_start_utc;
    const label = nextRace?.next_session_name || "ГОНКА";
    if (targetIso) {
      const target = new Date(targetIso).getTime();
      if (Number.isFinite(target)) {
        const running = now >= target && now <= target + SESSION_DURATION_MS;
        const completed = now > target + SESSION_DURATION_MS;
        return {
          status: running ? "running" : completed ? "completed" : "future",
          timerText: running ? "СЕССИЯ ИДЕТ" : completed ? "" : formatCountdown(target, now),
          dateText: formatSessionDate(targetIso, displayTz),
          subLabel: running ? `LIVE: ${label}` : label,
          showTimer: !completed,
        };
      }
    }

    return {
      status: "completed",
      timerText: "",
      dateText: nextRace?.date ? formatSessionDate(nextRace.date, displayTz) : "--.--",
      subLabel: "БЛИЖАЙШИЙ ЭТАП",
      showTimer: false,
    };
  })();

  const { status, timerText, dateText, subLabel, showTimer } = view;

  if (!nextRace?.status && !nextRace?.event_name) {
    return (
      <div className="btn hero-btn" id="hero-btn">
        <div className="hero-sub" id="hero-sub">БЛИЖАЙШИЙ ЭТАП</div>
        <div id="hero-title" className="hero-title">Загрузка...</div>
        <div id="hero-date" className="hero-date">--.--</div>
      </div>
    );
  }

  if ((nextRace.status as string) === "season_finished") {
    const nextSeason = (nextRace.season || new Date().getFullYear()) + 1;
    return (
      <Link to="/next-race" className="btn hero-btn" id="hero-btn">
        <div className="hero-sub" id="hero-sub">{`ДО ВСТРЕЧИ В ${nextSeason}!`}</div>
        <div id="hero-title" className="hero-title">Сезон завершен</div>
      </Link>
    );
  }

  if (nextRace.is_cancelled) {
    return (
      <Link to="/next-race" className="btn hero-btn" id="hero-btn">
        <div className="hero-sub" id="hero-sub">
          <span className="session-badge">ЭТАП ОТМЕНЕН</span>
        </div>
        <div id="hero-title" className="hero-title">
          {nextRace.event_name || "Ближайший этап"}
        </div>
        <div id="hero-date" className="hero-date">ОТМЕНЕН</div>
      </Link>
    );
  }

  const subDisplay = status === "running" ? (
    <span className="session-badge" style={{ background: "white", color: "#e10600" }}>
      {subLabel}
    </span>
  ) : (
    <span className="session-badge">{subLabel}</span>
  );

  return (
    <Link to="/next-race" className="btn hero-btn" id="hero-btn">
      {showTrackMap && nextRace.event_name && (
        <AnimatedTrackMap
          eventName={nextRace.event_name}
          className="index-hero-track-map"
          svgClassName="index-hero-track-svg"
          loadingClassName="index-hero-track-loading"
        />
      )}
      <div className="hero-sub" id="hero-sub">{subDisplay}</div>
      <div id="hero-title" className="hero-title">
        {nextRace.event_name || "Нет расписания"}
      </div>
      {(nextRace.status as string) !== "season_finished" && (
        <div id="hero-date" className="hero-date" style={{ display: dateText ? "inline-block" : "none" }}>
          {dateText}
        </div>
      )}
      {showTimer && (
        <div id="hero-timer" className="hero-timer" style={{ display: "block" }}>
          {timerText !== "СЕССИЯ ИДЕТ" && (
            <span style={{ fontSize: "12px", opacity: 0.8, marginRight: "4px" }}>До старта:</span>
          )}
          <span id="timer-val" style={{ fontFamily: "monospace", fontWeight: 700 }}>
            {timerText}
          </span>
        </div>
      )}
    </Link>
  );
}

export default Hero;
