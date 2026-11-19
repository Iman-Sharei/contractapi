import { expect, test } from "@playwright/test";
import { removeApi } from "./cleanup";

// Same DB host rules as studio-wizard.spec.ts (Compose service `db`).
const DB_URL = process.env.E2E_DATABASE_URL || "postgresql://postgres:postgres@db:5432/app";
const STUDIO_KEY = process.env.STUDIO_API_KEY || "dev-studio-key-change-me";

test.describe("API page → editor → Use your API", () => {
  const name = `e2e_ed_${Date.now().toString(36)}`;
  test.afterEach(async ({ page }) => removeApi(page.request, name));

  test("make live, get a key and working code, stop only this API, see path errors inline", async ({
    page,
  }) => {

    await page.goto("/login?next=/studio");
    // First-run help: the key is shown only while the server uses the public demo default.
    if (STUDIO_KEY === "dev-studio-key-change-me") {
      await expect(page.getByTestId("login-demo-hint")).toContainText(STUDIO_KEY);
    } else {
      await expect(page.getByTestId("login-key-hint")).toBeVisible();
      await expect(page.locator("body")).not.toContainText(STUDIO_KEY);
    }
    await page.getByTestId("login-key").fill(STUDIO_KEY);
    await page.getByTestId("login-submit").click();
    // Match the pathname: the login URL itself ends with "?next=/studio".
    await page.waitForURL((u) => u.pathname === "/studio");

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
    await expect(page.getByTestId("api-status")).toHaveText("Draft — not running");
    await expect(panel).toContainText("Make this API live");

    await page.getByRole("button", { name: "Make live", exact: true }).click();
    await expect(page.getByTestId("api-status")).toHaveText("Live", { timeout: 30_000 });
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
    // Next-page links keep the /apis/<name> mount (callers can follow them as-is).
    const link = live.headers()["link"] ?? "";
    if (link) expect(link).toContain(`/apis/${name}/customers`);

    // Interactive docs load this API's own schema.
    const docs = await page.request.get(`${(await url.textContent())?.trim().replace(/\/customers$/, "")}/openapi.json`);
    expect(docs.status()).toBe(200);

    // A key is required: no key → 401, not data.
    const anon = await page.request.get(`${(await url.textContent())?.trim()}?limit=1`);
    expect(anon.status()).toBe(401);

    // Editor explains a bad URL path before the server rejects it.
    const pathInput = page.getByLabel("Address (URL path)");
    // Wait until the editor finished loading the saved spec, or the load overwrites our edit.
    await expect(pathInput).toHaveValue("/customers", { timeout: 30_000 });
    await pathInput.fill("/Bad Path");
    await expect(page.getByText(/Use lowercase letters/)).toBeVisible();

    // Stop affects only this API; other live APIs keep running.
    const before = (await (await page.request.get("/api/studio/active/list")).json()) as { apis: { name: string }[] };
    page.once("dialog", (d) => d.accept());
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    await expect(page.getByTestId("api-status")).toHaveText("Draft — not running", { timeout: 30_000 });
    const after = (await (await page.request.get("/api/studio/active/list")).json()) as { apis: { name: string }[] };
    expect(after.apis.map((a) => a.name).sort()).toEqual(
      before.apis.map((a) => a.name).filter((n) => n !== name).sort(),
    );
  });
});
