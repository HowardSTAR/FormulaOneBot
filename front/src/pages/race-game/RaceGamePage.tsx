import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./styles.css";
import { apiRequest } from '../../helpers/api';
import { analyticsPlatform } from '../../helpers/analytics';
import { ShareComposer } from '../../components/ShareButton';
import { pendingInvitation, rememberInvitation, sharingEvent, validShareToken, type ShareOptions } from '../../helpers/sharing';
import { useAuthState } from '../../helpers/auth';
import { useLocation } from 'react-router-dom';

function isPhoneDevice() {
  const userAgent = navigator.userAgent || "";
  const userAgentData = (navigator as Navigator & { userAgentData?: { mobile?: boolean } }).userAgentData;
  const mobileUserAgent = /Android.+Mobile|iPhone|iPod|IEMobile|Windows Phone|Opera Mini/i.test(userAgent);
  const compactTouchScreen = window.matchMedia("(pointer: coarse)").matches
    && Math.min(window.screen.width, window.screen.height) <= 520;
  return Boolean(userAgentData?.mobile) || mobileUserAgent || compactTouchScreen;
}

function RaceGamePage() {
  useEffect(() => { document.title = 'Emerald Loop · F1Hub — проект TurboTears'; }, []);
  const location = useLocation();
  const auth = useAuthState();
  const frame = useRef<HTMLIFrameElement>(null);
  const [share, setShare] = useState<ShareOptions | null>(null);
  const search = new URLSearchParams(location.search);
  const challenge = search.get('challenge') || '';
  const track = search.get('track') || '';
  const gameParams = new URLSearchParams();
  if (validShareToken(challenge)) gameParams.set('challenge', challenge);
  if (/^[a-z0-9-]{1,60}$/.test(track)) gameParams.set('track', track);
  if (search.get('weekly') === '1') gameParams.set('weekly', '1');
  useEffect(() => {
    if (validShareToken(challenge)) rememberInvitation(challenge);
    const token = pendingInvitation();
    if (auth.signedIn && token) void sharingEvent(token, 'arrival');
  }, [challenge, auth.signedIn]);
  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow || event.data?.type !== 'f1hub-share-race') return;
      if (typeof event.data.trackId === 'string' && /^[a-z0-9-]{1,60}$/.test(event.data.trackId)) setShare({kind: 'race', track_id: event.data.trackId});
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => { void apiRequest('/api/analytics/visit',{path:'/race-game',platform:analyticsPlatform()},'POST').catch(() => {}); },500);
    return () => window.clearTimeout(timer);
  }, []);
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
          ref={frame}
          className="race-game-frame"
          src={`/race-game/index.html${gameParams.size ? '?' + gameParams.toString() : ''}`}
          title="Emerald Loop — пиксельная гонка"
          allow="fullscreen"
        />
      )}
      {share && <ShareComposer options={share} onClose={() => setShare(null)} />}
    </main>,
    document.body,
  );
}

export default RaceGamePage;
