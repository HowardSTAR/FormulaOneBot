import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/", label: "Главная", end: true },
  { to: "/season", label: "Календарь" },
  { to: "/drivers", label: "Пилоты" },
  { to: "/constructors", label: "Команды" },
  { to: "/compare", label: "Сравнение" },
];

export function AppHeader() {
  return (
    <header className="app-header">
      <NavLink to="/" end className="app-header-brand" aria-label="F1 Hub">
        <span className="app-header-brand-f1">F1</span> Hub
      </NavLink>
      <nav className="app-header-nav" aria-label="Главное меню">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `app-header-link${isActive ? " active" : ""}`}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
