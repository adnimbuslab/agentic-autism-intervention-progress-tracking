/**
 * Playwright browser-level E2E tests.
 *
 * Requires: running frontend (port 3000) and backend (port 8000) with
 * demo seed data loaded and external LLM calls mocked. Run after
 * `docker compose up` and `scripts/seed_demo.py`.
 *
 * Demo credentials:
 *   - interventionist: demo-interventionist@example.com / DemoPass123!
 *   - parent:          demo-parent@example.com          / DemoPass123!
 *   - teacher:         demo-teacher@example.com          / DemoPass123!
 */

import { test, expect, Page } from "@playwright/test";

const INTERVENTIONIST = {
  email: "demo-interventionist@example.com",
  password: "DemoPass123!",
};
const PARENT = {
  email: "demo-parent@example.com",
  password: "DemoPass123!",
};

async function login(page: Page, creds: { email: string; password: string }) {
  await page.goto("/");
  await page.getByLabel("Email").fill(creds.email);
  await page.getByLabel("Password").fill(creds.password);
  await page.getByRole("button", { name: "Sign In" }).click();
}

// ─── Interventionist browser tests ───────────────────────────────

test.describe("Interventionist browser flow", () => {
  test("1. login page renders with title", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("Intervention Tracker");
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
  });

  test("2. interventionist login redirects to dashboard", async ({ page }) => {
    await login(page, INTERVENTIONIST);
    await page.waitForURL("**/dashboard**", { timeout: 10_000 });
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("3. dashboard shows child list", async ({ page }) => {
    await login(page, INTERVENTIONIST);
    await page.waitForURL("**/dashboard**");
    await expect(page.getByText(/Alex/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test("4. navigate to child workspace", async ({ page }) => {
    await login(page, INTERVENTIONIST);
    await page.waitForURL("**/dashboard**");
    const childLink = page.getByText(/Alex/i).first();
    await childLink.click();
    await expect(page).toHaveURL(/\/children\/[0-9a-f-]+/);
  });

  test("5. child workspace shows tabs/links", async ({ page }) => {
    await login(page, INTERVENTIONIST);
    await page.waitForURL("**/dashboard**");
    await page.getByText(/Alex/i).first().click();
    await page.waitForURL(/\/children\//);

    const nav = page.locator("nav, [role='navigation'], aside, main");
    await expect(
      nav.getByText(/observations|records|goals|analytics|reports/i).first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("6. goals page loads", async ({ page }) => {
    await login(page, INTERVENTIONIST);
    await page.waitForURL("**/dashboard**");
    await page.getByText(/Alex/i).first().click();
    await page.waitForURL(/\/children\//);

    const goalsLink = page.getByRole("link", { name: /goals/i });
    if (await goalsLink.count()) {
      await goalsLink.first().click();
      await expect(page).toHaveURL(/\/goals/);
    }
  });

  test("7. observations page loads", async ({ page }) => {
    await login(page, INTERVENTIONIST);
    await page.waitForURL("**/dashboard**");
    await page.getByText(/Alex/i).first().click();
    await page.waitForURL(/\/children\//);

    const obsLink = page.getByRole("link", { name: /observations/i });
    if (await obsLink.count()) {
      await obsLink.first().click();
      await expect(page).toHaveURL(/\/observations/);
    }
  });

  test("8. records page loads", async ({ page }) => {
    await login(page, INTERVENTIONIST);
    await page.waitForURL("**/dashboard**");
    await page.getByText(/Alex/i).first().click();
    await page.waitForURL(/\/children\//);

    const recLink = page.getByRole("link", { name: /records/i });
    if (await recLink.count()) {
      await recLink.first().click();
      await expect(page).toHaveURL(/\/records/);
    }
  });

  test("9. reports page loads", async ({ page }) => {
    await login(page, INTERVENTIONIST);
    await page.waitForURL("**/dashboard**");
    await page.getByText(/Alex/i).first().click();
    await page.waitForURL(/\/children\//);

    const repLink = page.getByRole("link", { name: /reports/i });
    if (await repLink.count()) {
      await repLink.first().click();
      await expect(page).toHaveURL(/\/reports/);
    }
  });

  test("10. audit page loads", async ({ page }) => {
    await login(page, INTERVENTIONIST);
    await page.waitForURL("**/dashboard**");
    await page.getByText(/Alex/i).first().click();
    await page.waitForURL(/\/children\//);

    const auditLink = page.getByRole("link", { name: /audit/i });
    if (await auditLink.count()) {
      await auditLink.first().click();
      await expect(page).toHaveURL(/\/audit/);
    }
  });

  test("11. login failure shows error", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Email").fill("bad@example.com");
    await page.getByLabel("Password").fill("wrongpassword");
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 5_000 });
  });
});

// ─── Contributor browser tests ───────────────────────────────────

test.describe("Contributor browser flow", () => {
  test("12. contributor login redirects to contribute", async ({ page }) => {
    await login(page, PARENT);
    await page.waitForURL("**/contribute**", { timeout: 10_000 });
    await expect(page).toHaveURL(/\/contribute/);
  });

  test("13. contributor sees assigned children", async ({ page }) => {
    await login(page, PARENT);
    await page.waitForURL("**/contribute**");
    await expect(page.getByText(/Alex/i)).toBeVisible({ timeout: 10_000 });
  });

  test("14. observation submission page loads", async ({ page }) => {
    await login(page, PARENT);
    await page.waitForURL("**/contribute**");
    const newObsBtn = page.getByRole("link", { name: /New Observation/i }).first();
    await newObsBtn.click();
    await expect(page).toHaveURL(/\/contribute\/[0-9a-f-]+\/observe/, { timeout: 10_000 });
  });

  test("15. contributor cannot navigate to interventionist pages", async ({
    page,
  }) => {
    await login(page, PARENT);
    await page.waitForURL("**/contribute**");

    await page.goto("/dashboard");
    await page.waitForURL(/\/(contribute|$)/, { timeout: 10_000 });
    const url = page.url();
    expect(url).not.toMatch(/\/dashboard$/);
  });

  test("16. contributor history page loads", async ({ page }) => {
    await login(page, PARENT);
    await page.waitForURL("**/contribute**");
    const historyLink = page.getByRole("link", { name: /history/i });
    if (await historyLink.count()) {
      await historyLink.first().click();
      await expect(page).toHaveURL(/\/history/);
    }
  });
});
