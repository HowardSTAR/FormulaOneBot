import { type ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../helpers/api";

export function RequireAdmin({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<"loading" | "allowed" | "denied">("loading");

  useEffect(() => {
    let active = true;
    void apiRequest<{ role: "admin" | "superadmin" }>("/api/admin/me")
      .then(() => { if (active) setStatus("allowed"); })
      .catch(() => { if (active) setStatus("denied"); });
    return () => { active = false; };
  }, []);

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
