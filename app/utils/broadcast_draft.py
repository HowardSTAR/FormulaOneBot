"""Parse an optional, unformatted final Mini App button directive."""
import html
from urllib.parse import parse_qsl, urlsplit


def parse_button(formatted: str, plain: str):
    lines = plain.rstrip().splitlines()
    directives = [i for i, line in enumerate(lines) if line.strip().startswith('/button')]
    if not directives:
        return formatted, plain, None
    if directives != [len(lines)-1]:
        raise ValueError('Добавьте только одну строку /button в самом конце сообщения')
    footer = lines[-1].strip()
    if not footer.startswith('/button ') or '|' not in footer:
        raise ValueError('Формат: /button 🏆 Таблица прогнозов | /predictions?tab=leaderboard')
    label, destination = [v.strip() for v in footer[len('/button '):].split('|', 1)]
    if not label or len(label) > 64:
        raise ValueError('Название кнопки должно содержать от 1 до 64 символов')
    url = urlsplit(destination)
    if (url.scheme or url.netloc or url.fragment or url.path not in {'/predictions','/voting'}
            or any(c.isspace() or c == '\\' for c in destination)):
        raise ValueError('Кнопка поддерживает только /predictions и /voting внутри Mini App')
    pairs = parse_qsl(url.query, keep_blank_values=True)
    if pairs and (len(pairs) != 1 or pairs[0][0] != 'tab' or pairs[0][1] not in {'form','leaderboard'} or url.path != '/predictions'):
        raise ValueError('Для прогнозов допустим tab=form или tab=leaderboard; для голосования — /voting')
    # Never cut through HTML entities/tags. The directive must be on its own
    # unformatted line; all existing rich text above it is retained verbatim.
    parts = formatted.rstrip().rsplit('\n',1)
    if html.unescape(parts[-1]).strip() != footer:
        raise ValueError('Уберите жирный текст, ссылки и другое форматирование со строки /button')
    body = parts[0].rstrip() if len(parts) == 2 else ''
    text = '\n'.join(lines[:-1]).rstrip()
    if not text:
        raise ValueError('Перед строкой /button нужен текст рассылки')
    return body, text, (label, url.path, dict(pairs))
