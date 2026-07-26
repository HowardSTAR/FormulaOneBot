import { test, expect } from "@playwright/test";

test.describe("GET /health", () => {
  test("returns ok and ready database", async ({ request }) => {
    const response = await request.get("/health");
    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toMatchObject({
      status: "ok",
      database: "ready",
    });
  });
});
