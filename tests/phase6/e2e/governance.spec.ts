/**
 * Governance-critical end-to-end scenarios, driven through the UI and
 * recorded to video.
 *
 * The browser counterpart of tests/phase6/integration/test_governance_e2e.py.
 * Nothing is mocked: contributor notes go through the live extractor
 * (Ollama, qwen2.5:7b), deterministic validation, routing, persistence, the
 * verification gate, the adequacy router, the analytics engine and the
 * operational deterministic reporter.
 *
 * Inputs are the same short synthetic observations as the API suite. No
 * corpus text is used. The model's field values are not asserted -- this
 * tests governance, not extraction quality.
 *
 * The scenarios share one freshly created child and run in order:
 *
 *   S0  setup: new child, contributor invited, review period; extractor pinned
 *   S1  unverified AI-extracted records never reach longitudinal analytics
 *   S2  verify-as-written and correct both make a record analytics-eligible
 *   S3  a correction creates a new version; the original version and the
 *       source observation are preserved
 *   S4  insufficient evidence -> analytics withheld, not forced
 *   S5  the deterministic report names the withheld analysis, and its evidence
 *       is the corrected version, not the original
 *   S6  a contributor cannot reach professional pages, verify, correct,
 *       compute analytics or generate reports
 *
 * Requires the backend (EXTRACTION_PROVIDER=ollama, OLLAMA_MODEL=qwen2.5:7b,
 * REPORTING_MODE=deterministic) on :8000, the frontend on :3000 and the demo
 * users from scripts/seed_demo.py.
 *
 *   npx playwright test -c tests/phase6/e2e/governance.config.ts
 */

import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { test, expect, type Page } from "@playwright/test";

const API = process.env.API_URL || "http://localhost:8000";
const OLLAMA = process.env.OLLAMA_URL || "http://127.0.0.1:11434";
const EXPECTED_MODEL = "qwen2.5:7b";
const PASSWORD = "DemoPass123!";
const INTERVENTIONIST = "demo-interventionist@example.com";
const PARENT = "demo-parent@example.com";
const RECORD_DIR = path.resolve(__dirname, "../../../test-results/governance-e2e");

// Synthetic observations: invented for the API suite, no corpus-derived text.
const NOTES: { text: string; setting: string }[] = [
  { text: "At snack time the child pointed at the juice box and said 'juice please' without any help.", setting: "home" },
  { text: "When I held up two toys the child reached for the car after I modeled the word 'car'.", setting: "home" },
  { text: "During bath time the child handed me the cup and said 'more water' on his own.", setting: "home" },
  { text: "At the park the child waved and said 'hi' to a neighbour after I reminded him.", setting: "community" },
  { text: "At dinner the child asked for 'bread' by signing after I pointed to the basket.", setting: "home" },
];
const MIN_RECORDS = 3; // one verified, one corrected, one left unreviewed

// ─── Shared state across the serial scenarios ───────────────────

const run = {
  childName: `E2E Governance Child ${new Date().toISOString().slice(0, 16).replace("T", " ")}`,
  childId: "",
  records: [] as { id: string; status: string }[],
  verifiedId: "",
  correctedV1Id: "",
  correctedV2Id: "",
  unreviewedId: "",
  originalPrompt: "" as unknown,
  newPrompt: "",
  correctionReason: "Interventionist correction: prompt level misread.",
};
const facts: Record<string, unknown> = {};

// ─── Helpers ────────────────────────────────────────────────────

/** A caption bar along the bottom of the video, surviving page loads. */
async function installCaption(page: Page) {
  await page.addInitScript(() => {
    const draw = () => {
      const raw = sessionStorage.getItem("e2e-caption");
      if (!raw) return;
      const { title, step } = JSON.parse(raw);
      let el = document.getElementById("e2e-caption");
      if (!el) {
        el = document.createElement("div");
        el.id = "e2e-caption";
        Object.assign(el.style, {
          position: "fixed", left: "0", right: "0", bottom: "0", zIndex: "2147483647",
          background: "rgba(17,24,39,0.92)", color: "#fff", padding: "10px 18px",
          font: "15px/1.45 -apple-system, system-ui, sans-serif", pointerEvents: "none",
        });
        document.documentElement.appendChild(el);
      }
      el.replaceChildren();
      const t = document.createElement("div");
      t.style.fontWeight = "700";
      t.textContent = title;
      const s = document.createElement("div");
      s.textContent = step;
      el.append(t, s);
    };
    (window as unknown as { __e2eCaption: () => void }).__e2eCaption = draw;
    document.addEventListener("DOMContentLoaded", draw);
  });
}

