import { test, expect } from "@playwright/test";
import { getJson, resolveSeason } from "../helpers/api";

test.describe("GET media endpoints", () => {
  test("pilot-portrait responds for a known driver", async ({ request }) => {
    const season = await resolveSeason(request);
    const { body } = await getJson<{
      drivers: Array<{ code: string; name: string }>;
    }>(request, "/api/drivers", { season });

    const driver = body.drivers[0];
    const response = await request.get("/api/pilot-portrait", {
      params: {
        season: String(season),
        code: driver.code,
        name: driver.name,
      },
    });

    // May be image bytes or a placeholder — accept 200 with any content-type
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toBeTruthy();
  });

  test("team-logo responds for a known constructor", async ({ request }) => {
    const season = await resolveSeason(request);
    const { body } = await getJson<{
      constructors: Array<{ constructorId: string; name: string }>;
    }>(request, "/api/constructors", { season });

    const team = body.constructors[0];
    const response = await request.get("/api/team-logo", {
      params: {
        team: team.constructorId,
        name: team.name,
        season: String(season),
      },
    });

    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toBeTruthy();
  });

  test("car-image responds for a known constructor", async ({ request }) => {
    const season = await resolveSeason(request);
    const { body } = await getJson<{
      constructors: Array<{ constructorId: string }>;
    }>(request, "/api/constructors", { season });

    const team = body.constructors[0];
    const response = await request.get("/api/car-image", {
      params: {
        team: team.constructorId,
        season: String(season),
      },
    });

    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toBeTruthy();
  });
});
