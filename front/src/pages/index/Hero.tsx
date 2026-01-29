import { useEffect, useState } from "react";
import { formatDateToText } from "../../helpers";
import type { NextRaceResponse } from "./Index";

function Hero({ status, next_session_iso, next_session_name, date, event_name }: NextRaceResponse) {

    const [subIsLive, setSubIsLive] = useState(false);
    const [timerText, setTimerText] = useState("--:--:--");
    const subLabel = next_session_iso && next_session_name ? next_session_name : 
    status  === "season_finished" ? "ДО ВСТРЕЧИ В 2027!" : 
    "Нет расписания";

  // Таймер обратного отсчёта (обновляется каждую секунду)
    useEffect(() => {
        if (!next_session_iso) return;

        const targetTime = new Date(next_session_iso).getTime();

        function update() {
            const now = Date.now();
            const distance = targetTime - now;
            if (distance < 0) {
                setSubIsLive(true);
                return;
            }
            const days = Math.floor(distance / (1000 * 60 * 60 * 24));
            const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
            const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((distance % (1000 * 60)) / 1000);
            let text = "";
            if (days > 0) text += `${days}д `;
            text += `${hours}ч ${minutes}м ${seconds}с`;
            setTimerText(text);
        }

        update();
        const interval = setInterval(update, 1000);
        return () => clearInterval(interval);
    }, [next_session_iso]);

    return (
        <>
            <a href="next-race.html" className="btn hero-btn" id="hero-btn">
                <div
                className="hero-sub"
                id="hero-sub"
                >
                    <div className="session-badge">{subLabel}</div>
                </div>

                <div id="hero-title" className="hero-title">
                    {event_name}
                </div>
                {date && (
                    <div id="hero-date" className="hero-date">
                        {formatDateToText(date)}
                    </div>
                )}

                {subIsLive ? "СЕССИЯ ИДЕТ" : (
                <div id="hero-timer" className="hero-timer" style={{ display: "block" }}>
                    <span style={{ fontSize: "12px", opacity: 0.8, marginRight: "4px" }}>
                    До старта:
                    </span>
                    <span
                    id="timer-val"
                    style={{ fontFamily: "monospace", fontWeight: 700 }}
                    >
                    {timerText}
                    </span>
                </div>
                )}
            </a>
        </>
    )
}

export default Hero