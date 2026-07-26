import { test, expect } from "@playwright/test";
import { getJson, getNextRace, resolveSeason } from "../helpers/api";

async function pickCompletedRound(
  request: Parameters<typeof getJson>[0],
  season: number,
  sessionType: "race" | "quali"
): Promise<number | null> {
  const { status, body } = await getJson<{
    races: Array<{ round: number }>;
  }>(request, "/api/season", {
    season,
    completed_only: true,
    session_type: sessionType,
  });
  if (status !== 200 || !body.races?.length) return null;
  return body.races[body.races.length - 1].round;
}

test.describe("GET race / quali / sprint results", () => {
  test("race-results returns season payload", async ({ request }) => {
    const season = await resolveSeason(request);
    const response = await request.get("/api/race-results", {
      params: { season: String(season) },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty("results");
    expect(Array.isArray(body.results)).toBe(true);
  });

  test("quali-results returns season payload", async ({ request }) => {
    const season = await resolveSeason(request);
    const response = await request.get("/api/quali-results", {
      params: { season: String(season) },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty("results");
    expect(Array.isArray(body.results)).toBe(true);
  });

  test("race-results accepts completed round when available", async ({
    request,
  }) => {
    const season = await resolveSeason(request);
    const round = await pickCompletedRound(request, season, "race");
    test.skip(round == null, "No completed race rounds yet");

    const response = await request.get("/api/race-results", {
      params: { season: String(season), round: String(round) },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(Array.isArray(body.results)).toBe(true);
  });

  test("sprint endpoints respond for current season", async ({ request }) => {
    const season = await resolveSeason(request);

    for (const path of ["/api/sprint-results", "/api/sprint-quali-results"]) {
      const response = await request.get(path, {
        params: { season: String(season) },
      });
      expect(response.status(), path).toBe(200);
      const body = await response.json();
      expect(body, path).toHaveProperty("results");
    }
  });

  test("race-details for next-race round", async ({ request }) => {
    const next = await getNextRace(request);
    const response = await request.get("/api/race-details", {
      params: {
        season: String(next.season),
        round: String(next.round),
      },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toEqual(expect.any(Object));
  });
});
