import { test, expect } from "@playwright/test";
import { getJson, resolveSeason, SeasonRace } from "../helpers/api";

type SeasonResponse = {
  season: number;
  races: SeasonRace[];
};

test.describe("GET /api/season", () => {
  test("returns calendar races for season", async ({ request }) => {
    const season = await resolveSeason(request);
    const { status, body } = await getJson<SeasonResponse>(
      request,
      "/api/season",
      { season }
    );

    expect(status).toBe(200);
    expect(body.season).toBe(season);
    expect(body.races.length).toBeGreaterThan(0);

    const first = body.races[0];
    expect(first).toEqual(
      expect.objectContaining({
        round: expect.any(Number),
        event_name: expect.any(String),
        country: expect.any(String),
        location: expect.any(String),
        date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        is_cancelled: expect.any(Boolean),
      })
    );

    const rounds = body.races.map((r) => r.round);
    expect(rounds).toEqual([...rounds].sort((a, b) => a - b));
  });

  test("completed_only filter returns a subset of rounds", async ({
    request,
  }) => {
    const season = await resolveSeason(request);
    const full = await getJson<SeasonResponse>(request, "/api/season", {
      season,
    });
    const completed = await getJson<SeasonResponse>(request, "/api/season", {
      season,
      completed_only: true,
      session_type: "race",
    });

    expect(full.status).toBe(200);
    expect(completed.status).toBe(200);
    expect(completed.body.races.length).toBeLessThanOrEqual(
      full.body.races.length
    );
  });
});
