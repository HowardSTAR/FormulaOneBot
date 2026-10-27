import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./styles.css";
import { trackScreen, trackAction } from '../../helpers/analytics';
import { ShareComposer } from '../../components/ShareButton';
import { pendingInvitation, rememberInvitation, sharingEvent, validShareToken, type ShareOptions } from '../../helpers/sharing';
import { useAuthState } from '../../helpers/auth';
import { ThemeToggle } from "../../components/ThemeToggle";
import { homeSectionPath } from '../../helpers/homeSections';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { suspendTelegramVerticalSwipes } from '../../helpers/telegram';

function isPhoneDevice() {
  const userAgent = navigator.userAgent || "";
  const userAgentData = (navigator as Navigator & { userAgentData?: { mobile?: boolean } }).userAgentData;
  const mobileUserAgent = /Android.+Mobile|iPhone|iPod|IEMobile|Windows Phone|Opera Mini/i.test(userAgent);
  const compactTouchScreen = window.matchMedia("(pointer: coarse)").matches
    && Math.min(window.screen.width, window.screen.height) <= 520;
  return Boolean(userAgentData?.mobile) || mobileUserAgent || compactTouchScreen;
}

function RaceGamePage() {
  useEffect(() => suspendTelegramVerticalSwipes(), []);
  useEffect(() => { document.title = 'Emerald Loop · F1Hub — проект TurboTears'; }, []);
  const location = useLocation();
  const navigate = useNavigate();
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
      if (event.origin === window.location.origin && event.source === frame.current?.contentWindow && event.data?.type === 'f1hub-exit-race') {
        if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
        navigate(homeSectionPath('games'));
        return;
      }
      if (event.origin === window.location.origin && event.source === frame.current?.contentWindow && event.data?.type === 'f1hub-trophy-check') {
        window.dispatchEvent(new Event('turbotears:trophy-check'));
        return;
      }
      if (event.origin === window.location.origin && event.source === frame.current?.contentWindow && event.data?.type === 'f1hub-game-analytics') {
        if (['game_start', 'game_restart', 'button'].includes(event.data.action)) trackAction(event.data.action, '/race-game');
        return;
      }
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow || event.data?.type !== 'f1hub-share-race') return;
      if (typeof event.data.trackId === 'string' && /^[a-z0-9-]{1,60}$/.test(event.data.trackId)) setShare({kind: 'race', track_id: event.data.trackId});
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [navigate]);
  useEffect(() => {
    const timer = window.setTimeout(() => trackScreen('/race-game'),500);
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
          aria-labelledby="race-game-orientation-title"
        >
          <div className="race-game-orientation-card">
            <div className="race-game-orientation-icon" aria-hidden="true">
              <span className="race-game-orientation-phone" />
              <svg className="race-game-orientation-arrow" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M20 10a8 8 0 1 0-2 8M20 4v6h-6" /></svg>
            </div>
            <div className="race-game-orientation-tools"><Link to="/">На главную</Link><ThemeToggle /></div>
            <h1 id="race-game-orientation-title">Emerald Loop</h1>
            <h2>Поверните устройство</h2>
            <p>
              Для лучшего игрового опыта поверните устройство горизонтально
            </p>
            <button type="button" data-analytics-action="game_start" onClick={() => setGameStarted(true)}>
              Играть сейчас
            </button>
          </div>
        </section>
      ) : (
        <iframe
          ref={frame}
          className="race-game-frame"
          src={`/race-game/index.html${gameParams.size ? '?' + gameParams.toString() : ''}`}
          title="Заезд на трассе"
          allow="fullscreen"
        />
      )}
      {share && <ShareComposer options={share} onClose={() => setShare(null)} />}
    </main>,
    document.body,
  );
}

export default RaceGamePage;
