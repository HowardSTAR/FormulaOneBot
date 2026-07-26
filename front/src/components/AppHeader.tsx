import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuthState } from "../helpers/auth";

type IconName = "home" | "calendar" | "results" | "drivers" | "teams" | "compare" | "predictions" | "wiki" | "contact" | "games" | "star" | "vote" | "settings" | "account" | "admin";

type NavItem = {
  to: string;
  label: string;
  icon: IconName;
  activePaths: string[];
};

type NavGroup = {
  id: string;
  label: string;
  icon: IconName;
  items: Array<Omit<NavItem, "icon">>;
};

const PRIMARY_NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Обзор", icon: "home", activePaths: ["/"] },
  { to: "/season", label: "Календарь", icon: "calendar", activePaths: ["/season", "/next-race", "/race-details"] },
  { to: "/wiki", label: "Wiki F1", icon: "wiki", activePaths: ["/wiki"] },
  { to: "/account", label: "Аккаунт", icon: "account", activePaths: ["/account"] },
  { to: "/contact-admin", label: "Обратная связь", icon: "contact", activePaths: ["/contact-admin"] },
];

const NAV_GROUPS: NavGroup[] = [
  {
    id: "results",
    label: "Результаты",
    icon: "results",
    items: [
      { to: "/practice-results", label: "Свободные заезды", activePaths: ["/practice-results"] },
      { to: "/sprint-quali-results", label: "Спринт-квала", activePaths: ["/sprint-quali-results"] },
      { to: "/sprint-results", label: "Спринт-гонка", activePaths: ["/sprint-results"] },
      { to: "/quali-results", label: "Квала", activePaths: ["/quali-results"] },
      { to: "/race-results", label: "Гонка", activePaths: ["/race-results"] },
    ],
  },
  {
    id: "peloton",
    label: "Пелотон",
    icon: "drivers",
    items: [
      { to: "/drivers", label: "Пилоты", activePaths: ["/drivers", "/driver-details"] },
      { to: "/constructors", label: "Команды", activePaths: ["/constructors", "/constructor-details", "/team-principal"] },
    ],
  },
  {
    id: "analytics",
    label: "Аналитика",
    icon: "compare",
    items: [
      { to: "/compare", label: "Сравнение", activePaths: ["/compare"] },
      { to: "/predictions", label: "Прогнозы", activePaths: ["/predictions"] },
    ],
  },
  {
    id: "games",
    label: "Игры",
    icon: "games",
    items: [
      { to: "/reaction-game", label: "Тест реакции", activePaths: ["/reaction-game"] },
    ],
  },
];

function NavIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    home: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5.5 9.5V21h13V9.5" /><path d="M9.5 21v-6h5v6" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    results: <><path d="M5 4h14v16H5z" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
    drivers: <><circle cx="12" cy="8" r="4" /><path d="M4.5 21a7.5 7.5 0 0 1 15 0" /></>,
    teams: <><circle cx="8" cy="8" r="3" /><circle cx="17" cy="9" r="2.5" /><path d="M2.5 20a5.5 5.5 0 0 1 11 0M13 20a4.5 4.5 0 0 1 8.5-2" /></>,
    compare: <><path d="M7 7h12l-3-3M17 17H5l3 3" /></>,
    predictions: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /><path d="m4 7 6-4 6 7 5-5" /></>,
    wiki: <><path d="M4 4.5A3.5 3.5 0 0 1 7.5 1H12v19H7.5A3.5 3.5 0 0 0 4 23.5z" /><path d="M20 4.5A3.5 3.5 0 0 0 16.5 1H12v19h4.5a3.5 3.5 0 0 1 3.5 3.5z" /></>,
    contact: <><path d="M4 4h16v13H8l-4 4z" /><path d="M8 9h8M8 13h5" /></>,
    games: <><path d="M8 8h8a5 5 0 0 1 4.72 3.35l1.1 3.15A4.15 4.15 0 0 1 15 18.72L13.8 17h-3.6L9 18.72a4.15 4.15 0 0 1-6.82-4.22l1.1-3.15A5 5 0 0 1 8 8Z" /><path d="M7 11v4M5 13h4M16.5 12.5h.01M18.5 14.5h.01" /></>,
    star: <path d="m12 3 2.75 5.57 6.15.9-4.45 4.33 1.05 6.12L12 17.03l-5.5 2.89 1.05-6.12L3.1 9.47l6.15-.9L12 3Z" />,
    vote: <><path d="M7 3h10v4H7z" /><path d="M5 7h14l2 4v10H3V11z" /><path d="m9 14 2 2 4-5" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.08A1.7 1.7 0 0 0 8.97 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15 1.7 1.7 0 0 0 3.08 14H3v-4h.08A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.88L4.2 7.06l2.83-2.83.06.06A1.7 1.7 0 0 0 8.97 4.6 1.7 1.7 0 0 0 10 3.08V3h4v.08A1.7 1.7 0 0 0 15.03 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9 1.7 1.7 0 0 0 20.92 10H21v4h-.08A1.7 1.7 0 0 0 19.4 15Z" /></>,
    account: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
    admin: <><path d="M12 3 4.5 6v5.5c0 4.6 3.2 7.9 7.5 9.5 4.3-1.6 7.5-4.9 7.5-9.5V6z" /><path d="M9 12.5 11 14.5 15.5 10" /></>,
  };

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

