"""Local UX fixtures only: no database, bot, upstream requests or delivery jobs.

Run beside Vite with F1HUB_PREVIEW_API=http://127.0.0.1:8009.
Unknown endpoints fail explicitly; settings POSTs only update this process's RAM.
"""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

DRIVERS = [dict(code=code, name=name, driverId=driver_id, position=i+1, points=302-i*30,
                constructorId='mercedes' if i < 2 else 'ferrari', constructorName='Mercedes' if i < 2 else 'Ferrari')
           for i, (code, name, driver_id) in enumerate([('ANT','Andrea Kimi Antonelli','antonelli'),('RUS','George Russell','russell'),('LEC','Charles Leclerc','leclerc'),('HAM','Lewis Hamilton','hamilton'),('ALO','Fernando Alonso','alonso'),('VER','Max Verstappen','max_verstappen')])]
SETTINGS = dict(timezone='Etc/GMT-3', notify_before=60, notify_before_minutes=[60], notifications_enabled=True, reminder_sessions=31, results_spoiler=False)


def fixture(path, params):
    year = int(params.get('season', ['2026'])[0])
    round_number = int(params.get('round', ['15'])[0])
    # Deliberate unavailable calendar for recovery-state QA; not real 1997 data.
    if path == '/api/season' and year == 1997: return None
    races = [dict(round=i,event_name=f'Test Grand Prix {i}',location='Баку' if i==15 else 'Сахир', date=f'{year}-09-26' if i <=15 else f'{year}-10-04', race_start_utc=f'{year}-09-26T11:00:00Z' if i<=15 else f'{year}-10-04T14:00:00Z', quali_start_utc=f'{year}-09-25T12:00:00Z', available_practice_sessions=[1,2,3]) for i in range(1,18)]
    # Normal and sprint schedules exercise the calendar without external requests.
    races[15].update(quali_start_utc=f'{year}-10-03T14:00:00Z', practice1_start_utc=f'{year}-10-02T10:00:00Z', practice2_start_utc=f'{year}-10-02T14:00:00Z', practice3_start_utc=f'{year}-10-03T10:00:00Z')
    races[16].update(date=f'{year}-10-11',race_start_utc=f'{year}-10-11T14:00:00Z',quali_start_utc=f'{year}-10-10T14:00:00Z',practice1_start_utc=f'{year}-10-09T10:00:00Z',sprint_quali_start_utc=f'{year}-10-09T14:00:00Z',sprint_start_utc=f'{year}-10-10T10:00:00Z')
    if path=='/api/auth/me': return dict(id=1,email='qa@example.test',telegram_id=1,email_verified=True,role='superadmin',display_name='UX test',telegram_username='ux_test')
    if path=='/api/admin/me': return dict(id=1,role='superadmin')
    if path in ['/api/settings','/api/account/settings']: return SETTINGS.copy()
    if path=='/api/drivers': return dict(season=year,round=15,drivers=DRIVERS)
    if path=='/api/constructors': return dict(season=year,round=15,constructors=[dict(position=1,name='Mercedes',constructorId='mercedes',points=538),dict(position=2,name='Ferrari',constructorId='ferrari',points=378)])
    if path=='/api/constructor-details': return dict(constructorId='ferrari',name='Ferrari',nationality='Italian',url='',bio='Краткая биография команды [12].',season=year,drivers=[],principal=None,season_stats=dict(position=2,points=378,points_source='standings',grand_prix_points=330,standings_round=15,grand_prix_races=15,grand_prix_wins=2,grand_prix_podiums=5,grand_prix_poles=3),career_stats=dict(grand_prix_entered=2,grand_prix_events=1,career_points=33,highest_race_finish=dict(position=2,count=1),podiums=2,pole_positions=1,world_championships=16))
    if path=='/api/driver-details':
        return dict(driverId='alonso',code='ALO',givenName='Fernando',familyName='Alonso',permanentNumber='14',dateOfBirth='1981-07-29',nationality='Spanish',url='',bio='Краткая биография пилота […].',headshot_url='',season=year,season_stats=dict(position=5,points=40,grand_prix_races=15,grand_prix_points=30,grand_prix_wins=0,grand_prix_podiums=1,grand_prix_poles=0,grand_prix_top10s=5,fastest_laps=0,dnfs=1,sprint_races=2,sprint_points=10,sprint_wins=0,sprint_podiums=0,sprint_poles=0,sprint_top10s=2),career_stats=dict(grand_prix_entered=400,career_points=2300,highest_race_finish=dict(position=1,count=32),podiums=100,highest_grid=dict(position=1,count=22),pole_positions=22,world_championships=2,dnfs=40))
    if path=='/api/admin/tools/control': return dict(as_of=time.time(),counts=dict(failed=2,blocked=30,retry=1,pending=0,unknown=0),oldest_pending=None,recoveries={},push_configured=False,incomplete=[])
    if path=='/api/admin/tools/control/deliveries': return dict(items=[dict(event_key='test:classification:2026:15',recipient=i,channel='telegram',status=params.get('status',['failed'])[0],attempts=1,next_attempt=0,updated=time.time(),message_id=None,error='test_error',expires=time.time()+60) for i in [1,2]],has_more=False)
    if path=='/api/admin/tools/prediction-recovery': return []
    if path=='/api/admin/tools/prediction-recovery/rounds': return dict(rounds=[dict(season=year,round=15,event_name='Test Grand Prix 15',missing=['fastest_lap_driver'],current={},first_retirement_drivers=[])])
    if path=='/api/admin/audit-log': return dict(items=[dict(id=1,action='user.role_changed',created_at='2026-10-01T12:00:00Z',target_user_id=2,actor_email='qa@example.test',actor_telegram_id=1,details=dict(**{'from':'user','to':'admin'}))])
    if path=='/api/reflex-grid-leaderboard': return dict(entries=[],total=0,mode='timed',difficulty='normal')
    if path=='/api/reaction-leaderboard/profile': return dict(participate=False,display_name='UX test')
    if path=='/api/season': return dict(season=year,races=races[:15] if params.get('completed_only') else races)
    if path=='/api/next-race': return dict(status='ok',**races[-1],fp1_start_utc='2026-10-02T10:00:00Z',fp2_start_utc='2026-10-02T14:00:00Z',fp3_start_utc='2026-10-03T10:00:00Z')
    if path=='/api/race-details':
        race = races[min(round_number-1,len(races)-1)]
        return dict(season=year, country='Азербайджан', event_format='conventional',
                    sessions=[dict(name='Квалификация',utc_iso=race['quali_start_utc']),
                              dict(name='Гонка',utc_iso=race['race_start_utc'])], **race)
    if path in ['/api/race-results','/api/sprint-results','/api/quali-results','/api/sprint-quali-results','/api/practice-results']:
        rows=[dict(**{k:v for k,v in d.items() if k!='points'},team=d['constructorName'],points=[25,18,15,12,10,8][i],time='1:42.526',gap='+0.837',driver=d['code'],best='1:42.526',q1='1:43.100',q2='1:42.800',q3='1:42.526',laps=51,status='Finished') for i,d in enumerate(DRIVERS)]
        return dict(season=year,round=round_number,race_info={'event_name':f'Test Grand Prix {round_number}'},results=rows,session=int(params.get('session',['1'])[0]),available_sessions=[1,2,3],is_sprint_weekend=False,data_incomplete=False)
    if path.startswith('/api/compare/'):
        return dict(labels=['R1','R2','R3'],series=[dict(code=d['code'],history=[25-i,18-i,15-i],race_wins=2-i%2,quali_wins=1,quali_samples=3,total_points=d['points'],average_points=19-i) for i,d in enumerate(DRIVERS[:2])])
    if path=='/api/votes/me': return dict(race_votes={'15':4},driver_votes={})
    if path=='/api/votes/stats': return dict(stats=[dict(round=15,avg=4,count=3)])
    if path=='/api/votes/driver-stats': return dict(stats=[dict(driver_code='RUS',count=2)])
    if path=='/api/web-notifications/unread-count': return {'unread':1}
    if path=='/api/web-notifications': return dict(items=[dict(id=1,title='Итоги гонки',body='\n'.join(f'P{i+1} · {d["name"]} · {d["constructorName"]} · 0' for i,d in enumerate(DRIVERS)),url='/race-results?season=2026&round=15',created_at=time.time()-86400,read_at=None,historical_snapshot=True)],unread=1,next_before=None,push={'enabled':False,'public_key':''})
    if path=='/api/favorites': return dict(drivers=['ALO'],teams=['ferrari'])
    if path=='/api/driver-guide': return dict(guide=None)
    if path in ['/api/race-recap','/api/f1/race-recap']: return dict(status='ready',items=[],chronicle=[],news=[])
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def do_GET(self):
        url=urlsplit(self.path)
        params=parse_qs(url.query)
        # Delayed historical response verifies that a new year wins the race.
        if url.path=='/api/season' and params.get('season')==['2025']: time.sleep(1)
        value=fixture(url.path,params)
        self.send_response(200 if value is not None else 404)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(value if value is not None else {'detail':'Тестовый источник: сценарий недоступен'},ensure_ascii=False).encode())

    def do_POST(self):
        is_settings = self.path in ['/api/settings', '/api/account/settings']
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        if is_settings:
            values = json.loads(body)
            SETTINGS.update({key: value for key, value in values.items() if key in SETTINGS})
        self.send_response(200 if is_settings or self.path.startswith('/api/analytics/') else 405)
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')


if __name__=='__main__':
    print('UX fixture server: http://127.0.0.1:8009 (no persistent writes)',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8009),Handler).serve_forever()
