import { useMediaQuery } from '../../helpers/useMediaQuery';
import { SelectField } from '../../components/CustomSelect';
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest } from "../../helpers/api";
import { Link, useSearchParams } from 'react-router-dom';
import "./admin.css";
import { AnalyticsDashboard } from "./AnalyticsDashboard";
import { AdminNotifications, AdminToolDirectory } from "./AdminTools";
import { AdminControl } from './AdminControl';
import { AdminRecapNews } from './AdminRecapNews';
import { AdminPremium } from './AdminPremium';
import './admin-workspace.css';
import { AdminAudit } from './AdminAudit';

const sections = [
  { id: 'control', label: 'Доставка', hint: 'Очередь, ошибки и статусы', description: '' },
  { id: 'recovery', label: 'Результаты прогнозов', hint: 'Проверка и пересчёт', description: 'Выберите этап или весь сезон. Сначала проверьте изменения, затем подтвердите применение.' },
  { id: 'notifications', label: 'Рассылки сайта', hint: 'Аудитория и предпросмотр', description: 'Подготовьте сообщение, проверьте получателей и подтвердите отправку. Telegram-рассылки здесь не запускаются.' },
  { id: 'recap-news', label: 'Новости рекапа', hint: 'Источники и публикации', description: 'Подключите разрешённые ленты. Скрывайте неподходящие публикации без изменения результатов гонки и прогнозов.' },
  { id: 'users', label: 'Пользователи', hint: 'Поиск и доступ', description: 'Найдите аккаунт по имени, email или Telegram. Управление ролями доступно супер-администратору.' },
  { id: 'overview', label: 'Аналитика', hint: 'Аудитория и сценарии', description: '' },
  { id: 'games', label: 'Игры', hint: 'Рекорды и модерация', description: 'Статистика игровых результатов. Удаление рекордов требует отдельного подтверждения.' },
  { id: 'audit', label: 'Журнал действий', hint: 'Кто и что изменил', description: 'Найдите изменение по периоду, автору, пользователю или типу действия.' },
  { id: 'tools', label: 'Справка и инструменты', hint: 'Дополнительные возможности', description: '' },
] as const;