async function caption(page: Page, title: string, step: string, holdMs = 1500) {
  await page.evaluate(([t, s]) => {
    sessionStorage.setItem("e2e-caption", JSON.stringify({ title: t, step: s }));
    (window as unknown as { __e2eCaption?: () => void }).__e2eCaption?.();
  }, [title, step]);
  await page.waitForTimeout(holdMs);
}

async function login(page: Page, email: string, landing: RegExp) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await page.waitForURL(landing, { timeout: 20_000 });
}

/** Call the backend from the page as the signed-in user (same token the UI uses). */
async function apiAs(page: Page, method: string, urlPath: string, body?: unknown) {
  return page.evaluate(
    async ([api, m, p, b]) => {
      const token = localStorage.getItem("auth_token");
      const res = await fetch(`${api}${p}`, {
        method: m as string,
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: b === undefined ? undefined : JSON.stringify(b),
      });
      let json: unknown = null;
      try { json = await res.json(); } catch { /* empty body */ }
      return { status: res.status, json: json as any };
    },
    [API, method, urlPath, body] as const,
  );
}

async function listRecords(page: Page) {
  await page.goto(`/children/${run.childId}/records`);
  await expect(page.getByRole("heading", { name: "Structured Records" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  return page.locator('a[href*="/records/"]').evaluateAll((as) =>
    as.map((a) => ({
      id: (a.getAttribute("href") || "").split("/records/")[1],
      text: (a as HTMLElement).innerText,
    })),
  );
}

async function openPeriodAnalytics(page: Page) {
  await page.goto(`/children/${run.childId}/analytics`);
  await page.locator('[data-testid^="period-"]').first().click();
  await expect(page.getByText("Data Adequacy Assessment")).toBeVisible({ timeout: 60_000 });
}

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await installCaption(page);
});

test.afterAll(() => {
  mkdirSync(RECORD_DIR, { recursive: true });
  const git = (cmd: string) => execSync(`git ${cmd}`, { encoding: "utf8" }).trim();
  writeFileSync(
    path.join(RECORD_DIR, "scenario-facts.json"),
    JSON.stringify({
      run: "Recorded UI governance end-to-end run",
      finished_utc: new Date().toISOString(),
      build: {
        commit: git("rev-parse HEAD"),
        branch: git("rev-parse --abbrev-ref HEAD"),
        working_tree_clean: git("status --porcelain --untracked-files=no") === "",
      },
      child: { name: run.childName, id: run.childId },
      scenarios: facts,
    }, null, 2),
  );
});

// ─── S0 ─────────────────────────────────────────────────────────

test("S0 · frozen configuration and fresh synthetic child", async ({ page, request }) => {
  const tags = await (await request.get(`${OLLAMA}/api/tags`)).json();
  const model = tags.models.find((m: { name: string }) => m.name === EXPECTED_MODEL);
  expect(model, `${EXPECTED_MODEL} must be served by Ollama`).toBeTruthy();
  const version = await (await request.get(`${OLLAMA}/api/version`)).json();
  facts.S0 = {
    extractor: {
      provider: "ollama", model: EXPECTED_MODEL, digest: String(model.digest).slice(0, 12),
      quantization: model.details?.quantization_level, parameter_size: model.details?.parameter_size,
      ollama_version: version.version,
    },
  };

  await login(page, INTERVENTIONIST, /\/dashboard/);
  await caption(page, "S0 · Setup", `Interventionist signs in. Extractor under test: ollama / ${EXPECTED_MODEL} (digest ${String(model.digest).slice(0, 12)}).`);

  await page.goto("/children");
  await caption(page, "S0 · Setup", "Create a fresh synthetic child so no prior records can leak into the scenarios.");
  await page.getByRole("button", { name: "Add Child" }).click();
  await page.getByLabel("Display Name").fill(run.childName);
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByText(run.childName).click();
  await page.waitForURL(/\/children\/[0-9a-f-]{36}/);
  run.childId = page.url().match(/\/children\/([0-9a-f-]{36})/)![1];

  await page.goto(`/children/${run.childId}/actors`);
  await caption(page, "S0 · Setup", "Invite the demo parent as a contributor for this child only.");
  await page.getByRole("button", { name: "Invite Contributor" }).click();
  await page.locator("main").getByLabel("Email").fill(PARENT);
  await page.getByLabel("Role").selectOption("parent");
  await page.getByRole("button", { name: "Send Invitation" }).click();
  await expect(page.getByText(PARENT).first()).toBeVisible();

  const start = new Date(Date.now() - 30 * 86_400_000).toISOString().slice(0, 10);
  const end = new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10);
  await page.goto(`/children/${run.childId}/analytics`);
  await caption(page, "S0 · Setup", `Create the review period ${start} → ${end}.`);
  await page.getByRole("button", { name: "Create Review Period" }).click();
  await page.getByLabel("Start Date").fill(start);
  await page.getByLabel("End Date").fill(end);
  await page.getByRole("button", { name: /Create & Compute/ }).click();
  await expect(page.getByText("Data Adequacy Assessment")).toBeVisible({ timeout: 60_000 });
  await caption(page, "S0 · Setup", "Baseline: no records yet, so analytics are already withheld.", 2500);
  facts.S0 = { ...(facts.S0 as object), child_id: run.childId, review_period: { start, end } };
});

