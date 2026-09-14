"""Parse an optional, unformatted final Mini App button directive."""
import html
from urllib.parse import unquote, urlsplit


def validate_button_destination(destination: str):
    decoded = unquote(destination)
    if not destination or any(c.isspace() or ord(c) < 32 or c == '\\' for c in decoded):
        raise ValueError('В ссылке не должно быть пробелов, управляющих символов или обратного слеша')
    try:
        url = urlsplit(destination)
        port = url.port
    except ValueError:
        raise ValueError('Некорректная ссылка кнопки') from None
    if destination.startswith('/') and not decoded.startswith('//') and not url.netloc and not url.scheme:
        return url
    if url.scheme in {'https', 'http'} and url.hostname and not url.username and not url.password:
        return url
    raise ValueError('Укажите путь Mini App (/contact-admin) или полную ссылку https://…')


def parse_button(formatted: str, plain: str):
    lines = plain.rstrip().splitlines()
    directives = [i for i, line in enumerate(lines) if line.strip().startswith('/button')]
    if not directives:
        return formatted, plain, None
    if directives != [len(lines)-1]:
        raise ValueError('Добавьте только одну строку /button в самом конце сообщения')
    footer = lines[-1].strip()
    if not footer.startswith('/button '):
        raise ValueError('Формат: /button Название | /contact-admin')
    payload = footer[len('/button '):]
    parts = payload.split('|', 1) if '|' in payload else payload.rsplit(None, 1)
    if len(parts) != 2:
        raise ValueError('Формат: /button Название | /contact-admin')
    label, destination = [v.strip() for v in parts]
    if not label or len(label) > 64:
        raise ValueError('Название кнопки должно содержать от 1 до 64 символов')
    validate_button_destination(destination)
    # Never cut through HTML entities/tags. The directive must be on its own
    # unformatted line; all existing rich text above it is retained verbatim.
    parts = formatted.rstrip().rsplit('\n',1)
    if html.unescape(parts[-1]).strip() != footer:
        raise ValueError('Уберите жирный текст, ссылки и другое форматирование со строки /button')
    body = parts[0].rstrip() if len(parts) == 2 else ''
    text = '\n'.join(lines[:-1]).rstrip()
    if not text:
        raise ValueError('Перед строкой /button нужен текст рассылки')
    return body, text, (label, destination, {})
