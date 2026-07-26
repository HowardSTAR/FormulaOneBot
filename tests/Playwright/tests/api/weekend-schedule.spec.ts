import { test, expect } from "@playwright/test";
import { getJson, getNextRace } from "../helpers/api";

type SessionItem = {
  name: string;
  utc_iso?: string | null;
  utc?: string | null;
  local?: string | null;
};

type ScheduleResponse = {
  sessions: SessionItem[];
};

test.describe("GET /api/weekend-schedule", () => {
  test("returns sessions for next-race round", async ({ request }) => {
    const next = await getNextRace(request);
    const { status, body } = await getJson<ScheduleResponse>(
      request,
      "/api/weekend-schedule",
      { season: next.season, round_number: next.round }
    );

    expect(status).toBe(200);
    expect(body.sessions.length).toBeGreaterThan(0);

    for (const session of body.sessions) {
      expect(session.name.length).toBeGreaterThan(0);
      if (session.utc_iso) {
        expect(Number.isNaN(Date.parse(session.utc_iso))).toBe(false);
      }
    }
  });

  test("requires round_number", async ({ request }) => {
    const next = await getNextRace(request);
    const response = await request.get("/api/weekend-schedule", {
      params: { season: String(next.season) },
    });
    expect(response.status()).toBe(422);
  });
});
