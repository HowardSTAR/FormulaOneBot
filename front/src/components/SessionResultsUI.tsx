import type { ReactNode } from "react";
import "./session-results-ui.css";

type FeedbackProps = {
  loading?: boolean;
  error?: string | null;
  empty?: boolean;
  icon?: string;
  title?: string;
  description?: string;
};

export function ResultsFeedback({
  loading = false,
  error,
  empty = false,
  icon = "🏁",
  title = "Нет данных",
  description = "Результаты пока недоступны.",
}: FeedbackProps) {
  if (loading) {
    return (
      <div className="results-skeleton" role="status" aria-label="Загружаем результаты">
        {Array.from({ length: 6 }, (_, index) => (
          <div className="results-skeleton-row" key={index}>
            <span /><span /><span /><span />
          </div>
        ))}
      </div>
    );
  }
  if (error) return <div className="page-error results-feedback-error" role="alert">{error}</div>;
  if (!empty) return null;
  return (
    <div className="empty-state results-empty-state" role="status">
      <span className="empty-icon" aria-hidden>{icon}</span>
      <div className="empty-title">{title}</div>
      <div className="empty-desc">{description}</div>
    </div>
  );
}

type MobileRowProps = {
  position: number;
  name: string;
  code?: string;
  team?: string;
  value?: ReactNode;
  badge?: ReactNode;
  favorite?: boolean;
};

export function ResultsMobileRow({
  position,
  name,
  code,
  team,
  value,
  badge,
  favorite = false,
}: MobileRowProps) {
  const positionLabel = position === 1 ? "🥇" : position === 2 ? "🥈" : position === 3 ? "🥉" : position;
  return (
    <div className={`standings-item results-mobile-row${position === 1 ? " winner" : ""}`}>
      <div className={`standings-position ${position <= 3 ? "podium" : ""}`}>{positionLabel}</div>
      <div className="standings-info">
        <div className="standings-name">{favorite ? "★ " : ""}{name}</div>
        <div className="standings-code">
          {code || team || "—"}
          {code && team ? <span className="results-mobile-team">{team}</span> : null}
          {badge}
        </div>
      </div>
      {value !== undefined ? <div className="standings-time results-mobile-value">{value}</div> : null}
    </div>
  );
}

export function SessionBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: "green" | "blue" | "neutral" }) {
  return <span className={`session-result-badge is-${tone}`}>{children}</span>;
}

type TableRow = {
  key: string;
  values: ReactNode[];
  winner?: boolean;
};

export function ResultsDesktopTable({ columns, rows, className = "" }: { columns: string[]; rows: TableRow[]; className?: string }) {
  return (
    <div className={`race-results-desktop-table unified-results-table ${className}`.trim()}>
      <div className="race-results-desktop-table-head">
        {columns.map((column) => <span key={column}>{column}</span>)}
      </div>
      {rows.map((row) => (
        <div className={`race-results-desktop-row${row.winner ? " winner" : ""}`} key={row.key}>
          {row.values.map((value, index) => <span key={index}>{value}</span>)}
        </div>
      ))}
    </div>
  );
}
