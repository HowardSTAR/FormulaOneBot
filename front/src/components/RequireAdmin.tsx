import { type ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest, ApiError } from "../helpers/api";
import { PageFeedback } from './PageFeedback';

export function RequireAdmin({ children }: { children: ReactNode }) {
  const [result, setResult] = useState<{ attempt: number; status: "allowed" | "denied" | "error" } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const status = result?.attempt === attempt ? result.status : "loading";

  useEffect(() => {
    let active = true;
    void apiRequest<{ role: "admin" | "superadmin" }>("/api/admin/me")
      .then(() => { if (active) setResult({ attempt, status: "allowed" }); })
      .catch(error => { if (active) setResult({ attempt, status: error instanceof ApiError && [401,403].includes(error.status) ? "denied" : "error" }); });
    return () => { active = false; };
  }, [attempt]);

  if (status === "error") return <PageFeedback retry={() => setAttempt(v => v + 1)} />;

  if (status === "loading") {
    return <div className="admin-route-state" role="status">Проверяем права доступа…</div>;
  }
  if (status === "denied") {
    return (
      <div className="admin-route-state admin-route-denied">
        <span>403</span>
        <h1>Доступ запрещён</h1>
        <p>Административная панель доступна только администраторам.</p>
        <Link className="ui-action-link" to="/account">Перейти в аккаунт</Link>
      </div>
    );
  }
  return children;
}
