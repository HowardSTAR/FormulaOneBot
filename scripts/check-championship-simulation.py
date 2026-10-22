"""Run the real title/history path against the existing local Postman fixture.

Start: postman simulation run postman/simulations/forecast-recovery.sim.yaml --port 4902 --output ndjson
The fixture supplies paginated Jolpica-shaped race and qualifying archives.
Standings/calendar below are synthetic inputs; no production data is read.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('BOT_TOKEN', '123456:LOCAL_SIMULATION')

import httpx
import pandas as pd
from app.services import championship as title, prediction_history

BASE = 'http://127.0.0.1:4902/jolpica'


async def main():
    prediction_history.BASE = BASE
    schedule = [{'round': i, 'race_start_utc': f'2026-11-{i:02d}T12:00:00Z'} for i in range(1, 7)]
    drivers = pd.DataFrame([{'driverCode': f'D{i}', 'givenName': 'Fixture', 'familyName': f'Driver {i}',
                            'points': 100 if i == 0 else 65 if i == 1 else 0, 'wins': 3 if i == 0 else 0,
                            'constructorId': f'team{i//2}'} for i in range(20)])
    teams = pd.DataFrame([{'constructorId': f'team{i}', 'constructorName': f'Team {i}',
                          'points': 160 if i == 0 else 100, 'wins': 3 if i == 0 else 0} for i in range(10)])
    drivers.attrs['round'] = teams.attrs['round'] = 3
    async def driver_standings(*args): return drivers
    async def team_standings(*args): return teams
    title.get_driver_standings_async = driver_standings
    title.get_constructor_standings_async = team_standings
    async with httpx.AsyncClient(timeout=5) as client:
        await client.get(BASE + '/control/fail')
        failed = await title._get_context.__wrapped__(2026, 4, 'weekend', schedule)
        assert failed['status'] == 'unavailable' and not failed['drivers']
        await client.get(BASE + '/control/recover')
        try:
            recovered = await title._get_context.__wrapped__(2026, 4, 'weekend', schedule)
            assert recovered['status'] == 'ok', recovered
            assert [c['id'] for c in recovered['drivers']] == ['D0']
            assert [c['id'] for c in recovered['constructors']] == ['team0']
            assert recovered['drivers'][0]['finishes'][0] == 3
            assert recovered['drivers'][0]['qualifying'][0] == 3
        finally:
            await client.get(BASE + '/control/fail')
    report = {'provider_outage': failed['status'], 'recovered': recovered['status'],
              'drivers': [c['id'] for c in recovered['drivers']],
              'constructors': [c['id'] for c in recovered['constructors']]}
    Path('artifacts/championship/simulation-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    asyncio.run(main())
