import { test, expect } from "@playwright/test";

/**
 * GET endpoints that require a session — without auth they must stay locked.
 * No register/login here (prod has no staging).
 */
const protectedGets = [
  "/api/auth/me",
  "/api/favorites",
  "/api/predictions/current",
  "/api/predictions/leaderboard",
] as const;

test.describe("GET protected endpoints without session", () => {
  for (const path of protectedGets) {
    test(`${path} returns 401 missing_session`, async ({ request }) => {
      const response = await request.get(path);
      expect(response.status()).toBe(401);

      const body = await response.json();
      expect(body).toMatchObject({
        detail: {
          code: "missing_session",
          message: expect.any(String),
        },
      });
    });
  }
});
