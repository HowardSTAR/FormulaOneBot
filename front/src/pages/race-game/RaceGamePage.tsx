import { useEffect } from "react";
import "./styles.css";

function RaceGamePage() {
  useEffect(() => {
    const previousBodyOverflow = document.body.style.overflow;
    const previousHtmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousHtmlOverflow;
    };
  }, []);

  return (
    <main className="race-game-host">
      <iframe
        className="race-game-frame"
        src="/race-game/index.html"
        title="Emerald Loop — пиксельная гонка"
        allow="fullscreen"
      />
    </main>
  );
}

export default RaceGamePage;
