import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../helpers/api";
import { useSearchParams } from 'react-router-dom';
import "./admin.css";
import { AnalyticsDashboard } from "./AnalyticsDashboard";
import { AdminNotifications, AdminToolDirectory } from "./AdminTools";
import { AdminControl } from './AdminControl';
import { AdminRecapNews } from './AdminRecapNews';
import './admin-workspace.css';
import { auditActionLabels, describeAuditChange } from '../../helpers/adminAudit';

const sections = [
  { id: 'control', label: 'Доставка', hint: 'Очередь, ошибки и статусы', description: 'Посмотрите, какие уведомления требуют внимания. Отправки не запускаются при просмотре.' },
  { id: 'recovery', label: 'Результаты прогнозов', hint: 'Проверка и пересчёт', description: 'Выберите этап или весь сезон. Сначала проверьте изменения, затем подтвердите применение.' },
  { id: 'notifications', label: 'Рассылки сайта', hint: 'Аудитория и предпросмотр', description: 'Подготовьте сообщение, проверьте получателей и подтвердите отправку. Telegram-рассылки здесь не запускаются.' },
  { id: 'recap-news', label: 'Новости рекапа', hint: 'Источники и публикации', description: 'Подключите разрешённые ленты. Скрывайте неподходящие публикации без изменения результатов гонки и прогнозов.' },
  { id: 'users', label: 'Пользователи', hint: 'Поиск и доступ', description: 'Найдите аккаунт по имени, email или Telegram. Управление ролями доступно супер-администратору.' },
  { id: 'overview', label: 'Аналитика', hint: 'Аудитория и сценарии', description: 'Смотрите посещения, возвращаемость и использование функций. Анонимные браузеры считаются отдельно.' },
  { id: 'games', label: 'Игры', hint: 'Рекорды и модерация', description: 'Статистика игровых результатов. Удаление рекордов требует отдельного подтверждения.' },
  { id: 'audit', label: 'Журнал действий', hint: 'Кто и что изменил', description: 'Последние 100 административных действий: автор, время и объект изменения.' },
  { id: 'tools', label: 'Справка и инструменты', hint: 'Дополнительные возможности', description: 'Переходы к аналитике предсказаний и подсказки по диагностике.' },
] as const;

