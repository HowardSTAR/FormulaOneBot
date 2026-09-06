import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./styles.css";

function isPhoneDevice() {
  const userAgent = navigator.userAgent || "";
  const userAgentData = (navigator as Navigator & { userAgentData?: { mobile?: boolean } }).userAgentData;
  const mobileUserAgent = /Android.+Mobile|iPhone|iPod|IEMobile|Windows Phone|Opera Mini/i.test(userAgent);
  const compactTouchScreen = window.matchMedia("(pointer: coarse)").matches
    && Math.min(window.screen.width, window.screen.height) <= 520;
  return Boolean(userAgentData?.mobile) || mobileUserAgent || compactTouchScreen;
}

function RaceGamePage() {
  const hostRef = useRef<HTMLElement>(null);
  const [gameStarted, setGameStarted] = useState(() =>
    !isPhoneDevice() || window.innerWidth > window.innerHeight,
  );

  useEffect(() => {
    const previousBodyOverflow = document.body.style.overflow;
    const previousHtmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    const updateViewport = () => {
      const viewport = window.visualViewport;
      const width = viewport?.width ?? window.innerWidth;
      const height = viewport?.height ?? window.innerHeight;
      if (hostRef.current) {
        hostRef.current.style.width = `${Math.round(width)}px`;
        hostRef.current.style.height = `${Math.round(height)}px`;
      }
      // Keep the same iframe alive on subsequent rotations.
      if (width > height) setGameStarted(true);
    };
    updateViewport();
    window.addEventListener("resize", updateViewport);
    window.addEventListener("orientationchange", updateViewport);
    window.visualViewport?.addEventListener("resize", updateViewport);
    return () => {
      window.removeEventListener("resize", updateViewport);
      window.removeEventListener("orientationchange", updateViewport);
      window.visualViewport?.removeEventListener("resize", updateViewport);
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousHtmlOverflow;
    };
  }, []);

  return createPortal(
    <main className="race-game-host" ref={hostRef}>
      {!gameStarted ? (
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
            <button type="button" onClick={() => setGameStarted(true)} autoFocus>
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
    </main>,
    document.body,
  );
}

export default RaceGamePage;
