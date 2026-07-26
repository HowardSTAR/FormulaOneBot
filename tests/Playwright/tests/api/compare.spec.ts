import { test, expect } from "@playwright/test";
import { getJson, resolveSeason } from "../helpers/api";

test.describe("GET compare", () => {
  test("compare/multi for two drivers", async ({ request }) => {
    const season = await resolveSeason(request);
    const { body } = await getJson<{
      drivers: Array<{ code: string }>;
    }>(request, "/api/drivers", { season });

    const codes = body.drivers.map((d) => d.code).filter(Boolean).slice(0, 2);
    expect(codes.length).toBe(2);

    const response = await request.get("/api/compare/multi", {
      params: {
        drivers: codes.join(","),
        season: String(season),
      },
    });
    expect(response.status()).toBe(200);
    const compare = await response.json();
    expect(compare).toEqual(expect.any(Object));
  });

  test("compare/teams/multi for two constructors", async ({ request }) => {
    const season = await resolveSeason(request);
    const { body } = await getJson<{
      constructors: Array<{ constructorId: string }>;
    }>(request, "/api/constructors", { season });

    const teams = body.constructors
      .map((c) => c.constructorId)
      .filter(Boolean)
      .slice(0, 2);
    expect(teams.length).toBe(2);

    const response = await request.get("/api/compare/teams/multi", {
      params: {
        teams: teams.join(","),
        season: String(season),
      },
    });
    expect(response.status()).toBe(200);
    const compare = await response.json();
    expect(compare).toEqual(expect.any(Object));
  });
});
