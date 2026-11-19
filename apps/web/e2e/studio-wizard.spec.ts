import { expect, test } from "@playwright/test";
import { removeApi } from "./cleanup";

// When the API runs in Docker Compose it must reach Postgres as hostname `db`.
// Override with E2E_DATABASE_URL for host-only API (localhost:5433).
const DB_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql://postgres:postgres@db:5432/app";
const API_BASE = process.env.API_BASE || "http://127.0.0.1:8000";
const DATA_KEY = process.env.DATA_API_KEYS || "dev-data-key";
const STUDIO_KEY = process.env.STUDIO_API_KEY || "dev-studio-key-change-me";

test.describe("Studio wizard → data plane", () => {
  const specName = `e2e_${Date.now().toString(36)}`;
  test.afterEach(async ({ page }) => removeApi(page.request, specName));

  test("sign in from the home page, connect, publish, then GET /apis/<name>/customers", async ({
    page,
    request,
  }) => {
    const health = await request.get(`${API_BASE}/health`);
    expect(health.ok(), `API health failed: ${health.status()}`).toBeTruthy();

    // Studio is login-protected: signed-out visitors land on /login (also from the home page link).
    await page.goto("/");
    await page.getByRole("link", { name: "Create an API", exact: true }).click();
    await page.waitForURL(/\/login/);
    await page.getByTestId("login-key").fill(STUDIO_KEY);
    await page.getByTestId("login-submit").click();
    await page.waitForURL((u) => u.pathname === "/studio/new");
    await expect(page.getByRole("heading", { name: "Create an API from your database" })).toBeVisible();

    await page.getByTestId("wizard-db-url-toggle").click();
    const dbInput = page.getByTestId("wizard-db-url");
    await dbInput.fill(DB_URL);
    await page.getByTestId("wizard-spec-name").fill(specName);
    await page.getByTestId("wizard-introspect").click();

    await expect(page.getByTestId("wizard-pick")).toBeVisible({ timeout: 60_000 });
    await page.getByTestId("wizard-pick-continue").click();

    await expect(page.getByTestId("wizard-guards")).toBeVisible();
    await page.getByTestId("wizard-save-activate").click();

    await page.waitForURL(new RegExp(`/studio/${specName}`), { timeout: 60_000 });
    await expect(page.getByTestId("api-status")).toHaveText("Live", { timeout: 30_000 });
    await expect(page.getByRole("status").first()).toContainText("Your API is live");

    // Poll the data plane at this API's own address (/apis/<name>)
    let lastStatus = 0;
    let body: unknown = null;
    for (let i = 0; i < 20; i++) {
      const res = await request.get(`${API_BASE}/apis/${specName}/customers?limit=1`, {
        headers: { "X-API-Key": DATA_KEY },
      });
      lastStatus = res.status();
      if (res.ok()) {
        body = await res.json();
        break;
      }
      await page.waitForTimeout(500);
    }
    expect(lastStatus, "GET /apis/<name>/customers after publish").toBe(200);
    expect(body).toMatchObject({ items: expect.any(Array) });
  });
});