function SidebarAccordion({ group, pathname }: { group: NavGroup; pathname: string }) {
  const active = group.items.some((item) => item.activePaths.includes(pathname));
  const [open, setOpen] = useState(active);

  const expanded = open || active;
  const submenuId = `app-header-${group.id}-menu`;

  return (
    <div className={`app-header-menu${expanded ? " is-open" : ""}${active ? " active" : ""}`}>
      <button
        type="button"
        className={`app-header-link app-header-menu-trigger${active ? " active" : ""}`}
        aria-expanded={expanded}
        aria-controls={submenuId}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="app-header-link-icon"><NavIcon name={group.icon} /></span>
        <span className="app-header-link-label">{group.label}</span>
        <span className="app-header-link-arrow" aria-hidden>›</span>
      </button>
      <div id={submenuId} className="app-header-submenu" aria-hidden={!expanded}>
        {group.items.map((item) => {
          const itemActive = item.activePaths.includes(pathname);
          return (
            <Link
              key={item.to}
              to={item.to}
              className={`app-header-submenu-link${itemActive ? " active" : ""}`}
              aria-current={itemActive ? "page" : undefined}
              tabIndex={expanded ? 0 : -1}
            >
              <span aria-hidden />
              {item.label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export function AppHeader() {
  const auth = useAuthState();
  const { pathname } = useLocation();
  const isActive = (paths: string[]) => paths.includes(pathname);

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
        {PRIMARY_NAV_ITEMS.slice(0, 2).map((item) => {
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
        {NAV_GROUPS.slice(0, 3).map((group) => (
          <SidebarAccordion key={group.id} group={group} pathname={pathname} />
        ))}
        {PRIMARY_NAV_ITEMS.slice(2).map((item) => {
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
        <SidebarAccordion group={NAV_GROUPS[3]} pathname={pathname} />
      </nav>

      <div className="app-header-bottom">
        {(auth.role === "admin" || auth.role === "superadmin") && (
          <nav className="app-header-nav app-header-nav-secondary" aria-label="Администрирование">
            <Link to="/admin" className={`app-header-link${pathname === "/admin" ? " active" : ""}`}>
              <span className="app-header-link-icon"><NavIcon name="admin" /></span>
              <span className="app-header-link-label">Админ-панель</span>
            </Link>
          </nav>
        )}
        {auth.personalized ? (
          <nav className="app-header-nav app-header-nav-secondary" aria-label="Пользовательское меню">
            <Link to="/voting" className={`app-header-link${pathname === "/voting" ? " active" : ""}`}>
              <span className="app-header-link-icon"><NavIcon name="vote" /></span>
              <span className="app-header-link-label">Голосование</span>
            </Link>
            <Link to="/favorites" className={`app-header-link${pathname === "/favorites" ? " active" : ""}`}>
              <span className="app-header-link-icon"><NavIcon name="star" /></span>
              <span className="app-header-link-label">Избранное</span>
            </Link>
            <Link to="/settings" className={`app-header-link${pathname === "/settings" ? " active" : ""}`}>
              <span className="app-header-link-icon"><NavIcon name="settings" /></span>
              <span className="app-header-link-label">Настройки</span>
            </Link>
          </nav>
        ) : auth.loaded && !auth.signedIn ? (
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
