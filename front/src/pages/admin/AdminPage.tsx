import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
  type ChartConfiguration,
} from "chart.js";
import { apiRequest } from "../../helpers/api";
import "./admin.css";

Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
);

type Role = "user" | "admin" | "superadmin";
type Source = "all" | "site" | "bot";
type Period = "7d" | "30d" | "90d" | "all";
type AdminIdentity = { id: number; role: "admin" | "superadmin"; email: string | null; telegram_id: number | null };
type MetricCard = { dau: number; wau: number; mau: number };
type MetricPoint = { day: string; site: number; bot: number };
type Metrics = {
  cards: Record<Source, MetricCard>;
  series: MetricPoint[];
  generated_at: string;
};
type ManagedUser = {
  id: number;
  email: string | null;
  telegram_id: number | null;
  telegram_username: string | null;
  display_name: string | null;
  created_at: string;
  last_activity: string | null;
  role: Role;
  email_verified: boolean;
  protected: boolean;
};
type UserPage = { items: ManagedUser[]; page: number; pages: number; total: number; page_size: number };
type AuditItem = {
  id: number;
  action: string;
  created_at: string;
  target_user_id: number | null;
  actor_email: string | null;
  actor_telegram_id: number | null;
  details: Record<string, unknown>;
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function AdminChart({ metrics, source }: { metrics: Metrics; source: Source }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    const datasets = [
      ...(source !== "bot" ? [{
        label: "Сайт",
        data: metrics.series.map((point) => point.site),
        borderColor: "#ff4038",
        backgroundColor: "rgba(255,64,56,.35)",
      }] : []),
      ...(source !== "site" ? [{
        label: "Telegram-бот",
        data: metrics.series.map((point) => point.bot),
        borderColor: "#46a6ff",
        backgroundColor: "rgba(70,166,255,.35)",
      }] : []),
    ];
    const config: ChartConfiguration<"line", number[], string> = {
      type: "line",
      data: {
        labels: metrics.series.map((point) => point.day.slice(5)),
        datasets: datasets.map((dataset) => ({
          ...dataset,
          tension: 0.28,
          pointRadius: metrics.series.length > 35 ? 0 : 3,
          pointHoverRadius: 5,
          borderWidth: 2,
          fill: true,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { labels: { color: "#c7c8cf", usePointStyle: true } },
        },
        scales: {
          x: { ticks: { color: "#777a84", maxTicksLimit: 12 }, grid: { color: "rgba(255,255,255,.05)" } },
          y: { beginAtZero: true, ticks: { color: "#777a84", precision: 0 }, grid: { color: "rgba(255,255,255,.07)" } },
        },
      },
    };
    const chart = new Chart(canvasRef.current, config);
    return () => chart.destroy();
  }, [metrics, source]);

  return <canvas ref={canvasRef} aria-label="Динамика активных пользователей" />;
}

export default function AdminPage() {
  const [tab, setTab] = useState<"overview" | "users" | "audit">("overview");
  const [identity, setIdentity] = useState<AdminIdentity | null>(null);
  const [period, setPeriod] = useState<Period>("30d");
  const [source, setSource] = useState<Source>("all");
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [userPage, setUserPage] = useState<UserPage | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | Role>("all");
  const [page, setPage] = useState(1);
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);
  const [emailDraft, setEmailDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadIdentity = useCallback(async () => {
    setIdentity(await apiRequest<AdminIdentity>("/api/admin/me"));
  }, []);

  const loadMetrics = useCallback(async () => {
    setMetrics(await apiRequest<Metrics>("/api/admin/metrics", { period, source }));
  }, [period, source]);

  const loadUsers = useCallback(async () => {
    setUserPage(await apiRequest<UserPage>("/api/admin/users", {
      search,
      role: roleFilter,
      page,
      page_size: 25,
    }));
  }, [page, roleFilter, search]);

  const loadAudit = useCallback(async () => {
    const result = await apiRequest<{ items: AuditItem[] }>("/api/admin/audit-log", { limit: 100 });
    setAudit(result.items);
  }, []);

  useEffect(() => { void loadIdentity().catch((reason: Error) => setError(reason.message)); }, [loadIdentity]);
  useEffect(() => { if (tab === "overview") void loadMetrics().catch((reason: Error) => setError(reason.message)); }, [loadMetrics, tab]);
  useEffect(() => { if (tab === "users") void loadUsers().catch((reason: Error) => setError(reason.message)); }, [loadUsers, tab]);
  useEffect(() => { if (tab === "audit") void loadAudit().catch((reason: Error) => setError(reason.message)); }, [loadAudit, tab]);

  const selectedCards = metrics?.cards[source] ?? metrics?.cards.all;
  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError("");
    try {
      await action();
      setMessage(success);
      await Promise.all([loadUsers(), loadAudit()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось выполнить действие");
    } finally {
      setBusy(false);
    }
  };

  const changeRole = (user: ManagedUser, role: "user" | "admin") => {
    if (!window.confirm(`Изменить роль пользователя #${user.id} на ${role}?`)) return;
    void runAction(
      () => apiRequest(`/api/admin/users/${user.id}/role`, { role }, "PATCH"),
      "Роль пользователя обновлена",
    );
  };

  const unlinkTelegram = (user: ManagedUser) => {
    if (!window.confirm(`Отвязать Telegram у пользователя #${user.id}?`)) return;
    void runAction(
      () => apiRequest(`/api/admin/users/${user.id}/unlink-telegram`, {}, "POST"),
      "Telegram отвязан",
    );
  };

  const sendReset = (user: ManagedUser) => {
    if (!window.confirm(`Отправить ссылку восстановления на ${user.email}?`)) return;
    void runAction(
      () => apiRequest(`/api/admin/users/${user.id}/password-reset`, {}, "POST"),
      "Письмо для сброса пароля отправлено",
    );
  };

  const submitEmail = () => {
    if (!editingUser) return;
    void runAction(
      () => apiRequest(`/api/admin/users/${editingUser.id}/email`, { email: emailDraft }, "PATCH"),
      "Email пользователя обновлён",
    ).finally(() => setEditingUser(null));
  };

  const identityLabel = useMemo(
    () => identity?.email || (identity?.telegram_id ? `TG ${identity.telegram_id}` : "Администратор"),
    [identity],
  );

  return (
    <div className="admin-page">
      <header className="admin-hero">
        <div>
          <span className="admin-eyebrow">F1Hub Control Center</span>
          <h1>Администрирование</h1>
          <p>Активность, пользователи, роли и журнал критических действий.</p>
        </div>
        <div className="admin-identity">
          <span>{identity?.role ?? "…"}</span>
          <strong>{identityLabel}</strong>
        </div>
      </header>

      <nav className="admin-tabs" aria-label="Разделы администрирования">
        <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>Аналитика</button>
        <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>Пользователи</button>
        <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>Audit log</button>
      </nav>

      {(message || error) && (
        <div className={`admin-notice ${error ? "error" : "success"}`} role="status">
          {error || message}
          <button onClick={() => { setError(""); setMessage(""); }} aria-label="Закрыть">×</button>
        </div>
      )}

      {tab === "overview" && (
        <>
          <section className="admin-toolbar">
            <div>
              {(["7d", "30d", "90d", "all"] as Period[]).map((value) => (
                <button key={value} className={period === value ? "active" : ""} onClick={() => setPeriod(value)}>
                  {value === "all" ? "Всё время" : value.replace("d", " дней")}
                </button>
              ))}
            </div>
            <select value={source} onChange={(event) => setSource(event.target.value as Source)} aria-label="Источник активности">
              <option value="all">Все источники</option>
              <option value="site">Только сайт</option>
              <option value="bot">Только бот</option>
            </select>
          </section>
          <section className="admin-metric-grid">
            {(["dau", "wau", "mau"] as const).map((metric) => (
              <article key={metric}>
                <span>{metric.toUpperCase()}</span>
                <strong>{selectedCards?.[metric] ?? "—"}</strong>
                <small>{metric === "dau" ? "24 часа" : metric === "wau" ? "7 дней" : "30 дней"}</small>
              </article>
            ))}
          </section>
          <section className="admin-source-grid">
            {(["site", "bot", "all"] as Source[]).map((value) => (
              <article key={value}>
                <span>{value === "site" ? "Сайт" : value === "bot" ? "Telegram-бот" : "Суммарно"}</span>
                <div><b>{metrics?.cards[value].dau ?? 0}</b> DAU</div>
                <div><b>{metrics?.cards[value].wau ?? 0}</b> WAU</div>
                <div><b>{metrics?.cards[value].mau ?? 0}</b> MAU</div>
              </article>
            ))}
          </section>
          <section className="admin-chart-card">
            <header><h2>Динамика уникальных пользователей</h2><span>по дням</span></header>
            <div className="admin-chart-wrap">
              {metrics ? <AdminChart metrics={metrics} source={source} /> : <div className="admin-skeleton" />}
            </div>
          </section>
        </>
      )}

      {tab === "users" && (
        <section className="admin-users-card">
          <header className="admin-users-tools">
            <form onSubmit={(event) => { event.preventDefault(); setPage(1); setSearch(searchInput.trim()); }}>
              <input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Email, Telegram ID, имя…"
                aria-label="Поиск пользователей"
              />
              <button type="submit">Найти</button>
            </form>
            <select value={roleFilter} onChange={(event) => { setPage(1); setRoleFilter(event.target.value as typeof roleFilter); }}>
              <option value="all">Все роли</option>
              <option value="user">User</option>
              <option value="admin">Admin</option>
              <option value="superadmin">Superadmin</option>
            </select>
            <span>Найдено: {userPage?.total ?? 0}</span>
          </header>
          <div className="admin-table-wrap">
            <table>
              <thead><tr><th>ID</th><th>Пользователь</th><th>Telegram</th><th>Регистрация</th><th>Активность</th><th>Роль</th><th>Действия</th></tr></thead>
              <tbody>
                {userPage?.items.map((user) => (
                  <tr key={user.id}>
                    <td data-label="ID">#{user.id}</td>
                    <td data-label="Пользователь">
                      <strong>{user.display_name || user.email || "Без имени"}</strong>
                      <small>{user.email || "Email не указан"}</small>
                    </td>
                    <td data-label="Telegram">
                      {user.telegram_id ? <><strong>{user.telegram_id}</strong><small>{user.telegram_username ? `@${user.telegram_username}` : "username не указан"}</small></> : "—"}
                    </td>
                    <td data-label="Регистрация">{formatDate(user.created_at)}</td>
                    <td data-label="Активность">{formatDate(user.last_activity)}</td>
                    <td data-label="Роль"><span className={`admin-role role-${user.role}`}>{user.role}</span></td>
                    <td data-label="Действия">
                      <div className="admin-actions">
                        <button disabled={busy || user.protected} onClick={() => { setEditingUser(user); setEmailDraft(user.email || ""); }}>Email</button>
                        <button disabled={busy || user.protected || !user.telegram_id} onClick={() => unlinkTelegram(user)}>Отвязать TG</button>
                        <button disabled={busy || user.protected || !user.email} onClick={() => sendReset(user)}>Сброс пароля</button>
                        {identity?.role === "superadmin" && !user.protected && (
                          <button disabled={busy} onClick={() => changeRole(user, user.role === "admin" ? "user" : "admin")}>
                            {user.role === "admin" ? "Отозвать admin" : "Назначить admin"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer className="admin-pagination">
            <button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Назад</button>
            <span>{userPage?.page ?? page} / {userPage?.pages ?? 1}</span>
            <button disabled={page >= (userPage?.pages ?? 1)} onClick={() => setPage((value) => value + 1)}>Дальше</button>
          </footer>
        </section>
      )}

      {tab === "audit" && (
        <section className="admin-audit-card">
          <header><h2>Журнал действий</h2><span>последние 100 событий</span></header>
          <div className="admin-audit-list">
            {audit.map((item) => (
              <article key={item.id}>
                <time>{formatDate(item.created_at)}</time>
                <strong>{item.action}</strong>
                <span>Администратор: {item.actor_email || item.actor_telegram_id || "удалённый аккаунт"}</span>
                <span>Пользователь: {item.target_user_id ? `#${item.target_user_id}` : "—"}</span>
                <code>{JSON.stringify(item.details)}</code>
              </article>
            ))}
            {!audit.length && <p className="admin-empty">Критических действий ещё не было.</p>}
          </div>
        </section>
      )}

      {editingUser && (
        <div className="admin-modal-backdrop" role="presentation" onMouseDown={() => setEditingUser(null)}>
          <div className="admin-modal" role="dialog" aria-modal="true" aria-labelledby="admin-email-title" onMouseDown={(event) => event.stopPropagation()}>
            <span>Пользователь #{editingUser.id}</span>
            <h2 id="admin-email-title">Изменить email</h2>
            <input type="email" value={emailDraft} onChange={(event) => setEmailDraft(event.target.value)} autoFocus />
            <p>Изменение выполняется как доверенное действие администратора и попадёт в audit log.</p>
            <div>
              <button onClick={() => setEditingUser(null)}>Отмена</button>
              <button disabled={busy || !emailDraft.trim()} onClick={submitEmail}>Сохранить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
