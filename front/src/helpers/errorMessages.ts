// One boundary for user-facing API messages, including older server versions.
const legacyMessages: Record<string, string> = {
  'Password must contain letters and numbers': 'Пароль должен содержать буквы и цифры.',
  'Password must contain at least 12 characters': 'Пароль должен содержать не менее 12 символов.',
  'Password must not exceed 72 UTF-8 bytes': 'Пароль слишком длинный. Сократите его.',
  'Invalid email address': 'Введите корректный адрес электронной почты.',
  'Invalid email or password': 'Неверный email или пароль.',
  'Authentication required': 'Войдите в аккаунт, чтобы продолжить.',
  'Authentication failed': 'Не удалось подтвердить вход. Войдите снова или переоткройте приложение в Telegram.',
  'Invalid session': 'Сессия недействительна. Войдите снова.',
  'Invalid or expired session': 'Сессия завершена. Войдите снова.',
  'CSRF token is missing or invalid': 'Не удалось подтвердить запрос. Обновите страницу и повторите действие.',
  'Too many attempts; try again later': 'Слишком много попыток. Повторите позже.',
  'Link Telegram to use personalized features': 'Привяжите Telegram в настройках аккаунта, чтобы пользоваться этим разделом.',
  'A verified web account is required': 'Сначала подтвердите email в профиле.',
  'Invalid code': 'Неверный код. Проверьте его и повторите ввод.',
  'Link session not found': 'Ссылка для привязки не найдена. Создайте новую.',
  'Link session has expired': 'Срок действия ссылки для привязки истёк. Создайте новую.',
  'Link session is no longer pending': 'Эта ссылка уже использована или отменена. Создайте новую.',
  'Link session was opened by another Telegram account': 'Ссылка уже открыта другим аккаунтом Telegram. Создайте новую.',
  'Link session belongs to another Telegram account': 'Эта ссылка предназначена для другого аккаунта Telegram.',
  'Web account is already linked to another Telegram account': 'Аккаунт сайта уже привязан к другому аккаунту Telegram.',
  'Both accounts contain data; choose keep_web or keep_telegram': 'В обоих аккаунтах есть данные. Выберите, данные какого аккаунта сохранить.',
  'Not Found': 'Запрошенные данные не найдены.',
  'Forbidden': 'Нет доступа к этому действию.',
  'Unauthorized': 'Войдите в аккаунт, чтобы продолжить.',
};

const codeMessages: Record<string, string> = {
  invalid_credentials: 'Неверные данные для входа. Проверьте их и повторите попытку.',
  missing_session: 'Войдите в аккаунт, чтобы продолжить.',
  invalid_csrf: 'Не удалось подтвердить запрос. Обновите страницу и повторите действие.',
  invalid_verification_code: 'Неверный код из письма.',
  verification_code_expired: 'Срок действия кода истёк. Запросите новый код.',
  email_not_verified: 'Подтвердите email в профиле.',
  email_already_registered: 'Этот email уже зарегистрирован. Войдите в аккаунт.',
  telegram_link_required: 'Привяжите Telegram в настройках аккаунта, чтобы пользоваться этим разделом.',
  invalid_reset_token: 'Ссылка для восстановления недействительна. Запросите новое письмо.',
  password_reset_expired: 'Срок действия ссылки истёк. Запросите новое письмо.',
  rate_limit_exceeded: 'Слишком много попыток. Повторите позже.',
  verification_resend_cooldown: 'Подождите перед повторной отправкой письма.',
  merge_strategy_required: 'Выберите, данные какого аккаунта сохранить.',
  link_not_found: 'Код или ссылка для привязки не найдены. Запросите новые.',
  link_expired: 'Срок действия ссылки для привязки истёк. Создайте новую.',
  link_already_used: 'Ссылка для привязки уже использована. Создайте новую.',
};

const fields: Record<string, string> = {
  email: 'Email', password: 'Пароль', new_password: 'Новый пароль',
  current_password: 'Текущий пароль', password_confirmation: 'Повтор пароля',
  display_name: 'Ник', code: 'Код', token: 'Ссылка для восстановления',
};

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function translatedMessage(message: unknown): string | undefined {
  if (typeof message !== 'string') return;
  const text = message.replace(/^Value error, /, '').trim();
  if (Object.hasOwn(legacyMessages, text)) return legacyMessages[text];
  // Preserve useful messages produced in Russian; never expose unknown English
  // framework errors, backend internals or HTML error pages.
  if (/^(?:(?:Email|Telegram|Boosty|QR-код)\s+)?[А-Яа-яЁё]/.test(text) && text.length <= 500) return text;
}

function validationMessage(value: unknown): string {
  const issue = record(value);
  const translated = translatedMessage(issue.msg);
  if (translated) return translated;
  const location = Array.isArray(issue.loc) ? issue.loc : [];
  const key = String(location.at(-1));
  const name = Object.hasOwn(fields, key) ? fields[key] : undefined;
  const label = name ? `Поле «${name}»` : 'Поле';
  const context = record(issue.ctx);
  const count = typeof context.min_length === 'number' ? context.min_length
    : typeof context.max_length === 'number' ? context.max_length
      : Number(String(issue.msg || '').match(/at (?:least|most) (\d+)/)?.[1]);
  if (issue.type === 'missing') return name ? `Заполните поле «${name}».` : 'Заполните обязательные поля.';
  if (issue.type === 'string_too_short' && Number.isFinite(count)) return `${label} должно содержать не менее ${count} символов.`;
  if (issue.type === 'string_too_long' && Number.isFinite(count)) return `${label} должно содержать не более ${count} символов.`;
  if (issue.type === 'string_pattern_mismatch') return name === 'Код' ? 'Введите код из шести цифр.' : 'Проверьте формат введённых данных.';
  if (issue.type === 'json_invalid') return 'Не удалось прочитать отправленные данные. Обновите страницу и повторите действие.';
  if (String(issue.type).startsWith('int_') || String(issue.type).startsWith('float_')) return 'Введите корректное число.';
  return name ? `Проверьте поле «${name}».` : 'Проверьте введённые данные.';
}

export function apiErrorMessage(payload: unknown, status: number): string {
  if (status >= 500) return 'Сервис временно недоступен. Попробуйте повторить запрос позже.';
  const detail = record(payload).detail;
  if (Array.isArray(detail)) return detail.length ? validationMessage(detail[0]) : 'Проверьте введённые данные.';
  const data = record(detail);
  const message = translatedMessage(typeof detail === 'string' ? detail : data.message);
  if (message) return message;
  if (typeof data.code === 'string' && Object.hasOwn(codeMessages, data.code)) return codeMessages[data.code];
  if (status === 401) return 'Войдите в аккаунт или откройте приложение в Telegram.';
  if (status === 403) return 'Нет доступа к этому действию. Проверьте аккаунт и права доступа.';
  if (status === 404) return 'Запрошенные данные не найдены.';
  if (status === 409) return 'Не удалось сохранить изменения. Обновите страницу и повторите действие.';
  if (status === 410) return 'Срок действия ссылки или кода истёк. Запросите новые.';
  if (status === 422 || status === 400) return 'Проверьте введённые данные и повторите попытку.';
  if (status === 429) return 'Слишком много запросов. Подождите и повторите попытку.';
  return 'Не удалось выполнить запрос. Попробуйте ещё раз.';
}
