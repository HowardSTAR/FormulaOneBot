import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { AUTH_CHANGED_EVENT, getWebsiteUser, hasTelegramAuth } from "../helpers/auth";

type IconName = "home" | "calendar" | "results" | "drivers" | "teams" | "compare" | "star" | "settings" | "account";

type NavItem = {
  to: string;
  label: string;
  icon: IconName;
  activePaths: string[];
};

const PRIMARY_NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Обзор", icon: "home", activePaths: ["/"] },
  { to: "/season", label: "Календарь", icon: "calendar", activePaths: ["/season", "/next-race", "/race-details"] },
  { to: "/race-results", label: "Результаты", icon: "results", activePaths: ["/race-results", "/quali-results", "/sprint-results", "/sprint-quali-results"] },
  { to: "/drivers", label: "Пилоты", icon: "drivers", activePaths: ["/drivers", "/driver-details"] },
  { to: "/constructors", label: "Команды", icon: "teams", activePaths: ["/constructors", "/constructor-details"] },
  { to: "/compare", label: "Сравнение", icon: "compare", activePaths: ["/compare"] },
  { to: "/account", label: "Аккаунт", icon: "account", activePaths: ["/account"] },
];

function NavIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    home: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5.5 9.5V21h13V9.5" /><path d="M9.5 21v-6h5v6" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    results: <><path d="M5 4h14v16H5z" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
    drivers: <><circle cx="12" cy="8" r="4" /><path d="M4.5 21a7.5 7.5 0 0 1 15 0" /></>,
    teams: <><circle cx="8" cy="8" r="3" /><circle cx="17" cy="9" r="2.5" /><path d="M2.5 20a5.5 5.5 0 0 1 11 0M13 20a4.5 4.5 0 0 1 8.5-2" /></>,
    compare: <><path d="M7 7h12l-3-3M17 17H5l3 3" /></>,
    star: <path d="m12 3 2.75 5.57 6.15.9-4.45 4.33 1.05 6.12L12 17.03l-5.5 2.89 1.05-6.12L3.1 9.47l6.15-.9L12 3Z" />,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.08A1.7 1.7 0 0 0 8.97 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15 1.7 1.7 0 0 0 3.08 14H3v-4h.08A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.88L4.2 7.06l2.83-2.83.06.06A1.7 1.7 0 0 0 8.97 4.6 1.7 1.7 0 0 0 10 3.08V3h4v.08A1.7 1.7 0 0 0 15.03 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9 1.7 1.7 0 0 0 20.92 10H21v4h-.08A1.7 1.7 0 0 0 19.4 15Z" /></>,
    account: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  };

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

export function AppHeader() {
  const telegramMiniApp = hasTelegramAuth();
  const [websiteLinked, setWebsiteLinked] = useState<boolean | null>(telegramMiniApp ? true : null);
  const { pathname } = useLocation();
  const isActive = (paths: string[]) => paths.includes(pathname);
  const refreshWebsiteAuth = useCallback(() => {
    if (telegramMiniApp) return;
    void getWebsiteUser().then((user) => setWebsiteLinked(Boolean(user?.telegram_id)));
  }, [telegramMiniApp]);

  useEffect(() => {
    refreshWebsiteAuth();
    window.addEventListener(AUTH_CHANGED_EVENT, refreshWebsiteAuth);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, refreshWebsiteAuth);
  }, [refreshWebsiteAuth]);

  const isAuthenticated = telegramMiniApp || websiteLinked;

  return (
    <header className="app-header">
      <div className="app-header-brand-wrap">
        <Link to="/" className="app-header-brand" aria-label="F1Hub — главная">
          <span className="app-header-brand-f1">F1</span><span>Hub</span>
        </Link>
        <span className="app-header-brand-caption">Race intelligence</span>
      </div>

      <nav className="app-header-nav" aria-label="Главное меню">
        <span className="app-header-nav-label">Навигация</span>
        {PRIMARY_NAV_ITEMS.map((item) => {
          const active = isActive(item.activePaths);
          return (
            <Link
              key={item.to}
              to={item.to}
              className={`app-header-link${active ? " active" : ""}`}
              aria-current={active ? "page" : undefined}
            >
              <span className="app-header-link-icon"><NavIcon name={item.icon} /></span>
              <span className="app-header-link-label">{item.label}</span>
              <span className="app-header-link-arrow" aria-hidden>›</span>
            </Link>
          );
        })}
      </nav>

      <div className="app-header-bottom">
        {isAuthenticated ? (
          <nav className="app-header-nav app-header-nav-secondary" aria-label="Пользовательское меню">
            <Link to="/favorites" className={`app-header-link${pathname === "/favorites" ? " active" : ""}`}>
              <span className="app-header-link-icon"><NavIcon name="star" /></span>
              <span className="app-header-link-label">Избранное</span>
            </Link>
            <Link to="/settings" className={`app-header-link${pathname === "/settings" ? " active" : ""}`}>
              <span className="app-header-link-icon"><NavIcon name="settings" /></span>
              <span className="app-header-link-label">Настройки</span>
            </Link>
          </nav>
        ) : websiteLinked === false ? (
          <div className="app-header-guest">
            <div><i aria-hidden />Гостевой режим</div>
            <p>Календарь, результаты и статистика доступны без входа.</p>
          </div>
        ) : null}

        <div className="app-header-status">
          <span><i aria-hidden />API online</span>
          <small>Данные Formula 1</small>
        </div>
      </div>
    </header>
  );
}
