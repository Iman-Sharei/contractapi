import { expect, test } from "@playwright/test";

// Same DB host rules as studio-wizard.spec.ts (Compose service `db`).
const DB_URL = process.env.E2E_DATABASE_URL || "postgresql://postgres:postgres@db:5432/app";
const STUDIO_KEY = process.env.STUDIO_API_KEY || "dev-studio-key-change-me";

test.describe("API page → editor → Use your API", () => {
  test("activate, get a key and working code, and see path errors inline", async ({ page }) => {
    const name = `e2e_ed_${Date.now().toString(36)}`;

    await page.goto("/login?next=/studio");
    await page.getByTestId("login-key").fill(STUDIO_KEY);
    await page.getByTestId("login-submit").click();
    await page.waitForURL(/\/studio$/);

    // Seed a contract through the signed-in BFF (same cookies as the page).
    const saved = await page.request.post("/api/studio/specs", {
      data: {
        name,
        spec: {
          database: { url: DB_URL },
          app: { title: "Editor e2e", read_only: true, auth: "api_key", api_prefix: "" },
          endpoints: [
            { name: "customers", path: "/customers", table: "customers", fields: ["id", "name"], filters: ["id"] },
          ],
        },
      },
    });
    expect(saved.ok(), await saved.text()).toBeTruthy();
    expect(await saved.text()).not.toContain("postgres:postgres@"); // password moved to secret store

    await page.goto(`/studio/${name}`);
    const panel = page.getByTestId("use-your-api");
    await expect(panel).toContainText("Activate this API");

    await page.getByRole("button", { name: "Activate saved" }).click();
    const url = panel.getByTestId("use-your-api-url");
    await expect(url).toContainText(`/apis/${name}/customers`, { timeout: 30_000 });
    await expect(panel.getByTestId("use-your-api-snippet")).toContainText("curl -s");

    await panel.getByRole("button", { name: "Create an API key for this code" }).click();
    const key = (await panel.getByTestId("use-your-api-key").textContent())?.trim() ?? "";
    expect(key).toMatch(/^dk_/);
    await expect(panel.getByTestId("use-your-api-snippet")).toContainText(key);

    // The code we show must actually work.
    const live = await page.request.get(`${(await url.textContent())?.trim()}?limit=1`, {
      headers: { "X-API-Key": key },
    });
    expect(live.status()).toBe(200);
    expect((await live.json()).items).toBeInstanceOf(Array);

    // Editor explains a bad URL path before the server rejects it.
    const pathInput = page.getByLabel("Path (URL)");
    await pathInput.fill("/Bad Path");
    await expect(page.getByText(/Use lowercase letters/)).toBeVisible();
  });
});
