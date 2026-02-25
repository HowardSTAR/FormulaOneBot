import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { formatDateToText } from "../../helpers";
import type { NextRaceResponse, SessionItem } from "../../context/HeroDataContext";

const SESSION_DURATION_MS = 90 * 60 * 1000;

type HeroProps = {
  nextRace: NextRaceResponse | null;
  schedule: SessionItem[];
  userTz: string;
};

function Hero({ nextRace, schedule, userTz }: HeroProps) {
  const [status, setStatus] = useState<"future" | "running" | "completed">("completed");
  const [timerText, setTimerText] = useState("--:--:--");
  const [dateText, setDateText] = useState("--.--");
  const [subLabel, setSubLabel] = useState("БЛИЖАЙШИЙ ЭТАП");
  const [showTimer, setShowTimer] = useState(false);

  // Dynamic timer from weekend schedule (like web/app)
  useEffect(() => {
    if (!schedule.length) return;

    function update() {
      const now = Date.now();
      let found: SessionItem | null = null;
      let st: "future" | "running" | "completed" = "completed";

      for (const session of schedule) {
        const utcIso = session.utc_iso;
        if (!utcIso) continue;
        const startTime = new Date(utcIso).getTime();
        const endTime = startTime + SESSION_DURATION_MS;

        if (now < startTime) {
          found = session;
          st = "future";
          break;
        } else if (now >= startTime && now <= endTime) {
          found = session;
          st = "running";
          break;
        }
      }

      setStatus(st);

      if (!found) {
        setSubLabel("УИК-ЭНД ЗАВЕРШЕН");
        setShowTimer(false);
        return;
      }

      setShowTimer(true);

      if (st === "running") {
        setSubLabel(`LIVE: ${found.name}`);
        setTimerText("СЕССИЯ ИДЕТ");
        const dateObj = new Date(found.utc_iso!);
        setDateText(
          dateObj.toLocaleDateString("ru-RU", {
            timeZone: userTz,
            day: "numeric",
            month: "long",
          }).toUpperCase()
        );
      } else {
        setSubLabel(found.name);
        const dateObj = new Date(found.utc_iso!);
        setDateText(
          dateObj.toLocaleDateString("ru-RU", {
            timeZone: userTz,
            day: "numeric",
            month: "long",
          }).toUpperCase()
        );
        const distance = dateObj.getTime() - now;
        const days = Math.floor(distance / (1000 * 60 * 60 * 24));
        const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((distance % (1000 * 60)) / 1000);
        let text = "";
        if (days > 0) text += `${days}д `;
        text += `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
        setTimerText(text);
      }
    }

    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [schedule, userTz]);

  // Fallback when no schedule - use next_session_iso from next-race
  useEffect(() => {
    if (schedule.length > 0) return;
    const data = nextRace;
    if (!data?.next_session_iso || !data?.next_session_name) return;

    setShowTimer(true);
    setSubLabel(data.next_session_name);

    function update() {
      const targetTime = new Date(data!.next_session_iso!).getTime();
      const now = Date.now();
      if (now >= targetTime) {
        setSubLabel(`LIVE: ${data!.next_session_name!}`);
        setTimerText("СЕССИЯ ИДЕТ");
        return;
      }
      const distance = targetTime - now;
      const days = Math.floor(distance / (1000 * 60 * 60 * 24));
      const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((distance % (1000 * 60)) / 1000);
      let text = "";
      if (days > 0) text += `${days}д `;
      text += `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
      setTimerText(text);
    }

    if (data.fmt_date || data.local || data.date) {
      const raw = data.fmt_date?.split(" ")[0] ?? data.local?.split(" ")[0] ?? data.date ?? "";
      setDateText(formatDateToText(raw));
    } else {
      const d = new Date(data.next_session_iso);
      setDateText(
        d.toLocaleDateString("ru-RU", {
          timeZone: userTz,
          day: "numeric",
          month: "long",
        }).toUpperCase()
      );
    }

    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [nextRace, schedule.length, userTz]);

  // Initial date when no timer (schedule empty, no next_session)
  useEffect(() => {
    if (schedule.length > 0 || nextRace?.next_session_iso) return;
    const data = nextRace;
    if (!data || data.status === "season_finished") return;

    if (data.next_session_iso) {
      const d = new Date(data.next_session_iso);
      setDateText(
        d.toLocaleDateString("ru-RU", {
          timeZone: userTz,
          day: "numeric",
          month: "long",
        }).toUpperCase()
      );
    } else if (data.fmt_date || data.local || data.date) {
      const raw = data.fmt_date?.split(" ")[0] ?? data.local?.split(" ")[0] ?? data.date ?? "";
      setDateText(formatDateToText(raw));
    }
  }, [nextRace, schedule.length, userTz]);

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
    return (
      <Link to="/next-race" className="btn hero-btn" id="hero-btn">
        <div className="hero-sub" id="hero-sub">ДО ВСТРЕЧИ В 2027!</div>
        <div id="hero-title" className="hero-title">Сезон завершен</div>
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
