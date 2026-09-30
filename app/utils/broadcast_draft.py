"""Parse a final block of button directives without losing rich text."""
import html
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit


class _FormattedPrefix(HTMLParser):
    """Cut Telegram HTML by visible characters, closing any spanning entities."""

    def __init__(self, length):
        super().__init__(convert_charrefs=True)
        self.remaining = length
        self.output = []
        self.stack = []
        self.visible = []

    def handle_starttag(self, tag, attrs):
        if self.remaining > 0:
            self.output.append(self.get_starttag_text())
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.remaining > 0 and self.stack and self.stack[-1] == tag:
            self.output.append(f'</{tag}>')
            self.stack.pop()

    def handle_data(self, data):
        self.visible.append(data)
        if self.remaining > 0:
            prefix = data[:self.remaining]
            self.output.append(html.escape(prefix, quote=False))
            self.remaining -= len(prefix)

    def result(self):
        return ''.join(self.output) + ''.join(f'</{tag}>' for tag in reversed(self.stack))


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


def parse_buttons(formatted: str, plain: str):
    lines = plain.rstrip().splitlines()
    directives = [i for i, line in enumerate(lines) if line.strip().startswith('/button')]
    if not directives:
        return formatted, plain, []
    if any(line.strip() and not line.strip().startswith('/button')
           for line in lines[directives[0]:]):
        raise ValueError('Разместите все строки /button в самом конце сообщения, после текста рассылки')
    if len(directives) > 10:
        raise ValueError('В одной рассылке можно добавить до 10 кнопок')
    buttons = []
    for index in directives:
        footer = lines[index].strip()
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
        buttons.append((label, destination, {}))
    text = '\n'.join(lines[:directives[0]]).rstrip()
    if not text:
        raise ValueError('Перед строкой /button нужен текст рассылки')
    parser = _FormattedPrefix(len(text))
    parser.feed(formatted)
    parser.close()
    if ''.join(parser.visible).rstrip() != plain.rstrip():
        raise ValueError('Не удалось разобрать форматирование сообщения. Отправьте текст заново.')
    body = parser.result()
    return body, text, buttons


def parse_button(formatted: str, plain: str):
    """Compatibility interface for callers expecting at most one button."""
    body, text, buttons = parse_buttons(formatted, plain)
    if len(buttons) > 1:
        raise ValueError('Этот обработчик поддерживает только одну кнопку')
    return body, text, buttons[0] if buttons else None
