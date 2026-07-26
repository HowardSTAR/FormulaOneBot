import { test, expect } from "@playwright/test";
import { getNextRace, resolveSeason } from "../helpers/api";

test.describe("GET /api/next-race", () => {
  test("returns upcoming or current event payload", async ({ request }) => {
    const body = await getNextRace(request);

    expect(body.status).toBe("ok");
    expect(body.season).toEqual(expect.any(Number));
    expect(body.round).toEqual(expect.any(Number));
    expect(body.event_name.length).toBeGreaterThan(0);
    expect(body.country.length).toBeGreaterThan(0);
    expect(body.location.length).toBeGreaterThan(0);
    expect(body.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(typeof body.is_cancelled).toBe("boolean");
  });

  test("accepts season query and keeps season in response", async ({
    request,
  }) => {
    const season = await resolveSeason(request);
    const body = await getNextRace(request, season);
    expect(body.season).toBe(season);
  });
});
