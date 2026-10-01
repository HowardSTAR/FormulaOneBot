import { type ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest, ApiError } from "../helpers/api";
import { PageFeedback } from './PageFeedback';

export function RequireAdmin({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<"loading" | "allowed" | "denied" | "error">("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setStatus("loading");
    void apiRequest<{ role: "admin" | "superadmin" }>("/api/admin/me")
      .then(() => { if (active) setStatus("allowed"); })
      .catch(error => { if (active) setStatus(error instanceof ApiError && [401,403].includes(error.status) ? "denied" : "error"); });
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
        <Link to="/account">Перейти в аккаунт</Link>
      </div>
    );
  }
  return children;
}