type Role = "user" | "admin" | "superadmin";
type UserSortField = "created_at" | "last_activity" | "role";
type SortOrder = "asc" | "desc";
type GameRecordScope = "all" | "reaction" | "race" | "reflex";
type AdminIdentity = { id: number; role: "admin" | "superadmin"; email: string | null; telegram_id: number | null };
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
type UserPage = {
  items: ManagedUser[];
  page: number;
  pages: number;
  total: number;
  page_size: number;
  sort_by: UserSortField;
  sort_order: SortOrder;
};
type AuditItem = {
  id: number;
  action: string;
  created_at: string;
  target_user_id: number | null;
  actor_email: string | null;
  actor_telegram_id: number | null;
  details: Record<string, unknown>;
};
type GameRecordStat = {
  key: Exclude<GameRecordScope, "all">;
  label: string;
  records: number;
  players: number;
};
type GameRecordStats = {
  games: GameRecordStat[];
  total_records: number;
  total_players: number;
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function AdminPage() {
  const [params, setParams] = useSearchParams();
  const tab = sections.find(section => section.id === params.get('section'))?.id || 'control';
  useEffect(() => { window.scrollTo(0,0); }, [tab]);
  const activeSection = sections.find(section => section.id === tab)!;
  const setTab = (value: string) => { setError(''); setMessage(''); setParams({ section: value }); };
  const [identity, setIdentity] = useState<AdminIdentity | null>(null);
  const [userPage, setUserPage] = useState<UserPage | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | Role>("all");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<UserSortField>("last_activity");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditSearch, setAuditSearch] = useState('');
  const [auditAction, setAuditAction] = useState('all');
  const filteredAudit = audit.filter(item => (auditAction === 'all' || item.action === auditAction) && `${item.target_user_id ?? ''} ${item.actor_email ?? ''} ${item.actor_telegram_id ?? ''} ${describeAuditChange(item.action, item.details)}`.toLowerCase().includes(auditSearch.toLowerCase().trim()));
  const [gameRecords, setGameRecords] = useState<GameRecordStats | null>(null);
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);
  const [emailDraft, setEmailDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [recoveryBusy, setRecoveryBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadIdentity = useCallback(async () => {
    setIdentity(await apiRequest<AdminIdentity>("/api/admin/me"));
  }, []);

  const loadUsers = useCallback(async () => {
    setUserPage(await apiRequest<UserPage>("/api/admin/users", {
      search,
      role: roleFilter,
      page,
      page_size: 25,
      sortBy,
      sortOrder,
    }));
  }, [page, roleFilter, search, sortBy, sortOrder]);

  const loadAudit = useCallback(async () => {
    setAuditLoading(true);
    try {
      const result = await apiRequest<{ items: AuditItem[] }>("/api/admin/audit-log", { limit: 100 });
      setAudit(result.items);
    } finally { setAuditLoading(false); }
  }, []);

  const loadGameRecords = useCallback(async () => {
    setGameRecords(await apiRequest<GameRecordStats>("/api/admin/game-records"));
  }, []);

  useEffect(() => { void loadIdentity().catch((reason: Error) => setError(reason.message)); }, [loadIdentity]);
  useEffect(() => { if (tab === "users") void loadUsers().catch((reason: Error) => setError(reason.message)); }, [loadUsers, tab]);
  useEffect(() => { if (tab === "games") void loadGameRecords().catch((reason: Error) => setError(reason.message)); }, [loadGameRecords, tab]);
  useEffect(() => { if (tab === "audit") void loadAudit().catch((reason: Error) => setError(reason.message)); }, [loadAudit, tab]);

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError("");
    try {
      await action();
      setMessage(success);
      await Promise.all([loadUsers(), loadGameRecords(), loadAudit()]);
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

  const deleteUserGameRecords = (user: ManagedUser) => {
    const label = user.display_name || user.email || `#${user.id}`;
    if (!window.confirm(`Удалить все игровые результаты пользователя «${label}»? Это действие нельзя отменить.`)) return;
    void runAction(
      () => apiRequest(`/api/admin/users/${user.id}/game-records/all`, {}, "DELETE"),
      "Игровые результаты пользователя удалены",
    );
  };

  const deleteGameRecords = (scope: GameRecordScope, label: string) => {
    const confirmation = window.prompt(
      `Будут навсегда удалены ${label}. Профили игроков сохранятся. Для подтверждения введите УДАЛИТЬ`,
    );
    if (confirmation !== "УДАЛИТЬ") return;
    void runAction(
      () => apiRequest(`/api/admin/game-records/${scope}`, {}, "DELETE"),
      scope === "all" ? "Все игровые результаты удалены" : `Результаты «${label}» удалены`,
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
  const toggleUserSort = (field: UserSortField) => {
    setPage(1);
    if (sortBy === field) {
      setSortOrder((current) => current === "asc" ? "desc" : "asc");
      return;
    }
    setSortBy(field);
    setSortOrder(field === "role" ? "asc" : "desc");
  };
  const sortIndicator = (field: UserSortField) => (
    <span className="admin-sort-indicator" aria-hidden>
      {sortBy === field ? (sortOrder === "asc" ? "▲" : "▼") : "↕"}
    </span>
  );

  return (
    <div className="admin-page">
      <header className="admin-hero">
        <div>
          <span className="admin-eyebrow">Управление проектом</span>
          <h1>Админ-панель</h1>
        </div>
        <div className="admin-identity">
          <span>{identity?.role === 'superadmin' ? 'Супер-администратор' : identity ? 'Администратор' : 'Проверяем доступ…'}</span>
          <strong>{identityLabel}</strong>
        </div>
      </header>

      <div className="admin-workspace">
      <label className="admin-mobile-section">Раздел админ-панели<select value={tab} disabled={busy || recoveryBusy} onChange={event => setTab(event.target.value)}>{sections.map(section => <option key={section.id} value={section.id}>{section.label}</option>)}</select></label>
      <nav className="admin-section-nav" aria-label="Разделы администрирования">
        {sections.map(section => <button type="button" key={section.id} disabled={recoveryBusy || busy} onClick={() => setTab(section.id)} className={tab === section.id ? 'active' : undefined} aria-current={tab === section.id ? 'page' : undefined}><strong>{section.label}</strong><small>{section.hint}</small></button>)}
      </nav>
      <div className="admin-workspace-content">
      <header className="admin-section-heading"><span>Админ-панель / {activeSection.label}</span><h2>{activeSection.label}</h2><p>{activeSection.description}</p></header>
      {recoveryBusy && <p role="status">Проверка или пересчёт выполняется. Дождитесь завершения; проверку сезона можно остановить после текущего этапа.</p>}

      {(message || error) && (
        <div className={`admin-notice ${error ? "error" : "success"}`} role="status">
          {error || message}
          <button onClick={() => { setError(""); setMessage(""); }} aria-label="Закрыть">×</button>
        </div>
      )}

      {(tab === 'control' || tab === 'recovery') && <AdminControl key={tab} mode={tab === 'recovery' ? 'recovery' : 'delivery'} onNavigate={setTab} onBusy={setRecoveryBusy} />}
      {tab === "overview" && <AnalyticsDashboard />}

      {tab === "notifications" && <AdminNotifications adminId={identity?.id} />}
      {tab === "tools" && <AdminToolDirectory />}
      {tab === 'recap-news' && <AdminRecapNews />}
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
              <option value="user">Участники</option>
              <option value="admin">Администраторы</option>
              <option value="superadmin">Супер-администраторы</option>
            </select>
            <span>{userPage ? `Найдено: ${userPage.total}` : 'Загружаем пользователей…'}</span>
          </header>
          <div className="admin-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>№ участника</th>
                  <th>Пользователь</th>
                  <th>Telegram</th>
                  <th aria-sort={sortBy === "created_at" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>
                    <button type="button" className="admin-sort-button" onClick={() => toggleUserSort("created_at")}>
                      Регистрация {sortIndicator("created_at")}
                    </button>
                  </th>
                  <th aria-sort={sortBy === "last_activity" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>
                    <button type="button" className="admin-sort-button" onClick={() => toggleUserSort("last_activity")}>
                      Активность {sortIndicator("last_activity")}
                    </button>
                  </th>
                  <th aria-sort={sortBy === "role" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>
                    <button type="button" className="admin-sort-button" onClick={() => toggleUserSort("role")}>
                      Роль {sortIndicator("role")}
                    </button>
                  </th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {userPage?.items.map((user, index) => (
                  <tr key={user.id}>
                    <td data-label="№ участника">
                      {(userPage.page - 1) * userPage.page_size + index + 1}
                    </td>
                    <td data-label="Пользователь">
                      <strong>{user.display_name || user.email || "Без имени"}</strong>
                      <small>{user.email || "Email не указан"}</small>
                    </td>
                    <td data-label="Telegram">
                      {user.telegram_id ? <><strong>{user.telegram_id}</strong><small>{user.telegram_username ? `@${user.telegram_username}` : "username не указан"}</small></> : "—"}
                    </td>
                    <td data-label="Регистрация">{formatDate(user.created_at)}</td>
                    <td data-label="Активность">{formatDate(user.last_activity)}</td>
                    <td data-label="Роль"><span className={`admin-role role-${user.role}`}>{user.role==='superadmin'?'Супер-администратор':user.role==='admin'?'Администратор':'Участник'}</span></td>
                    <td data-label="Действия">
                      <details className="admin-user-actions"><summary>Действия · {user.display_name || 'участник'}</summary><div className="admin-actions">
                        <button disabled={busy || user.protected} onClick={() => { setEditingUser(user); setEmailDraft(user.email || ""); }}>Email</button>
                        <button disabled={busy || user.protected || !user.telegram_id} onClick={() => unlinkTelegram(user)}>Отвязать TG</button>
                        <button disabled={busy || user.protected || !user.email} onClick={() => sendReset(user)}>Сброс пароля</button>
                        <button
                          className="admin-danger-button"
                          disabled={busy || (user.protected && user.id !== identity?.id) || !user.telegram_id}
                          onClick={() => deleteUserGameRecords(user)}
                        >
                          Удалить рекорды
                        </button>
                        {identity?.role === "superadmin" && !user.protected && (
                          <button disabled={busy} onClick={() => changeRole(user, user.role === "admin" ? "user" : "admin")}>
                            {user.role === "admin" ? "Отозвать admin" : "Назначить admin"}
                          </button>
                        )}
                      </div></details>
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

      {tab === "games" && (
        <section className="admin-games-card">
          <header className="admin-games-header">
            <div>
              <span className="admin-eyebrow">Таблицы лидеров</span>
              <h2>Игровые результаты</h2>
              <p>Удаляются только результаты. Имена, настройки участия и аккаунты игроков сохраняются.</p>
            </div>
            <div className="admin-games-total">
              <strong>{gameRecords?.total_records ?? "—"}</strong>
              <span>результатов · {gameRecords?.total_players ?? 0} игроков</span>
            </div>
          </header>

          <div className="admin-games-grid">
            {gameRecords?.games.map((game) => (
              <article key={game.key}>
                <span>{game.label}</span>
                <strong>{game.records}</strong>
                <small>{game.players} игроков</small>
                <button
                  className="admin-danger-button"
                  disabled={busy || identity?.role !== "superadmin" || game.records === 0}
                  onClick={() => deleteGameRecords(game.key, `все результаты игры «${game.label}»`)}
                >
                  Очистить результаты
                </button>
              </article>
            ))}
            {!gameRecords && <div className="admin-skeleton admin-games-skeleton" />}
          </div>

          <aside className="admin-danger-zone">
            <div>
              <strong>Удалить результаты всех игр</strong>
              <p>Будут очищены таблицы «Игра на реакцию», Emerald Loop и Reflex Grid.</p>
              {identity?.role !== "superadmin" && <small>Действие доступно только superadmin.</small>}
            </div>
            <button
              className="admin-danger-button"
              disabled={busy || identity?.role !== "superadmin" || !gameRecords?.total_records}
              onClick={() => deleteGameRecords("all", "все результаты во всех играх")}
            >
              Удалить всё
            </button>
          </aside>
        </section>
      )}

      {tab === "audit" && (
        <section className="admin-audit-card">
          <header><h3>Последние изменения</h3><span>последние 100 событий</span></header>
          {auditLoading && <p role="status">Загрузка журнала…</p>}
          <div className="control-filters"><label>Поиск по автору, ID участника или изменению<input value={auditSearch} onChange={event => setAuditSearch(event.target.value)} /></label><label>Тип действия<select value={auditAction} onChange={event => setAuditAction(event.target.value)}><option value="all">Все действия</option>{[...new Set(audit.map(item => item.action))].map(action => <option key={action} value={action}>{auditActionLabels[action] || action}</option>)}</select></label></div>
          <p className="ui-data-context">Показано {filteredAudit.length} из {audit.length} загруженных событий. Фильтры действуют на последние 100 записей.</p>
          <div className="admin-audit-list">
            {filteredAudit.map((item) => (
              <article key={item.id}>
                <time>{formatDate(item.created_at)}</time>
                <strong>{auditActionLabels[item.action] || 'Административное действие'}</strong>
                <span>Администратор: {item.actor_email || item.actor_telegram_id || "удалённый аккаунт"}</span>
                <span>Пользователь: {item.target_user_id ? `#${item.target_user_id}` : "—"}</span>
                <p>{describeAuditChange(item.action, item.details)}</p>
                <details><summary>Технические сведения</summary><code>{item.action} · {JSON.stringify(item.details)}</code></details>
              </article>
            ))}
            {!auditLoading && !error && !audit.length && <p className="admin-empty">Действий в журнале пока нет.</p>}
            {!!audit.length && !filteredAudit.length && <p className="admin-empty">Нет совпадений. Измените поиск или тип действия.</p>}
          </div>
        </section>
      )}

      </div></div>
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
