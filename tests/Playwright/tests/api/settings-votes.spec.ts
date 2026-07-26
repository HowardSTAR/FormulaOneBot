import { test, expect } from "@playwright/test";
import { getJson, resolveSeason } from "../helpers/api";

test.describe("GET /api/settings (guest defaults)", () => {
  test("returns default settings without session", async ({ request }) => {
    const response = await request.get("/api/settings");
    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toEqual(
      expect.objectContaining({
        timezone: expect.any(String),
        notify_before: expect.any(Number),
        notifications_enabled: expect.any(Boolean),
      })
    );
  });
});

test.describe("GET votes stats (public)", () => {
  test("votes/stats requires season", async ({ request }) => {
    const response = await request.get("/api/votes/stats");
    expect(response.status()).toBe(422);
  });

  test("votes/stats returns averages for season", async ({ request }) => {
    const season = await resolveSeason(request);
    const { status, body } = await getJson<{
      stats: Array<{ round: number; avg: number; count: number }>;
    }>(request, "/api/votes/stats", { season });

    expect(status).toBe(200);
    expect(Array.isArray(body.stats)).toBe(true);
    if (body.stats.length > 0) {
      expect(body.stats[0]).toEqual(
        expect.objectContaining({
          round: expect.any(Number),
          avg: expect.any(Number),
          count: expect.any(Number),
        })
      );
    }
  });

  test("votes/driver-stats returns seasonal driver votes", async ({
    request,
  }) => {
    const season = await resolveSeason(request);
    const { status, body } = await getJson<{
      stats: Array<{ driver_code: string; count: number }>;
      round_winners?: unknown[];
    }>(request, "/api/votes/driver-stats", { season });

    expect(status).toBe(200);
    expect(Array.isArray(body.stats)).toBe(true);
  });

  test("votes/me as guest returns empty vote maps", async ({ request }) => {
    const season = await resolveSeason(request);
    const { status, body } = await getJson<{
      race_votes: Record<string, unknown>;
      driver_votes: Record<string, unknown>;
    }>(request, "/api/votes/me", { season });

    expect(status).toBe(200);
    expect(body.race_votes).toEqual({});
    expect(body.driver_votes).toEqual({});
  });
});
