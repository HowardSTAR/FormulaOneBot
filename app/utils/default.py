import random
from datetime import datetime

# Фразы для "путешественников во времени"
TIME_MACHINE_PHRASES = [
    "🏎️ Бот не машина времени! Марти Макфлай еще не вернулся с результатами.",
    "🔮 Мой хрустальный шар в ремонте, будущее туманно.",
    "🦖 В этом году гонки либо еще не придумали, либо пилоты ездили на динозаврах.",
    "🤖 Я бы сказал, кто выиграл, но спойлеры запрещены Временной Полицией.",
    "📅 Док Браун запретил мне смотреть в эту дату, чтобы не нарушить пространственно-временной континуум.",
    "🛠️ Данные за этот год находятся в разработке у Вселенной (или у Берни Экклстоуна).",
    "🚫 Ошибка хронологии! Выберите год, когда Формула-1 действительно существует (1950 — наше время).",
    "⚡ 1.21 Гигаватт?! К сожалению, у меня нет столько энергии, чтобы заглянуть в этот год."
]


def validate_f1_year(year: int) -> str | None:
    """
    Проверяет год. Возвращает смешную фразу, если год некорректен,
    или None, если всё ок.
    """
    current_year = datetime.now().year

    # Формула 1 началась в 1950 году
    if year < 1950:
        return random.choice(TIME_MACHINE_PHRASES) + "\n\n(Подсказка: Формула-1 стартовала в 1950 году)"

    # Если год больше текущего (на год вперед и далее)
    if year > current_year:
        return random.choice(TIME_MACHINE_PHRASES)

    return None

OWNER_TELEGRAM_ID = 2099386

# Соответствие кода пилота имени файла с его фотографией
# Файлы лежат в app/assets/pilots
DRIVER_CODE_TO_FILE = {
    "ALB": "Alexander Albon.png",
    "ANT": "Andrea Kimi Antonelli.png",
    "SAI": "Carlos Sainz.png",
    "LEC": "Charles Leclerc.png",
    "OCO": "Esteban Ocon.png",
    "ALO": "Fernando Alonso.png",
    "COL": "Franco Colapinto.png",
    "BOR": "Gabriel Bortoleto.png",
    "RUS": "George Russell.png",
    "HAD": "Isack Hadjar.png",
    "DOO": "Jack Doohan.png",
    "STR": "Lance Stroll.png",
    "NOR": "Lando Norris.png",
    "HAM": "Lewis Hamilton.png",
    "LAW": "Liam Lawson.png",
    "VER": "Max Verstappen.png",
    "HUL": "Nico Hülkenberg.png",
    "BEA": "Oliver Bearman.png",
    "PIA": "Oscar Piastri.png",
    "GAS": "Pierre Gasly.png",
    "TSU": "Yuki Tsunoda.png",
}

# маппинг нормализованных названий/кодов -> файл логотипа
_TEAM_KEY_TO_FILE: dict[str, str] = {
    "mclaren": "mclaren.png",
    "mclarenf1team": "mclaren.png",

    "mercedes": "mersedec.png",
    "mercedesamgf1team": "mersedec.png",

    "redbull": "redbull.png",
    "redbullracing": "redbull.png",

    "rbf1team": "racing bulls.png",
    "racingbulls": "racing bulls.png",

    "ferrari": "ferrari.png",
    "scuderiaferrari": "ferrari.png",

    "williams": "williams.png",
    "williamsracing": "williams.png",

    "astonmartin": "aston martin.png",
    "astonmartinf1team": "aston martin.png",

    "haas": "haas.png",
    "haasf1team": "haas.png",

    "sauber": "stacke.png",
    "stakef1teamkicksauber": "stacke.png",

    "alpine": "alpine.png",
    "alpinef1team": "alpine.png",
}

SESSION_NAME_RU = {
    "Practice 1": "Практика 1",
    "Practice 2": "Практика 2",
    "Practice 3": "Практика 3",
    "Free Practice 1": "Практика 1",
    "Free Practice 2": "Практика 2",
    "Free Practice 3": "Практика 3",

    "Sprint Qualifying": "Спринт-квалификация",
    "Sprint Shootout": "Спринт-квалификация",  # на всякий случай
    "Sprint": "Спринт",

    "Qualifying": "Квалификация",
    "Race": "Гонка",
}