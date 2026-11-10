import { expect, test } from "@playwright/test";

const DB_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql://postgres:postgres@127.0.0.1:5433/app";
const API_BASE = process.env.API_BASE || "http://127.0.0.1:8000";
const DATA_KEY = process.env.DATA_API_KEYS || "dev-data-key";

test.describe("Studio wizard → data plane", () => {
  test("introspect, save & activate, then GET /data/customers", async ({
    page,
    request,
  }) => {
    const health = await request.get(`${API_BASE}/health`);
    expect(health.ok(), `API health failed: ${health.status()}`).toBeTruthy();

    const specName = `e2e_${Date.now().toString(36)}`;

    await page.goto("/studio/new");
    await expect(page.getByRole("heading", { name: "New API" })).toBeVisible();

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

    // Poll data plane until activate is live (empty prefix → /data/customers)
    let lastStatus = 0;
    let body: unknown = null;
    for (let i = 0; i < 20; i++) {
      const res = await request.get(`${API_BASE}/data/customers?limit=1`, {
        headers: { "X-API-Key": DATA_KEY },
      });
      lastStatus = res.status();
      if (res.ok()) {
        body = await res.json();
        break;
      }
      await page.waitForTimeout(500);
    }
    expect(lastStatus, "GET /data/customers after activate").toBe(200);
    expect(body).toMatchObject({ items: expect.any(Array) });
  });
});
