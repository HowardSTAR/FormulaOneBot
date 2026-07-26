import { defineConfig } from "@playwright/test";
import dotenv from "dotenv";
import path from "path";

// Playwright does not load .env by itself — resolve next to this config file
dotenv.config({ path: path.resolve(__dirname, ".env") });

const baseURL = process.env.BASE_URL || "https://f1hub.ru";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 2 : undefined,
  reporter: [["list"], ["html", { open: "never" }]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
  },
  projects: [
    {
      name: "api",
      testMatch: "api/**/*.spec.ts",
      use: {
        extraHTTPHeaders: {
          Accept: "application/json",
        },
      },
    },
    {
      name: "chromium",
      testMatch: "ui/**/*.spec.ts",
      use: {
        browserName: "chromium",
        headless: true,
        viewport: { width: 1280, height: 720 },
      },
    },
  ],
});
