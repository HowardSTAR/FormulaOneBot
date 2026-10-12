"""Safe Russian messages for Pydantic errors, without echoing submitted values."""

import re

FIELDS = {
    "email": "Email", "password": "Пароль", "new_password": "Новый пароль",
    "current_password": "Текущий пароль", "password_confirmation": "Повтор пароля",
    "display_name": "Ник", "code": "Код", "token": "Ссылка для восстановления",
    "confirmation": "Подтверждение", "favorite_drivers": "Избранные пилоты",
    "favorite_teams": "Избранные команды", "avatar": "Аватар",
    "season": "Сезон", "round": "Этап", "user_id": "Пользователь",
}


def validation_message(error: dict) -> str:
    kind = error.get("type", "")
    location = error.get("loc", ())
    field = FIELDS.get(str(location[-1])) if location else None
    label = f"Поле «{field}»" if field else "Поле"
    context = error.get("ctx") or {}
    if kind == "missing":
        return f"Заполните поле «{field}»." if field else "Заполните обязательные поля."
    if kind == "string_too_short":
        return f"{label} должно содержать не менее {context['min_length']} символов."
    if kind == "string_too_long":
        return f"{label} должно содержать не более {context['max_length']} символов."
    if kind == "string_pattern_mismatch":
        return "Введите код из шести цифр." if field == "Код" else "Проверьте формат введённых данных."
    if kind in {"too_short", "too_long"}:
        bound = "не менее" if kind == "too_short" else "не более"
        count = context.get("min_length" if kind == "too_short" else "max_length")
        return f"Список должен содержать {bound} {count} элементов."
    if kind in {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}:
        bounds = {"greater_than": ("больше", "gt"), "greater_than_equal": ("не меньше", "ge"),
                  "less_than": ("меньше", "lt"), "less_than_equal": ("не больше", "le")}
        text, key = bounds[kind]
        return f"Значение должно быть {text} {context[key]}."
    if kind == "json_invalid":
        return "Не удалось прочитать отправленные данные. Обновите страницу и повторите действие."
    if kind.startswith(("int_", "float_", "decimal_")):
        return "Введите корректное число."
    if kind.startswith(("date_", "datetime_", "time_")):
        return "Укажите корректные дату и время."
    if kind.startswith("bool_"):
        return "Выберите корректное значение переключателя."
    if kind in {"literal_error", "enum"}:
        return "Выберите один из доступных вариантов."
    if kind == "extra_forbidden":
        return "Запрос содержит лишние поля. Обновите страницу и повторите действие."
    if kind == "value_error":
        # Explicit application validators already use Russian. Do not include
        # Pydantic's English prefix or arbitrary exception context/input values.
        message = re.sub(r"^Value error, ", "", error.get("msg", ""))
        if re.search(r"[А-Яа-яЁё]", message):
            return message
    return f"Проверьте поле «{field}»." if field else "Проверьте введённые данные."