// ─── S1 ─────────────────────────────────────────────────────────

test("S1a · contributor submits synthetic observations through the chat UI", async ({ page }) => {
  await login(page, PARENT, /\/contribute/);
  await caption(page, "S1 · Contributor submits observations", "The parent sees only their assigned child and a conversational form.");
  const card = page.locator("div").filter({ hasText: run.childName }).filter({ has: page.getByRole("link", { name: "New Observation" }) }).last();
  await card.getByRole("link", { name: "New Observation" }).click();
  await page.waitForURL(/\/observe/);

  const outcomes: { note: number; outcome: string; clarification_questions: string[] }[] = [];
  let finalized = 0;
  for (const [i, note] of NOTES.entries()) {
    if (finalized >= MIN_RECORDS + 1) break;
    await caption(page, "S1 · Contributor submits observations",
      `Note ${i + 1} (${note.setting}) goes to the live extractor, ${EXPECTED_MODEL}.`, 600);
    await page.getByLabel("What did you observe?").fill(note.text);
    await page.getByLabel("Setting").selectOption(note.setting);
    await page.getByRole("button", { name: "Submit Observation" }).click();

    const questions: string[] = [];
    let outcome = "";
    for (let turn = 0; turn < 6 && !outcome; turn++) {
      // A finalized observation flashes a thank-you and then moves the
      // contributor to their history, so arriving there is the success signal.
      const asked = page.getByText("Quick Question");
      const failed = page.getByText(/Observation processing failed|Failed to submit|Failed to finalize/);
      const state = async () =>
        /\/history/.test(page.url()) ? "finalized"
          : (await asked.isVisible()) ? "asked"
            : (await failed.isVisible()) ? "failed" : "";
      await expect.poll(state, { timeout: 300_000, intervals: [500] }).not.toBe("");
      const st = await state();
      if (st === "finalized") outcome = "finalized";
      else if (st === "failed") outcome = `failed: ${await failed.innerText()}`;
      else {
        const q = await page.locator(".bg-blue-50 p").first().innerText();
        questions.push(q);
        await caption(page, "S1 · Contributor submits observations",
          "The system asks a non-leading clarification question; the contributor skips it.", 2000);
        await page.getByRole("button", { name: "Skip" }).click();
        await expect.poll(async () => {
          const st = await state();
          if (st !== "asked") return true;
          return (await page.locator(".bg-blue-50 p").first().innerText().catch(() => q)) !== q;
        }, { timeout: 300_000, intervals: [500] }).toBe(true);
      }
    }
    outcomes.push({ note: i + 1, outcome: outcome || "unresolved", clarification_questions: questions });

    if (outcome === "finalized") {
      finalized++;
      // On completion the contributor is taken to their own history, which
      // must never show extraction output.
      await page.waitForURL(/\/contribute\/[0-9a-f-]{36}\/history/, { timeout: 20_000 });
      await expect(page.getByText(note.text).first()).toBeVisible();
      const body = await page.locator("main").innerText();
      for (const hidden of ["prompt_level", "Prompt level", EXPECTED_MODEL, "confidence", "Validated"]) {
        expect(body, `contributor view must not show "${hidden}"`).not.toContain(hidden);
      }
      await caption(page, "S1 · Contributor submits observations",
        "Accepted. The contributor sees their own note only: no structured fields, model or confidence.", 1500);
      await page.goto(`/contribute/${run.childId}/observe`);
    } else {
      await caption(page, "S1 · Contributor submits observations", `Not accepted by the pipeline (${outcome}).`, 2000);
      await page.getByRole("button", { name: "Try Again" }).click();
    }
  }
  facts.S1_submissions = outcomes;
  expect(finalized, `need at least ${MIN_RECORDS} finalized observations`).toBeGreaterThanOrEqual(MIN_RECORDS);
});

