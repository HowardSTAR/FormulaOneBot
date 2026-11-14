"""Isolated UI fixtures; never imported by the app or production backend.
Run: python3 ios/Preview/server.py (port 18765).
"""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from urllib.parse import urlparse, parse_qs

NOW = datetime.now(timezone.utc)
SESSIONS = [
    {"code": code, "source_name": name, "starts_at": (NOW + timedelta(hours=offset)).isoformat()}
    for code, name, offset in [("practice_1", "Practice 1", -24), ("practice_2", "Practice 2", -20),
                               ("practice_3", "Practice 3", 2), ("qualifying", "Qualifying", 6), ("race", "Race", 28)]
]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        season = int(query.get("season", [NOW.year])[0])
        round_number = int(query.get("round", [1])[0])
        if url.path == '/api/v1/weekend':
            data = {"status": "ok", "season": season, "schedule_status": "available", "sessions": SESSIONS,
                    "event": {"id": f"{season}:{round_number}", "round": round_number, "name": "Тестовый этап · превью",
                              "country": "Тестовые данные", "location": "Превью интерфейса", "date": NOW.date().isoformat(),
                              "starts_at": SESSIONS[-1]["starts_at"], "is_cancelled": False}}
        elif url.path in ['/api/drivers', '/api/constructors']:
            key = url.path.split('/')[-1]
            data = {"season": season, key: [{"position": i, "name": f"Тестовый {'пилот' if key == 'drivers' else 'конструктор'} {i}",
                                            "points": 120 - i * 10} for i in range(1, 6)]}
        elif url.path == '/api/circuit-profile':
            data = {"status": "unavailable", "season": season, "round": round_number, "profile": None}
        elif url.path.endswith('-results'):
            data = {"season": season, "round": round_number, "session": int(query.get("session", [1])[0]),
                    "results": [{"position": i, "name": f"Тестовый пилот {i}", "team": "Тестовая команда",
                                 "best": f"1:2{i}.000", "laps": 10 + i} for i in range(1, 5)]}
        else:
            self.send_error(404)
            return
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    HTTPServer(('127.0.0.1', 18765), Handler).serve_forever()
