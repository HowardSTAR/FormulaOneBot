"""Build synthetic examples with the production title calculator, no network."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.championship import calculate_candidates, notification_text, NOTE


def entry(code, name, score, wins=0):
    return {'id': code, 'name': name, 'points': float(score), 'wins': wins,
            'finishes': [wins] + [0] * 31}


def main():
    target = Path('artifacts/championship')
    target.mkdir(parents=True, exist_ok=True)
    drivers = [entry('ANT', 'Кими Антонелли', 350, 7), entry('RUS', 'Джордж Расселл', 315, 7),
               entry('NOR', 'Ландо Норрис', 299, 2), entry('VER', 'Макс Ферстаппен', 285, 1),
               entry('LEC', 'Шарль Леклер', 260, 1), entry('HAM', 'Льюис Хэмилтон', 240, 1)]
    teams = [entry('mercedes', 'Mercedes', 665, 14), entry('mclaren', 'McLaren', 610, 3),
             entry('ferrari', 'Ferrari', 500, 2)]
    start = time.monotonic()
    single = {'status': 'ok', 'season': 2026, 'round': 22, 'scope': 'Основная гонка', 'note': NOTE,
              'drivers': calculate_candidates(drivers, 2, 0, grid_size=6),
              'constructors': calculate_candidates(teams, 2, 0, grid_size=6, cars=2)}
    finale = [entry('ANT', 'Кими Антонелли', 350, 7), entry('RUS', 'Джордж Расселл', 348, 7),
              entry('NOR', 'Ландо Норрис', 342, 4), *drivers[3:]]
    multiple = {**single, 'round': 24, 'drivers': calculate_candidates(finale, 0, 0, grid_size=6),
                'constructors': calculate_candidates([entry('mercedes', 'Mercedes', 700, 8), entry('mclaren', 'McLaren', 695, 7), teams[2]], 0, 0, cars=2, grid_size=6)}
    sprint = {**single, 'scope': 'Уикенд, включая спринт',
              'drivers': calculate_candidates(drivers, 2, 1, has_sprint=True, grid_size=6),
              'constructors': calculate_candidates(teams, 2, 1, cars=2, has_sprint=True, grid_size=6)}
    for name, context in [('single', single), ('multiple', multiple), ('sprint', sprint)]:
        (target / f'{name}.json').write_text(json.dumps(context, ensure_ascii=False), encoding='utf-8')
    message = '🏎 Скоро гонка!\n\nЧерез 1 час · Гран-при (демонстрация)\n' + notification_text(single)
    (target / 'notification.txt').write_text(message, encoding='utf-8')
    # HTML preview of the exact notification text, with a real collapsed detail.
    message = message.replace('<tg-spoiler>', '<details><summary>Раскрыть условия чемпионства</summary><div>').replace('</tg-spoiler>', '</div></details>')
    (target / 'notification.html').write_text('''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Предпросмотр уведомления</title><style>body{background:#17212b;color:#e9eef3;font:16px/1.65 system-ui;margin:0;padding:28px}main{max-width:460px;margin:auto}small{color:#abb7c2}article{background:#263544;border-radius:20px;padding:24px;margin-top:22px;white-space:pre-line}details{white-space:normal;border-top:1px solid #ffffff20;margin-top:18px;padding-top:14px}details div{white-space:pre-line;margin-top:14px}summary{cursor:pointer;color:#85bbeb}a{display:block;text-align:center;border:1px solid #77a6d160;border-radius:12px;padding:10px;margin-top:12px;color:#85bbeb}</style><main><small>Демонстрационные данные · сообщение не отправлено</small><article>''' + message + '</article><a href="conditions-390.png">🏆 Все условия титула</a><p><small>В Telegram условия скрыты спойлером. Здесь показано раскрытие для предпросмотра.</small></p></main></html>', encoding='utf-8')
    print(json.dumps({'seconds': round(time.monotonic() - start, 2), 'single_candidates': [c['id'] for c in single['drivers']], 'multiple_candidates': [c['id'] for c in multiple['drivers']]}, ensure_ascii=True))


if __name__ == '__main__':
    main()
