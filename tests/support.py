"""Data builders without importing other test modules or depending on their fixtures."""
import base64
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class Clock:
    now: datetime = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)

    def time(self):
        return self.now.timestamp()

    def advance(self, *, seconds=0):
        self.now += timedelta(seconds=seconds)


def replay(track_id, speed=220, laps=3):
    from app.race_rules import TRACKS
    points = TRACKS[track_id]['centerLine']
    samples = [{'t': 0, 'x': points[0][0], 'y': points[0][1], 'rotation': -1.5708}]
    elapsed = 0
    for _ in range(laps):
        for index, (x, y) in enumerate(points):
            bx, by = points[(index + 1) % len(points)]
            distance = math.hypot(bx-x, by-y)
            steps = math.ceil(distance/20)
            angle = math.atan2(by-y, bx-x)-math.pi/2
            rotation = math.atan2(math.sin(angle), math.cos(angle))
            for step in range(1, steps+1):
                elapsed += math.ceil(distance/steps/speed*1000)
                samples.append({'t': elapsed, 'x': round(x+(bx-x)*step/steps, 2),
                                'y': round(y+(by-y)*step/steps, 2), 'rotation': round(rotation, 4)})
    return {'track_id': track_id, 'time_ms': elapsed, 'telemetry': samples}


def subscription(endpoint='https://fcm.googleapis.com/fcm/send/test'):
    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip('=')
    return {'endpoint': endpoint, 'keys': {'p256dh': encode(b'\x04'+b'a'*64), 'auth': encode(b'b'*16)}}
