import { defineConfig, devices } from "@playwright/test";

const PORT = 4310;

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  // Each test boots the 17 MB engine; one at a time keeps boot times steady.
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.BASE_URL ?? `http://localhost:${PORT}`,
    trace: "retain-on-failure",
    acceptDownloads: true,
    // Every test loads the engine the same way, without the service worker's cache.
    serviceWorkers: "block",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } } },
    { name: "firefox", use: { ...devices["Desktop Firefox"], viewport: { width: 1440, height: 1000 } } },
    { name: "webkit", use: { ...devices["Desktop Safari"], viewport: { width: 1440, height: 1000 } } },
  ],
  webServer: process.env.BASE_URL ? undefined : {
    command: `node scripts/serve.mjs ${PORT}`,
    port: PORT,
    reuseExistingServer: true,
  },
});
