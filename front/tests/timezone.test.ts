import test from 'node:test';
import assert from 'node:assert/strict';
import { getDisplayTimezone } from '../src/helpers/timezone.ts';

for (const [timezone, instant, expected] of [
  ['Europe/Moscow', '2026-10-11T12:00:00Z', '11.10.2026, 15:00'],
  ['Asia/Tokyo', '2026-10-11T22:00:00Z', '12.10.2026, 07:00'],
  ['Asia/Kolkata', '2026-10-11T12:00:00Z', '11.10.2026, 17:30'],
  ['America/New_York', '2026-07-11T12:00:00Z', '11.07.2026, 08:00'],
  ['America/New_York', '2026-01-11T12:00:00Z', '11.01.2026, 07:00'],
]) test(`Device time: ${timezone} at ${instant}`, () => {
  const previous = process.env.TZ;
  try {
    process.env.TZ = timezone;
    const result = new Date(instant).toLocaleString('ru-RU', {
      timeZone: getDisplayTimezone(), year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    });
    assert.equal(result, expected);
  } finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
});
