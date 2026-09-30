"""Small persistent keyboard; secondary actions live under the bot's messages."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

MAIN_BUTTONS = {
    "🏁 Уик-энд": "weekend",
    "🔮 Прогнозы": "predictions",
    "📚 Разделы": "sections",
    "👤 Моё": "personal",
}

# (heading, hint, rows of (label, callback_data)). No personal/admin mutations here.
SECTIONS = {
    "home": ("Главное меню", "Выберите действие на компактной клавиатуре внизу.", []),
    "weekend": ("🏁 Уик-энд", "Ближайший этап, расписание и главное после гонки.", [
        [("🏁 Следующая гонка", "nav:action:next")],
        [("📅 Календарь", "nav:action:calendar"), ("📰 Рекап гонки", "nav:action:recap")],
        [("← Главное меню", "nav:section:home")],
    ]),
    "sections": ("📚 Разделы", "Что хотите посмотреть?", [
        [("📊 Статистика", "nav:section:stats"), ("🏎 Справочник", "nav:section:guides")],
        [("🤝 С друзьями", "nav:action:community"), ("🎮 Игры", "nav:section:games")],
        [("← Главное меню", "nav:section:home")],
    ]),
    "stats": ("📊 Статистика", "Зачёты, сравнение пилотов и история чемпионата.", [
        [("🏎 Личный зачёт", "nav:action:drivers"), ("🏆 Кубок команд", "nav:action:teams")],
        [("⚔️ Сравнение", "nav:action:compare"), ("📈 История сезонов", "nav:action:history")],
        [("← Разделы", "nav:section:sections")],
    ]),
    "guides": ("🏎 Справочник", "Познакомьтесь с пилотами и разберитесь в терминах F1.", [
        [("🏎 Справка о пилоте", "nav:action:guide")],
        [("← Разделы", "nav:section:sections")],
    ]),
    "personal": ("👤 Моё", "Избранное, напоминания и обратная связь.", [
        [("⭐ Избранное", "nav:action:favorites"), ("⚙️ Настройки", "nav:action:settings")],
        [("📩 Связь с админом", "nav:action:feedback")],
        [("← Главное меню", "nav:section:home")],
    ]),
    "predictions": ("🔮 Прогнозы", "Составьте прогноз, посмотрите свои очки или соревнуйтесь в лиге друзей.", [
        [("← Главное меню", "nav:section:home")],
    ]),
    "games": ("🎮 Игры", "Гонки, реакция и личные рекорды — внутри F1Hub.", [
        [("← Разделы", "nav:section:sections")],
    ]),
}

WEB_DESTINATIONS = {
    "predictions": [
        ("🔮 Мой прогноз", "/predictions?tab=form", {}),
        ("🏆 Таблица прогнозов", "/predictions?tab=leaderboard", {}),
        ("🤝 Лиги друзей", "/predictions?tab=leagues", {}),
    ],
    "guides": [("📖 Wiki Formula 1", "/wiki", {})],
    "games": [
        ("🏎 Emerald Loop", "/race-game", {}),
        ("🚦 Тест реакции", "/reaction-game", {}),
        ("🟩 Reflex Grid", "/reflex-grid-game", {}),
    ],
}


def main_keyboard() -> ReplyKeyboardMarkup:
    labels = list(MAIN_BUTTONS)
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in labels[i:i + 2]] for i in (0, 2)],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел",
    )


def section_keyboard(section: str, web: InlineKeyboardMarkup | None = None) -> InlineKeyboardMarkup | None:
    rows = [[InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
            for row in SECTIONS[section][2]]
    for row in rows:
        for button in row:
            if button.callback_data in {"nav:action:next", "nav:action:guide"}:
                button.style = "primary"
    if web:
        # Keep the return button last; guide's bot lookup remains the first action.
        rows = [*rows[:-1], *web.inline_keyboard, *rows[-1:]]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
