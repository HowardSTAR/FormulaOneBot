import { test, expect } from "@playwright/test";
import {
  expectSortedByPosition,
  getJson,
  resolveSeason,
} from "../helpers/api";

type Constructor = {
  position: number;
  points: number;
  name: string;
  constructorId: string;
  is_favorite: boolean;
};

type ConstructorsResponse = {
  season: number;
  round: number | null;
  constructors: Constructor[];
};

test.describe("GET /api/constructors", () => {
  test("returns constructor standings for current season", async ({
    request,
  }) => {
    const season = await resolveSeason(request);
    const { status, body } = await getJson<ConstructorsResponse>(
      request,
      "/api/constructors",
      { season }
    );

    expect(status).toBe(200);
    expect(body.season).toBe(season);
    expect(body.constructors.length).toBeGreaterThan(0);

    const first = body.constructors[0];
    expect(first).toEqual(
      expect.objectContaining({
        position: expect.any(Number),
        points: expect.any(Number),
        name: expect.any(String),
        constructorId: expect.any(String),
        is_favorite: expect.any(Boolean),
      })
    );
    expectSortedByPosition(body.constructors);
  });
});
