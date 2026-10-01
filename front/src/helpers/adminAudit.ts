export const auditActionLabels: Record<string, string> = {
  'user.role_changed': 'Изменена роль',
  'user.email_changed': 'Изменён email',
  'user.telegram_unlinked': 'Отвязан Telegram',
  'user.password_reset_sent': 'Отправлен сброс пароля',
  'game_records.cleared': 'Очищены все игровые рекорды',
  'game_records.user_cleared': 'Очищены рекорды пользователя',
};
const roles: Record<string, string> = {user: 'Участник', admin: 'Администратор', superadmin: 'Супер-администратор'};
const scopes: Record<string, string> = {all: 'Все игры', reaction: 'Тест реакции', race: 'Emerald Loop', reflex: 'Reflex Grid'};
export function describeAuditChange(action: string, details: Record<string, unknown>): string {
  const text = (value: unknown) => value == null ? 'Не задано' : String(value);
  if (action === 'user.role_changed') return `Было: ${roles[text(details.from)] || text(details.from)} → стало: ${roles[text(details.to)] || text(details.to)}`;
  if (action === 'user.email_changed') return `Было: ${text(details.from)} → стало: ${text(details.to)}`;
  if (action.startsWith('game_records.') && action.endsWith('cleared')) return `${scopes[text(details.scope)] || text(details.scope)} · удалено записей: ${text(details.total)}`;
  if (action === 'user.telegram_unlinked') return `Связь с Telegram #${text(details.telegram_id)} удалена`;
  if (action === 'user.password_reset_sent') return `Письмо для сброса пароля отправлено на ${text(details.email)}`;
  return 'Подробности доступны в технических сведениях.';
}
