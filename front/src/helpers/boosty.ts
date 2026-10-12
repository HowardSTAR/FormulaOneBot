export type BoostyStatus = {
  eligible: boolean; configured: boolean; active: boolean;
  blog_url: string; level_name: string | null; checked_at: number | null;
  check_failed: boolean; premium_active: boolean; premium_override: boolean | null;
  expires_at: number | null; can_check: boolean; check_unavailable_reason: string | null;
  check_error_code?: 'auth_required' | 'unavailable' | null;
};

export function boostyCheckFailureLabel(status: BoostyStatus): string {
  if (!status.check_failed) return '';
  const saved = status.checked_at ? ' Показан последний подтверждённый статус.' : '';
  return status.check_error_code === 'auth_required'
    ? `Требуется восстановить подключение Boosty владельцем проекта.${saved} Повторная проверка станет доступна после восстановления подключения.`
    : `Не удалось связаться с Boosty.${saved} Повторите проверку позже.`;
}

export function boostySubscriptionLabel(status: BoostyStatus, now = Date.now()): string {
  const date = status.expires_at ? new Date(status.expires_at * 1000).toLocaleDateString('ru-RU') : null;
  if (status.active) {
    const name = status.level_name ? ` «${status.level_name}»` : '';
    return date ? `Подписка${name} активна до ${date}.`
      : `Подписка${name} активна. Boosty не передал дату окончания.`;
  }
  if (status.expires_at && status.expires_at * 1000 <= now) return `Подписка закончилась ${date}.`;
  return status.checked_at ? 'Активная платная подписка не найдена.' : 'Подписка ещё не проверена.';
}
