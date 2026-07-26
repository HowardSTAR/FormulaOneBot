import { test, expect } from "@playwright/test";

test.describe("GET public leaderboards", () => {
  test("reaction-leaderboard responds with entries", async ({ request }) => {
    const response = await request.get("/api/reaction-leaderboard");
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toEqual(
      expect.objectContaining({
        entries: expect.any(Array),
      })
    );
  });

  test("reflex-grid-leaderboard requires mode and difficulty", async ({
    request,
  }) => {
    const response = await request.get("/api/reflex-grid-leaderboard");
    expect(response.status()).toBe(422);
  });

  test("reflex-grid-leaderboard timed/easy returns entries", async ({
    request,
  }) => {
    const response = await request.get("/api/reflex-grid-leaderboard", {
      params: { mode: "timed", difficulty: "easy" },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toEqual(
      expect.objectContaining({
        entries: expect.any(Array),
      })
    );
  });
});
