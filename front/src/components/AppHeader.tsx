import { NavLink } from "react-router-dom";
import { hasTelegramAuth } from "../helpers/auth";

const PRIMARY_NAV_ITEMS = [
  { to: "/", label: "Главная", icon: "⌁", end: true },
  { to: "/season", label: "Календарь", icon: "◷" },
  { to: "/drivers", label: "Пилоты", icon: "◉" },
  { to: "/constructors", label: "Команды", icon: "▣" },
  { to: "/compare", label: "Сравнение", icon: "⇄" },
];

export function AppHeader() {
  const isAuthenticated = hasTelegramAuth();

  return (
    <header className="app-header">
      <NavLink to="/" end className="app-header-brand" aria-label="F1Hub">
        <span className="app-header-brand-f1">F1</span>Hub
      </NavLink>
      <nav className="app-header-nav" aria-label="Главное меню">
        {PRIMARY_NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `app-header-link${isActive ? " active" : ""}`}
          >
            <span className="app-header-link-icon" aria-hidden>
              {item.icon}
            </span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      {isAuthenticated && (
        <nav className="app-header-nav app-header-nav-secondary" aria-label="Пользовательское меню">
          <NavLink to="/favorites" className={({ isActive }) => `app-header-link${isActive ? " active" : ""}`}>
            <span className="app-header-link-icon" aria-hidden>★</span>
            <span>Избранное</span>
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `app-header-link${isActive ? " active" : ""}`}>
            <span className="app-header-link-icon" aria-hidden>⚙</span>
            <span>Настройки</span>
          </NavLink>
        </nav>
      )}
    </header>
  );
}
