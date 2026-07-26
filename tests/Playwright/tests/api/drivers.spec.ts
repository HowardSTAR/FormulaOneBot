import { test, expect } from "@playwright/test";
import {
  expectSortedByPosition,
  getJson,
  resolveSeason,
} from "../helpers/api";

type Driver = {
  position: number;
  points: number;
  code: string;
  name: string;
  is_favorite: boolean;
  number?: string;
  constructorId?: string;
  constructorName?: string;
  driverId?: string;
};

type DriversResponse = {
  season: number;
  round: number | null;
  drivers: Driver[];
};

test.describe("GET /api/drivers", () => {
  test("returns championship standings for current season", async ({
    request,
  }) => {
    const season = await resolveSeason(request);
    const { status, body } = await getJson<DriversResponse>(
      request,
      "/api/drivers",
      { season }
    );

    expect(status).toBe(200);
    expect(body.season).toBe(season);
    expect(body.drivers.length).toBeGreaterThan(0);

    const first = body.drivers[0];
    expect(first).toEqual(
      expect.objectContaining({
        position: expect.any(Number),
        points: expect.any(Number),
        code: expect.any(String),
        name: expect.any(String),
        is_favorite: expect.any(Boolean),
      })
    );
    expect(first.code.length).toBeGreaterThan(0);
    expect(first.name.length).toBeGreaterThan(0);
    expectSortedByPosition(body.drivers);
  });

  test("rejects unknown route trailing slash style consistently", async ({
    request,
  }) => {
    // sanity: known missing path stays 404 JSON
    const response = await request.get("/api/standings");
    expect(response.status()).toBe(404);
    const body = await response.json();
    expect(body).toHaveProperty("detail");
  });
});
