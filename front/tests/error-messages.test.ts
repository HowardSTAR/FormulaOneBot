import test from 'node:test';
import assert from 'node:assert/strict';
import { apiErrorMessage } from '../src/helpers/errorMessages.ts';

test('registration error from the screenshot is translated for an older backend', () => {
  assert.equal(apiErrorMessage({ detail: { message: 'Password must contain letters and numbers' } }, 422),
    'Пароль должен содержать буквы и цифры.');
});

test('legacy errors support string, object and validation-array response formats', () => {
  assert.equal(apiErrorMessage({ detail: 'Invalid email address' }, 422), 'Введите корректный адрес электронной почты.');
  assert.equal(apiErrorMessage({ detail: [{ msg: 'Password must contain at least 12 characters' }] }, 422),
    'Пароль должен содержать не менее 12 символов.');
  assert.equal(apiErrorMessage({ detail: { message: 'Invalid code' } }, 404), 'Неверный код. Проверьте его и повторите ввод.');
});

test('Russian server messages keep the specific error instead of a broad code fallback', () => {
  const message = 'Текущий пароль указан неверно';
  assert.equal(apiErrorMessage({ detail: { code: 'invalid_credentials', message } }, 401), message);
  assert.equal(apiErrorMessage({ detail: [{ type: 'value_error', msg: 'Value error, Сезон ещё не начался' }] }, 422), 'Сезон ещё не начался');
});

test('validation messages explain the field and boundaries without echoing input', () => {
  assert.equal(apiErrorMessage({ detail: [{ type: 'string_too_short', loc: ['body', 'password'], msg: 'String should have at least 15 characters', input: 'SECRET' }] }, 422),
    'Поле «Пароль» должно содержать не менее 15 символов.');
  assert.equal(apiErrorMessage({ detail: [{ type: 'string_too_long', loc: ['body', 'display_name'], ctx: { max_length: 32 } }] }, 422),
    'Поле «Ник» должно содержать не более 32 символов.');
  assert.equal(apiErrorMessage({ detail: [{ type: 'string_pattern_mismatch', loc: ['body', 'code'], msg: "String should match pattern '^\\d{6}$'" }] }, 422),
    'Введите код из шести цифр.');
  assert.equal(apiErrorMessage({ detail: [{ type: 'missing', loc: ['body', 'email'], msg: 'Field required' }] }, 422), 'Заполните поле «Email».');
});

test('unknown English messages and internal details never reach the user', () => {
  assert.equal(apiErrorMessage({ detail: { message: 'SQL error SECRET table users', code: 'unknown' } }, 400),
    'Проверьте введённые данные и повторите попытку.');
  assert.equal(apiErrorMessage({ detail: 'Unknown input Иван SECRET' }, 400),
    'Проверьте введённые данные и повторите попытку.');
  assert.equal(apiErrorMessage({ detail: { message: 'SECRET smtp config', code: 'email_delivery_failed' } }, 503),
    'Сервис временно недоступен. Попробуйте повторить запрос позже.');
  assert.equal(apiErrorMessage({ detail: { code: 'invalid_csrf', message: 'Unrecognized English message' } }, 403),
    'Не удалось подтвердить запрос. Обновите страницу и повторите действие.');
});

test('empty, malformed and unknown validation responses use Russian fallback', () => {
  for (const payload of [null, undefined, {}, { detail: null }, { detail: [] }, { detail: [{ type: 'unknown', msg: 'SECRET', loc: ['body', 'constructor'] }] }]) {
    const message = apiErrorMessage(payload, 422);
    assert.match(message, /[А-Яа-я]/);
    assert.doesNotMatch(message, /SECRET|constructor|function|undefined/);
  }
  assert.equal(apiErrorMessage(undefined, 429), 'Слишком много запросов. Подождите и повторите попытку.');
});
