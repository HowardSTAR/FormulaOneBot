import { test, expect } from "@playwright/test";
import { getJson, resolveSeason } from "../helpers/api";

test.describe("GET driver / constructor details", () => {
  test("driver-details by driverId from standings", async ({ request }) => {
    const season = await resolveSeason(request);
    const { body: standings } = await getJson<{
      drivers: Array<{ driverId?: string; code?: string }>;
    }>(request, "/api/drivers", { season });

    const sample = standings.drivers.find((d) => d.driverId || d.code);
    expect(sample).toBeTruthy();

    const params: Record<string, string | number> = { season };
    if (sample!.driverId) params.driverId = sample!.driverId;
    else params.code = sample!.code!;

    const response = await request.get("/api/driver-details", {
      params: Object.fromEntries(
        Object.entries(params).map(([k, v]) => [k, String(v)])
      ),
    });
    expect(response.status()).toBe(200);
    const details = await response.json();
    expect(details).toEqual(expect.any(Object));
  });

  test("constructor-details by constructorId from standings", async ({
    request,
  }) => {
    const season = await resolveSeason(request);
    const { body: standings } = await getJson<{
      constructors: Array<{ constructorId: string }>;
    }>(request, "/api/constructors", { season });

    const sample = standings.constructors[0];
    expect(sample?.constructorId).toBeTruthy();

    const response = await request.get("/api/constructor-details", {
      params: {
        constructorId: sample.constructorId,
        season: String(season),
      },
    });
    expect(response.status()).toBe(200);
    const details = await response.json();
    expect(details).toEqual(expect.any(Object));
  });
});
