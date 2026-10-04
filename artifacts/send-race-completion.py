"""Recover one requested race notification without resetting persistent watermarks."""
import argparse
import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from aiogram import Bot
from app.config import get_settings
from app.db import db, get_last_notified_round
from app.f1_data import get_race_results_async, get_season_schedule_short_async
from app.services import race_recap
from app.utils import notifications
from app.utils.telegram_presentation import rich_enabled


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--round', type=int, required=True)
    parser.add_argument('--send', action='store_true')
    args = parser.parse_args()
    await db.connect()
    bot = None
    try:
        assert args.season == datetime.now(timezone.utc).year, 'Only the current season can be recovered.'
        schedule = await get_season_schedule_short_async(args.season)
        now = datetime.now(timezone.utc)
        finished = []
        for event in schedule:
            if event.get('is_testing') or event.get('is_cancelled') or not event.get('race_start_utc'):
                continue
            start = datetime.fromisoformat(event['race_start_utc'])
            if start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
            status = str(event.get('race_status') or '').lower()
            if status in {'completed', 'results_ready'} or not status and now > start + timedelta(hours=2):
                finished.append(event)
        assert finished and max(int(event['round']) for event in finished) == args.round, 'Requested round is not the latest completed race.'
        event = next(event for event in finished if int(event['round']) == args.round)
        assert now - datetime.fromisoformat(event['race_start_utc'].replace('Z', '+00:00')) < timedelta(days=7), 'Race is too old.'
        watermark = await get_last_notified_round(args.season)
        assert not watermark or watermark <= args.round, 'A later race has already been processed.'
        frame = (await get_race_results_async(args.season, args.round)).copy()
        assert len(race_recap.classified_rows(frame)) >= 10, 'Classification is incomplete.'
        if 'FullName' not in frame:
            frame['FullName'] = (frame['FirstName'].fillna('') + ' ' + frame['LastName'].fillna('')).str.strip()
        with patch.object(race_recap, 'get_race_results_async', AsyncMock(return_value=frame)):
            recap = await asyncio.wait_for(race_recap.get_race_recap_with_news(args.season, args.round), timeout=90)
        assert recap.get('status') in {'ready', 'partial'} and recap.get('items'), 'No verified recap is ready.'
        users = await notifications.get_users_with_settings()
        groups = await notifications.get_all_group_chats()
        summary = {'season': args.season, 'round': args.round, 'event': event['event_name'],
                   'classification_rows': len(frame), 'users': len(users), 'groups': len(groups),
                   'recap_status': recap['status'], 'recap': recap['items'],
                   'chronicle': recap.get('chronicle', []), 'news': recap.get('news', []),
                   'native_table': rich_enabled(), 'mode': 'send' if args.send else 'preview'}
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if args.send:
            bot = Bot(token=get_settings().bot.token)
            # Change only this invocation's guard. Frozen per-recipient outbox keys
            # still prevent replay; the stored watermark is never moved backwards.
            with patch.object(notifications, 'get_last_notified_round', AsyncMock(return_value=args.round - 1)), \
                 patch.object(notifications, 'get_season_schedule_short_async', AsyncMock(return_value=finished)), \
                 patch.object(notifications, 'get_race_results_async', AsyncMock(return_value=frame)), \
                 patch.object(notifications, 'get_race_recap', AsyncMock(return_value=recap)):
                await notifications.check_and_send_results(bot)
            rows = await (await db.conn.execute(
                "SELECT status,COUNT(*) FROM telegram_deliveries WHERE event_key LIKE ? GROUP BY status",
                (f'race-photo:{args.season}:{args.round}:%',))).fetchall()
            print(json.dumps({'result_deliveries': [list(row) for row in rows]}, ensure_ascii=False), flush=True)
    finally:
        if bot: await bot.session.close()
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
