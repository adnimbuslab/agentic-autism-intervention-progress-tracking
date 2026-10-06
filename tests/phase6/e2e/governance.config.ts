/**
 * Playwright config for the recorded governance E2E run (governance.spec.ts).
 *
 * Separate from playwright.config.ts because this run drives the live
 * extractor (qwen2.5:7b through Ollama), so each test takes minutes rather
 * than seconds, and every test is recorded to video. Output goes under
 * test-results/, which is gitignored.
 *
 *   npx playwright test -c tests/phase6/e2e/governance.config.ts
 */

import { defineConfig, devices } from "@playwright/test";

const SIZE = { width: 1280, height: 800 };

export default defineConfig({
  testDir: ".",
  testMatch: "governance.spec.ts",
  outputDir: "../../../test-results/governance-e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "../../../test-results/governance-e2e/results.json" }]],
  timeout: 15 * 60_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: process.env.FRONTEND_URL || "http://localhost:3000",
    viewport: SIZE,
    actionTimeout: 60_000,
    navigationTimeout: 60_000,
    video: { mode: "on", size: SIZE },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: { slowMo: 150 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: SIZE } }],
});
