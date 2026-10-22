import { Suspense, useRef, useCallback, useEffect } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { hapticImpact } from "../helpers/telegram";
import { AppHeader } from "./AppHeader";
import { LegalFooter } from "./LegalFooter";
import { InstallHint } from "./InstallHint";
import { MobileNav } from "./MobileNav";
import { trackScreen } from '../helpers/analytics';
import { EngagementEntry } from './EngagementEntry';
import { NotificationEntry } from './NotificationEntry';
import { RouteContext } from './RouteContext';
import { DataReceipt } from './DataReceipt';
import { FirstVisitGuide } from './FirstVisitGuide';
import { PageMotion } from './PageMotion';
import { VisitReminder } from './VisitReminder';
import { AccountShortcut } from './AccountShortcut';
import { ThemeToggle } from './ThemeToggle';
import { HomeToolbar } from './HomeToolbar';
import '../assets/home-glass.css';

const EDGE_THRESHOLD = 30;
const SWIPE_THRESHOLD = 60;

export function SwipeBackLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const startX = useRef(0);
  const startY = useRef(0);
  const tracking = useRef(false);
  const previousPathRef = useRef<string | null>(null);
  useEffect(() => {
    // Only the route is sent: no query parameters, search text or personal data.
    const timer = window.setTimeout(() => {
      trackScreen(location.pathname);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [location.pathname]);

  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      const touch = e.touches[0];
      if (!touch) return;
      if (touch.clientX <= EDGE_THRESHOLD) {
        tracking.current = true;
        startX.current = touch.clientX;
        startY.current = touch.clientY;
      }
    },
    []
  );

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!tracking.current) return;
    const touch = e.touches[0];
    if (!touch) return;
    const deltaX = touch.clientX - startX.current;
    const deltaY = Math.abs(touch.clientY - startY.current);
    if (deltaX < 0 || deltaY > deltaX * 1.5) {
      tracking.current = false;
    }
  }, []);

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (!tracking.current) return;
      const touch = e.changedTouches[0];
      if (!touch) {
        tracking.current = false;
        return;
      }
      const deltaX = touch.clientX - startX.current;
      tracking.current = false;
      if (deltaX >= SWIPE_THRESHOLD && location.pathname !== "/") {
        hapticImpact("light");
        if (Number(window.history.state?.idx) > 0) navigate(-1); else navigate('/');
      }
    },
    [navigate, location.pathname]
  );

  const routeKey =
    location.pathname === "/"
      ? "home"
      : location.pathname
          .replace(/^\/+/, "")
          .replace(/\/+/g, "-")
          .replace(/[^a-z0-9-_]/gi, "")
          .toLowerCase() || "page";

  return (
    <div onTouchStart={handleTouchStart} onTouchMove={handleTouchMove} onTouchEnd={handleTouchEnd} className={`app-shell design-shell${routeKey === 'home' ? ' glass-home' : ''}`}>
      <EngagementEntry />
      <NotificationEntry />
      <RouteContext />
      <a className="design-skip" href="#page-content">Перейти к содержимому</a>
      <AppHeader />
      <InstallHint />
      <FirstVisitGuide />
      <div className="app-content">
        {routeKey === 'home' ? <HomeToolbar /> : <div className="account-shortcut-bar"><ThemeToggle /><AccountShortcut /></div>}
        <section className={`app-page-main route-${routeKey}`} id="page-content" tabIndex={-1}>
          <VisitReminder />
          <Suspense fallback={<div className="route-loading" role="status">Загрузка раздела…</div>}>
            <PageMotion key={location.pathname} pathname={location.pathname} previousPathRef={previousPathRef} />
            <Outlet />
          </Suspense>
          <DataReceipt />
        </section>
        <LegalFooter />
      </div>
      <MobileNav />
    </div>
  );
}
