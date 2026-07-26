import { test, expect } from "@playwright/test";

test("home page shows F1 Hub brand", async ({ page }) => {
  await page.goto("/");

  const brand = page.locator(".app-header-brand-wrap");
  await expect(brand).toBeVisible();
  // "F1" and "Hub" are sibling spans — allow optional whitespace
  await expect(brand).toContainText(/F1\s*Hub/);
  await expect(brand).toContainText("Race intelligence");
});
