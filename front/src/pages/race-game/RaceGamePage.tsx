import { useEffect, useState } from "react";
import "./styles.css";

function RaceGamePage() {
  const [orientationPromptDismissed, setOrientationPromptDismissed] = useState(false);

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
      {!orientationPromptDismissed ? (
        <section
          className="race-game-orientation-prompt"
          role="dialog"
          aria-modal="true"
          aria-labelledby="race-game-orientation-title"
        >
          <div className="race-game-orientation-card">
            <div className="race-game-orientation-icon" aria-hidden="true">
              <span className="race-game-orientation-phone" />
              <span className="race-game-orientation-arrow">↻</span>
            </div>
            <p className="race-game-orientation-kicker">EMERALD LOOP</p>
            <h1 id="race-game-orientation-title">Поверните устройство</h1>
            <p>
              Для лучшего игрового опыта поверните устройство горизонтально
              <span>Rotate to landscape for best experience</span>
            </p>
            <button type="button" onClick={() => setOrientationPromptDismissed(true)} autoFocus>
              Continue / Играть
            </button>
          </div>
        </section>
      ) : (
        <iframe
          className="race-game-frame"
          src="/race-game/index.html"
          title="Emerald Loop — пиксельная гонка"
          allow="fullscreen"
        />
      )}
    </main>
  );
}

export default RaceGamePage;