test("S1b · unverified AI-extracted records are blocked from analytics", async ({ page }) => {
  await login(page, INTERVENTIONIST, /\/dashboard/);
  const rows = await listRecords(page);
  await caption(page, "S1 · Unverified-block", `${rows.length} AI-extracted records exist; none has been professionally reviewed.`, 2500);
  run.records = rows.map((r) => ({ id: r.id, status: r.text.match(/Validated|Pending|Verified|Corrected|Rejected|Abstained/)?.[0] ?? "?" }));
  expect(run.records.length).toBeGreaterThanOrEqual(MIN_RECORDS);
  for (const r of run.records) expect(["Validated", "Pending"]).toContain(r.status);

  await page.goto(`/children/${run.childId}/records/${run.records[0].id}`);
  await expect(page.getByText(/excluded from longitudinal analytics until verified or corrected/)).toBeVisible();
  await expect(page.getByText(`Model: ${EXPECTED_MODEL}`)).toBeVisible();
  await caption(page, "S1 · Unverified-block", `Record detail: extracted by ${EXPECTED_MODEL}, marked as excluded from analytics until reviewed.`, 2500);

  const models = new Set<string>();
  for (const r of run.records) models.add((await apiAs(page, "GET", `/records/${r.id}`)).json.model);
  expect([...models]).toEqual([EXPECTED_MODEL]);

  await openPeriodAnalytics(page);
  await expect(page.getByText("INSUFFICIENT").first()).toBeVisible();
  await expect(page.getByText(/Only 0\/5 observations received/)).toBeVisible();
  await expect(page.getByText(/Analytics are withheld/).first()).toBeVisible();
  await caption(page, "S1 · Unverified-block",
    `Analytics admit 0 of ${run.records.length} records ("Only 0/5 observations received"), so they are withheld.`, 3000);
  facts.S1 = { records: run.records.length, statuses: run.records.map((r) => r.status.toLowerCase()),
               models: [...models], admitted_to_analytics: 0, adequacy: "insufficient" };
});

// ─── S2 ─────────────────────────────────────────────────────────

