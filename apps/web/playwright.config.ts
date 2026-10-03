import { defineConfig, devices } from "@playwright/test";

// Runs against the live stack (`make dev`): web on :5173 proxying to the API.
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  use: { baseURL: process.env.WEB_URL ?? "http://localhost:5173", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