type Role = "user" | "admin" | "superadmin";
type UserSortField = "created_at" | "last_activity" | "role";
type SortOrder = "asc" | "desc";
type GameRecordScope = "all" | "reaction" | "race" | "reflex";
type AdminIdentity = { id: number; role: "admin" | "superadmin"; email: string | null; telegram_id: number | null; can_manage_own_premium: boolean };
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
  const compact = useMediaQuery('(max-width: 600px)');
  const [params, setParams] = useSearchParams();
  const tab = sections.find(section => section.id === params.get('section'))?.id || 'control';
  const season = Number(params.get('season'));
  const round = Number(params.get('round'));
  const recoveryTarget = Number.isInteger(season) && season >= 1950 && season <= 2100 && Number.isInteger(round) && round >= 1 && round <= 40
    ? { season, round } : undefined;
  useEffect(() => { window.scrollTo(0, 0); }, [tab, season, round]);
  const activeSection = sections.find(section => section.id === tab)!;
  const setTab = (value: string, target?: { season: number; round: number }) => {
    setError('');
    setMessage('');
    setParams(target ? { section: value, season: String(target.season), round: String(target.round) } : { section: value });
  };
  const [identity, setIdentity] = useState<AdminIdentity | null>(null);
  const [userPage, setUserPage] = useState<UserPage | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | Role>("all");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<UserSortField>("last_activity");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [historyUser, setHistoryUser] = useState<number>();
  const [auditRevision, setAuditRevision] = useState(0);
  const [gameRecords, setGameRecords] = useState<GameRecordStats | null>(null);
  const [gameScope, setGameScope] = useState<GameRecordScope>('all');
  const gameSelection = gameRecords?.games.find(game => game.key === gameScope);
  const recordsToRemove = gameScope === 'all' ? gameRecords?.total_records : gameSelection?.records;
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);
  const emailDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (editingUser) emailDialog.current?.showModal(); }, [editingUser]);
  const [emailDraft, setEmailDraft] = useState("");
  const [emailError, setEmailError] = useState("");
  useEffect(() => {
    if (emailError) emailDialog.current?.querySelector<HTMLInputElement>('#admin-email')?.focus();
  }, [emailError]);
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

  const loadGameRecords = useCallback(async () => {
    setGameRecords(await apiRequest<GameRecordStats>("/api/admin/game-records"));
  }, []);

  useEffect(() => { void loadIdentity().catch((reason: Error) => setError(reason.message)); }, [loadIdentity]);
  useEffect(() => { if (tab === "users") void loadUsers().catch((reason: Error) => setError(reason.message)); }, [loadUsers, tab]);
  useEffect(() => { if (tab === "games") void loadGameRecords().catch((reason: Error) => setError(reason.message)); }, [loadGameRecords, tab]);

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError("");
    try {
      await action();
      setMessage(success);
      setAuditRevision(value => value + 1);
      await (tab === "users" ? loadUsers() : loadGameRecords());
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

  const submitEmail = async () => {
    if (!editingUser || busy) return;
    setBusy(true);
    setEmailError('');
    try {
      await apiRequest(`/api/admin/users/${editingUser.id}/email`, { email: emailDraft.trim() }, 'PATCH');
    } catch (reason) {
      setEmailError(reason instanceof Error ? reason.message : 'Не удалось сохранить email. Повторите попытку.');
      setBusy(false);
      return;
    }
    setEditingUser(null);
    setMessage('Email пользователя обновлён');
    setAuditRevision(value => value + 1);
    setError('');
    try { await loadUsers(); }
    catch { setError('Email сохранён, но список пользователей не обновился. Повторите загрузку страницы.'); }
    finally { setBusy(false); }
  };

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
        <h1>Админ-панель</h1>
        <div className="admin-identity">
          <span>{identity?.role === 'superadmin' ? 'Супер-администратор' : identity ? 'Администратор' : 'Проверяем доступ…'}</span>
        </div>
      </header>

      <div className="admin-workspace">
      <label className="admin-mobile-section">Раздел админ-панели<SelectField value={tab} disabled={busy || recoveryBusy} onChange={event => setTab(event)}>{sections.map(section => <option key={section.id} value={section.id}>{section.label}</option>)}</SelectField></label>
      <nav className="admin-section-nav" aria-label="Разделы администрирования">
        {sections.map(section => <Link key={section.id} to={`?section=${section.id}`} aria-disabled={recoveryBusy || busy || undefined} onClick={event => { if (recoveryBusy || busy) event.preventDefault(); else { setError(''); setMessage(''); } }} className={tab === section.id ? 'admin-section-link active' : 'admin-section-link'} aria-current={tab === section.id ? 'page' : undefined}><strong>{section.label}</strong><small>{section.hint}</small></Link>)}
      </nav>
      <div className="admin-workspace-content">
      <header className="admin-section-heading"><h2>{activeSection.label}</h2>{activeSection.description && <p>{activeSection.description}</p>}</header>
      {recoveryBusy && <p role="status">Проверка или пересчёт выполняется. Дождитесь завершения; проверку сезона можно остановить после текущего этапа.</p>}

      {(message || error) && (
        <div className={`admin-notice ${error ? "error" : "success"}`} role="status">
          {error || message}
          <button onClick={() => { setError(""); setMessage(""); }} aria-label="Закрыть">×</button>
        </div>
      )}

      {(tab === 'control' || tab === 'recovery') && <AdminControl key={tab} mode={tab === 'recovery' ? 'recovery' : 'delivery'} target={recoveryTarget} locked={recoveryBusy} onNavigate={setTab} onBusy={setRecoveryBusy} />}
      {tab === "overview" && <AnalyticsDashboard />}

      {tab === "notifications" && <AdminNotifications adminId={identity?.id} />}
      {tab === "tools" && <AdminToolDirectory />}
      {tab === 'recap-news' && <AdminRecapNews />}
      {tab === 'users' && identity?.can_manage_own_premium && <AdminPremium />}
      {tab === "users" && (
        <section className="admin-users-card">
          <header className="admin-users-tools">
            <form onSubmit={(event) => { event.preventDefault(); setPage(1); setSearch(searchInput.trim()); }}>
              <input
                type="search" name="user-search" autoComplete="off"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Email, Telegram ID, имя…"
                aria-label="Поиск пользователей"
              />
              <button type="submit">Найти</button>
            </form>
            <div className="admin-users-role-filter">
              <SelectField aria-label="Роль пользователя" value={roleFilter} onChange={(event) => { setPage(1); setRoleFilter(event as typeof roleFilter); }}>
                <option value="all">Все роли</option>
                <option value="user">Участники</option>
                <option value="admin">Администраторы</option>
                <option value="superadmin">Супер-администраторы</option>
              </SelectField>
            </div>
            <span role="status">{userPage ? `Найдено: ${userPage.total}` : 'Загружаем пользователей…'}</span>
          </header>
          {userPage?.items.length === 0 && <p className="admin-empty">Пользователи не найдены. Измените поиск или роль.</p>}
          <label className="admin-user-sort">Сортировка<SelectField value={`${sortBy}:${sortOrder}`} onChange={value => { const [field, order] = value.split(':'); setSortBy(field as UserSortField); setSortOrder(order as SortOrder); setPage(1); }}>
            <option value="last_activity:desc">Сначала активные</option><option value="last_activity:asc">Сначала давно не заходившие</option>
            <option value="created_at:desc">Сначала новые</option><option value="created_at:asc">Сначала ранние регистрации</option>
            <option value="role:asc">Роль по возрастанию</option><option value="role:desc">Роль по убыванию</option>
          </SelectField></label>
          <div className="admin-table-wrap" role="region" aria-label="Таблица пользователей" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>№ участника</th>
                  <th>Пользователь</th>
                  <th>Telegram</th>
                  <th aria-sort={sortBy === "created_at" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>
                    <button type="button" tabIndex={compact ? -1 : 0} className="admin-sort-button" onClick={() => toggleUserSort("created_at")}>
                      Регистрация {sortIndicator("created_at")}
                    </button>
                  </th>
                  <th aria-sort={sortBy === "last_activity" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>
                    <button type="button" tabIndex={compact ? -1 : 0} className="admin-sort-button" onClick={() => toggleUserSort("last_activity")}>
                      Активность {sortIndicator("last_activity")}
                    </button>
                  </th>
                  <th aria-sort={sortBy === "role" ? (sortOrder === "asc" ? "ascending" : "descending") : "none"}>
                    <button type="button" tabIndex={compact ? -1 : 0} className="admin-sort-button" onClick={() => toggleUserSort("role")}>
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
                      <details className="admin-user-actions" open={historyUser === user.id}>
                        <summary onClick={event => { event.preventDefault(); setHistoryUser(historyUser === user.id ? undefined : user.id); }}>Карточка аккаунта</summary>
                        {historyUser === user.id && <><p>Пользователь #{user.id} · {user.email_verified ? 'Email подтверждён' : 'Email не подтверждён'}</p><AdminAudit userId={user.id} revision={auditRevision} /></>}
                      </details>
                    </td>
                    <td data-label="Telegram">
                      {user.telegram_id ? <><strong>{user.telegram_id}</strong><small>{user.telegram_username ? `@${user.telegram_username}` : "username не указан"}</small></> : "—"}
                    </td>
                    <td data-label="Регистрация">{formatDate(user.created_at)}</td>
                    <td data-label="Активность">{formatDate(user.last_activity)}</td>
                    <td data-label="Роль"><span className={`admin-role role-${user.role}`}>{user.role==='superadmin'?'Супер-администратор':user.role==='admin'?'Администратор':'Участник'}</span></td>
                    <td data-label="Действия">
                      <details className="admin-user-actions"><summary>Действия<span className="admin-action-user"> · {user.display_name || 'участник'}</span></summary><div className="admin-actions">
                        <button disabled={busy || user.protected} onClick={() => { setEmailError(''); setEditingUser(user); setEmailDraft(user.email || ""); }}>Email</button>
                        <button disabled={busy || user.protected || !user.telegram_id} onClick={() => unlinkTelegram(user)}>Отвязать Telegram</button>
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
          {!gameRecords && !error && <p role="status">Загружаем результаты игр…</p>}
          {!gameRecords && error && <button type="button" onClick={() => {
            setError('');
            void loadGameRecords().catch((reason: Error) => setError(reason.message));
          }}>Повторить загрузку</button>}
          {gameRecords && <>
            <p className="admin-games-overview"><strong>{gameRecords.total_records}</strong> результатов · <strong>{gameRecords.total_players}</strong> игроков</p>
            <dl className="admin-game-stats">
              {gameRecords.games.map(game => <div key={game.key}>
                <dt>{game.label}</dt><dd>{game.records} результатов · {game.players} игроков</dd>
              </div>)}
            </dl>
            {identity?.role === "superadmin" && <details className="admin-game-moderation">
              <summary>Модерация рекордов</summary>
              <label>Какие результаты очистить<SelectField value={gameScope} disabled={busy} onChange={value => setGameScope(value as GameRecordScope)}>
                <option value="all">Все игры</option>
                {gameRecords.games.map(game => <option key={game.key} value={game.key}>{game.label}</option>)}
              </SelectField></label>
              <p>Будет удалено записей: <strong>{recordsToRemove ?? 0}</strong>. Аккаунты игроков сохранятся.</p>
              <button type="button" className="admin-danger-button" disabled={busy || !recordsToRemove}
                onClick={() => deleteGameRecords(gameScope, gameScope === 'all' ? `все результаты во всех играх (${recordsToRemove} записей)` : `все результаты игры «${gameSelection?.label}» (${recordsToRemove} записей)`)}>
                Очистить результаты
              </button>
            </details>}
          </>}
        </section>
      )}

      {tab === "audit" && <AdminAudit />}
      </div></div>
      {editingUser && (
        <dialog ref={emailDialog} className="admin-modal" aria-labelledby="admin-email-title" onCancel={event => { if (busy) event.preventDefault(); else setEditingUser(null); }}>
          <form onSubmit={event => { event.preventDefault(); void submitEmail(); }} aria-busy={busy}>
            <p className="admin-modal-user">Пользователь #{editingUser.id}</p>
            <h2 id="admin-email-title">Изменить email</h2>
            <label htmlFor="admin-email">Email</label>
            <input id="admin-email" name="email" autoComplete="off" spellCheck={false} type="email" required disabled={busy} aria-invalid={!!emailError} aria-describedby={emailError ? "admin-email-error" : undefined} value={emailDraft} onChange={(event) => setEmailDraft(event.target.value)} autoFocus />
            {emailError && <p id="admin-email-error" className="admin-email-error" role="alert">{emailError}</p>}
            <p>Изменение выполняется как доверенное действие администратора и попадёт в audit log.</p>
            <div>
              <button type="button" disabled={busy} onClick={() => setEditingUser(null)}>Отмена</button>
              <button type="submit" disabled={busy || !emailDraft.trim()}>{busy ? 'Сохраняем…' : 'Сохранить'}</button>
            </div>
          </form>
        </dialog>
      )}
    </div>
  );
}