test("S2 · interventionist verifies one record and corrects another", async ({ page }) => {
  await login(page, INTERVENTIONIST, /\/dashboard/);
  const pending = run.records.find((r) => r.status === "Pending");
  const validated = run.records.filter((r) => r.status === "Validated");
  const verifyTarget = validated[0];
  const correctTarget = pending ?? validated[1];
  expect(verifyTarget, "a validated record to verify").toBeTruthy();
  expect(correctTarget, "a record to correct").toBeTruthy();
  run.verifiedId = verifyTarget.id;
  run.correctedV1Id = correctTarget.id;
  run.unreviewedId = run.records.find((r) => r.id !== verifyTarget.id && r.id !== correctTarget.id)!.id;

  // Verify as written.
  await page.goto(`/children/${run.childId}/records/${verifyTarget.id}`);
  await caption(page, "S2 · Verify", "Option 1: the interventionist accepts the extraction as written.");
  await page.getByRole("button", { name: "Verify as written" }).click();
  await expect(page.getByText("Verified", { exact: true })).toBeVisible();
  await expect(page.getByText(/included in longitudinal analytics/)).toBeVisible();
  await expect(page.getByText(/Verified by:/)).toBeVisible();
  await caption(page, "S2 · Verify", "Now VERIFIED, with reviewer and time recorded, and included in analytics. No new version was created.", 2500);

  // Correct.
  await page.goto(`/children/${run.childId}/records/${correctTarget.id}`);
  if (pending) {
    await expect(page.getByText(/cannot be accepted as written/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Verify as written" })).toHaveCount(0);
    await caption(page, "S2 · Correct", "This record was routed for review, so it cannot be accepted as written; only correction is offered.", 2500);
  }
  await caption(page, "S2 · Correct", "Option 2: the interventionist corrects the extraction.");
  await page.getByRole("button", { name: "Correct", exact: true }).click();
  const editor = page.locator("#record-data");
  const data = JSON.parse(await editor.inputValue());
  run.originalPrompt = data.prompt_level ?? null;
  run.newPrompt = data.prompt_level === "full_physical" ? "gestural" : "full_physical";
  data.prompt_level = run.newPrompt;
  await editor.fill(JSON.stringify(data, null, 2));
  await page.getByLabel("Correction Reason").fill(run.correctionReason);
  await caption(page, "S2 · Correct", `prompt_level: ${String(run.originalPrompt)} → ${run.newPrompt}, with a stated reason.`, 2000);
  await page.getByRole("button", { name: "Submit Correction" }).click();
  await expect(page.getByText("Version History")).toBeVisible();

  const rows = await listRecords(page);
  const v2 = rows.find((r) => /Corrected/.test(r.text));
  expect(v2, "corrected version listed").toBeTruthy();
  run.correctedV2Id = v2!.id;
  await caption(page, "S2 · Correct", "The correction is a new CORRECTED version (v2); the AI version stays as v1.", 2500);

  await openPeriodAnalytics(page);
  await expect(page.getByText(/Only 2\/5 observations received/)).toBeVisible();
  await caption(page, "S2 · Eligibility",
    `Analytics now admit exactly 2 records, the VERIFIED one and the CORRECTED one. The unreviewed record${run.records.length > 3 ? "s and the" : " and the"} superseded v1 stay out.`, 3500);

  const verified = (await apiAs(page, "GET", `/records/${run.verifiedId}`)).json;
  expect(verified.status).toBe("verified");
  expect(verified.version).toBe(1);
  facts.S2 = { verified: 1, corrected: 1, left_unreviewed: run.records.length - 2,
               pending_offered_correction_only: !!pending, admitted_to_analytics: 2 };
});

// ─── S3 ─────────────────────────────────────────────────────────

test("S3 · correction creates a new version; original and source are preserved", async ({ page }) => {
  await login(page, INTERVENTIONIST, /\/dashboard/);
  await page.goto(`/children/${run.childId}/records/${run.correctedV2Id}`);
  await expect(page.getByText("Corrected", { exact: true })).toBeVisible();
  await expect(page.getByText(`Reason: ${run.correctionReason}`)).toBeVisible();
  await expect(page.getByText("Version History")).toBeVisible();
  await caption(page, "S3 · Correction propagation", `v2 (CORRECTED) holds prompt_level = ${run.newPrompt}. Version history keeps v1 and v2.`, 3000);

  const v2 = (await apiAs(page, "GET", `/records/${run.correctedV2Id}`)).json;
  const v1 = (await apiAs(page, "GET", `/records/${run.correctedV1Id}`)).json;
  const history = (await apiAs(page, "GET", `/records/${run.correctedV2Id}/history`)).json;
  expect(v2.version).toBe(2);
  expect(v2.record_data.prompt_level).toBe(run.newPrompt);
  expect(v1.version).toBe(1);
  expect(v1.record_data.prompt_level ?? null).toEqual(run.originalPrompt);
  expect(history.map((h: { version: number }) => h.version)).toEqual([1, 2]);

  await page.goto(`/children/${run.childId}/records/${run.correctedV1Id}`);
  await caption(page, "S3 · Correction propagation", `The original AI version v1 is untouched (prompt_level = ${String(run.originalPrompt)}).`, 3000);

  const obs = (await apiAs(page, "GET", `/observations/${v1.observation_id}`)).json;
  expect(NOTES.map((n) => n.text)).toContain(obs.raw_text);
  await page.goto(`/children/${run.childId}/observations/${v1.observation_id}`);
  await expect(page.getByText(obs.raw_text)).toBeVisible();
  await caption(page, "S3 · Correction propagation", "The source observation text is preserved exactly as the contributor wrote it.", 3000);
  facts.S3 = { corrected_field: "prompt_level", original_value: run.originalPrompt, corrected_value: run.newPrompt,
               original_version_preserved: true, history_versions: [1, 2], source_text_unchanged: true,
               v1_status_after_correction: v1.status };
});

// ─── S4 ─────────────────────────────────────────────────────────

test("S4 · insufficient evidence: analytics are withheld, not forced", async ({ page }) => {
  await login(page, INTERVENTIONIST, /\/dashboard/);
  await openPeriodAnalytics(page);
  await expect(page.getByText("INSUFFICIENT").first()).toBeVisible();
  await expect(page.getByText(/Analytics are withheld because the available evidence does not meet/).first()).toBeVisible();
  await caption(page, "S4 · Insufficient evidence",
    "Two eligible records from one contributor fall below the adequacy thresholds, so the router withholds analytics and lists why.", 4000);

  const periods = (await apiAs(page, "GET", `/children/${run.childId}/review-periods`)).json;
  const a = (await apiAs(page, "POST", `/children/${run.childId}/analytics`, { review_period_id: periods[0].id })).json;
  const withheld = a.kpis.filter((k: { abstained: boolean }) => k.abstained);
  expect(a.adequacy.level).toMatch(/^(insufficient|limited)$/);
  expect(withheld.length).toBeGreaterThan(0);
  for (const k of withheld) {
    expect(k.value, `${k.name} withheld but valued`).toBeNull();
    expect(k.abstention_reason, `${k.name} withheld without reason`).toBeTruthy();
  }
  facts.S4 = { adequacy: a.adequacy.level, withheld: withheld.map((k: { name: string }) => k.name),
               produced: a.kpis.filter((k: { abstained: boolean }) => !k.abstained).map((k: { name: string }) => k.name),
               failed_checks: a.adequacy.checks.filter((c: { passed: boolean }) => !c.passed).map((c: { check: string }) => c.check) };
});

// ─── S5 ─────────────────────────────────────────────────────────

test("S5 · deterministic report preserves the withheld state and uses the corrected version", async ({ page }) => {
  await login(page, INTERVENTIONIST, /\/dashboard/);
  await page.goto(`/children/${run.childId}/reports`);
  await caption(page, "S5 · Reporting preservation", "Generate the operational report for the review period.");
  await page.getByRole("button", { name: "Generate Report" }).click();
  await page.locator('[data-testid^="report-period-"]').first().click();
  await page.getByRole("button", { name: "Generate", exact: true }).click();
  await page.locator(`a[href*="/children/${run.childId}/reports/"]`).first().click();
  await page.waitForURL(/\/reports\/[0-9a-f-]{36}/);
  const reportId = page.url().match(/\/reports\/([0-9a-f-]{36})/)![1];

  await expect(page.getByText(/Deterministic Evidence Summary/)).toBeVisible();
  await expect(page.locator("main").getByText(/All longitudinal analytics were withheld/).first()).toBeVisible();
  await caption(page, "S5 · Reporting preservation",
    "Deterministic report (no language model). It states explicitly that the analysis was withheld; it does not omit it.", 4000);

  await page.getByText(/Source Records/).scrollIntoViewIfNeeded();
  await expect(page.getByRole("link", { name: run.correctedV2Id })).toBeVisible();
  await expect(page.getByRole("link", { name: run.correctedV1Id })).toHaveCount(0);
  await expect(page.getByRole("link", { name: run.unreviewedId })).toHaveCount(0);
  await caption(page, "S5 · Correction propagation",
    "Report evidence cites the CORRECTED v2 and the VERIFIED record. The original v1 and unreviewed records are absent.", 4000);

  const report = (await apiAs(page, "GET", `/reports/${reportId}`)).json;
  const evidence = (await apiAs(page, "GET", `/reports/${reportId}/evidence`)).json;
  const periods = (await apiAs(page, "GET", `/children/${run.childId}/review-periods`)).json;
  const a = (await apiAs(page, "POST", `/children/${run.childId}/analytics`, { review_period_id: periods[0].id })).json;
  const withheld = a.kpis.filter((k: { abstained: boolean }) => k.abstained);
  // Each withheld analysis must be stated as withheld, with its reason, in
  // one sentence. Mentioning the evidence level alone does not count.
  const prose = report.sections.map((s: { body: string }) => s.body).join(" ").toLowerCase();
  const sentences = prose.split(/(?<=\.)\s+/).filter((x: string) => x.includes("withheld"));
  const named = withheld.filter((k: { abstention_reason: string }) =>
    sentences.some((x: string) => x.includes(String(k.abstention_reason).toLowerCase())));

  expect(report.provider).toBe("deterministic");
  expect(report.is_experimental).toBe(false);
  expect(report.validation_passed).toBe(true);
  expect(named.length).toBe(withheld.length);
  expect(new Set(evidence.record_ids)).toEqual(new Set([run.verifiedId, run.correctedV2Id]));
  facts.S5 = { report_provider: report.provider, is_experimental: report.is_experimental,
               validation_passed: report.validation_passed, withheld_named: named.length, withheld_total: withheld.length };
  facts.S3_reporting = { evidence_uses_corrected_version: true, original_version_excluded: true,
                         evidence_record_count: evidence.record_ids.length };
});

// ─── S6 ─────────────────────────────────────────────────────────

test("S6 · a contributor cannot verify or reach professional analytics", async ({ page }) => {
  await login(page, PARENT, /\/contribute/);
  await caption(page, "S6 · Authorization negative", "Signed in as the parent (contributor). Try the interventionist's pages directly.");

  await page.goto(`/children/${run.childId}/analytics`);
  await page.waitForURL(/\/contribute/, { timeout: 20_000 });
  await caption(page, "S6 · Authorization negative", "Analytics URL: redirected back to the contributor home.", 2000);
  await page.goto(`/children/${run.childId}/records/${run.unreviewedId}`);
  await page.waitForURL(/\/contribute/, { timeout: 20_000 });
  await caption(page, "S6 · Authorization negative", "Record review URL: redirected back to the contributor home.", 2000);

  const periods = await apiAs(page, "GET", `/children/${run.childId}/review-periods`);
  const reviewPeriodId = periods.status === 200 ? periods.json[0]?.id : "00000000-0000-0000-0000-000000000000";
  const attempts = {
    verify: (await apiAs(page, "POST", `/records/${run.unreviewedId}/verify`)).status,
    correct: (await apiAs(page, "POST", `/records/${run.unreviewedId}/correct`, { record_data: {}, correction_reason: "x" })).status,
    analytics: (await apiAs(page, "POST", `/children/${run.childId}/analytics`, { review_period_id: reviewPeriodId })).status,
    report: (await apiAs(page, "POST", `/children/${run.childId}/reports/generate`, { review_period_id: reviewPeriodId })).status,
    read_record: (await apiAs(page, "GET", `/records/${run.unreviewedId}`)).status,
  };
  await caption(page, "S6 · Authorization negative",
    `Direct API calls with the parent's own token: ${Object.entries(attempts).map(([k, v]) => `${k} → ${v}`).join(", ")}.`, 4000);
  for (const [action, status] of Object.entries(attempts)) expect(status, action).toBe(403);
  facts.S6 = { role: "parent", refused: attempts };
});

test("S6b · the refused verification left the record unreviewed", async ({ page }) => {
  await login(page, INTERVENTIONIST, /\/dashboard/);
  await page.goto(`/children/${run.childId}/records/${run.unreviewedId}`);
  await expect(page.getByText(/excluded from longitudinal analytics until verified or corrected/)).toBeVisible();
  const rec = (await apiAs(page, "GET", `/records/${run.unreviewedId}`)).json;
  expect(["validated", "pending"]).toContain(rec.status);
  expect(rec.verified_by ?? null).toBeNull();
  await caption(page, "S6 · Authorization negative", "Back as the interventionist: the record the parent tried to verify is still unreviewed and excluded.", 3500);
  facts.S6 = { ...(facts.S6 as object), record_unchanged: true };
});
