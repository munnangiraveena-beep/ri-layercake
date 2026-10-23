import { expect, test, type Page } from "@playwright/test";

async function ready(page: Page) {
  await page.goto("/");
  await page.evaluate(() => localStorage.clear());
  await page.goto("/");
  await expect(page.locator(".footer-meta")).toContainText(/engine \d+\.\d+\.\d+/, { timeout: 90_000 });
  await expect(page.locator(".preview-badge")).toHaveCount(0);
}

test("add QS, XL and SL from the menu; stacked by default, then side by side", async ({ page }) => {
  await ready(page);
  const badges = page.locator(".layer-grid .kind-badge");
  const before = await badges.count();
  for (const name of ["Quota share", "Excess of loss layer", "Stop loss"]) {
    await page.getByRole("button", { name: "+ Add layer ▾" }).click();
    await page.getByRole("menuitem", { name: new RegExp(name) }).click();
    await expect(badges).toHaveCount(before + ["Quota share", "Excess of loss layer", "Stop loss"].indexOf(name) + 1);
  }
  await expect(page.locator(".canvas-svg rect.shape-qs")).toBeVisible();
  await expect(page.locator(".canvas-svg rect.shape-sl").first()).toBeVisible();
  const stacked = page.getByRole("checkbox", { name: "Stacked" });
  await expect(stacked).toBeChecked();
  await stacked.click(); // a controlled tick: it flips when the engine confirms
  await expect(page.locator(".canvas-svg")).toContainText("XL on the retained");
  await expect(stacked).not.toBeChecked();
});

test("per risk, portfolio and aggregate examples", async ({ page }) => {
  await ready(page);
  await page.getByRole("button", { name: /Try an example: a .* risk/ }).click();
  await expect(page.locator(".loss-table").first()).toBeVisible();
  await expect(page.locator(".loss-fill").first()).toBeAttached();

  await page.getByRole("tab", { name: "Portfolio" }).click();
  await page.getByRole("button", { name: "Try an example portfolio" }).click();
  await expect(page.getByText(/10 risks · total exposure/)).toBeVisible();

  await page.getByRole("tab", { name: "Annual aggregate" }).click();
  await page.getByRole("button", { name: /95% loss ratio year/ }).click();
  await expect(page.locator("#cover-h ~ dl.facts").first()).toContainText("Net loss ratio");
});

test("premium walk and live formulas", async ({ page }) => {
  await ready(page);
  await expect(page.locator(".walk-table")).toContainText("Margin");
  await expect(page.locator(".walk-table")).toContainText("Internal expenses");
  await page.locator("rect.shape-layer").first().click();
  const inspector = page.locator(".inspector");
  await expect(inspector).toContainText("Premium (RTE) = EPI (gross) × Adj. rate");
  await inspector.getByLabel(/Adj\. rate/).fill("3");
  await inspector.getByLabel(/Adj\. rate/).press("Enter");
  await expect(inspector).toContainText("£120m × 3%");
});

test("one programme with lines: variable QS, before and after RI, and the optimiser", async ({ page }) => {
  await ready(page);
  await page.getByLabel("Open a gallery tower").selectOption("credit_surety");
  const lines = page.getByRole("table", { name: "Lines of business" });
  await expect(lines.getByLabel("Credit QS cession")).toHaveValue("35");
  await expect(lines.getByLabel("Surety QS cession")).toHaveValue("15");
  const ba = page.getByRole("table", { name: "Before and after reinsurance" });
  await expect(ba).toContainText("Loss ratio");
  await page.getByRole("button", { name: "Open the optimiser" }).click();
  const compare = page.getByRole("table", { name: "No reinsurance, current programme and what-if" });
  await expect(compare).toContainText("Return on capital", { timeout: 60_000 });
  await expect(page.locator(".risk-best")).toContainText(/Best placeable/, { timeout: 60_000 });
  await expect(page.locator(".frontier svg circle.pt").first()).toBeVisible();
  await page.getByRole("button", { name: "Try it" }).click();
  await expect(compare).toContainText("What-if");
  await page.getByRole("button", { name: "Apply what-if to programme" }).click();
  await expect(lines.getByLabel("Credit QS cession")).not.toHaveValue("35");
});

test("light by default, theme switch remembered", async ({ page }) => {
  await page.goto("/formulas/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("radio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator(".fcard").first()).toContainText("Example");
});

test("contact page", async ({ page }) => {
  await page.goto("/contact/");
  await expect(page.getByRole("link", { name: "banu.munnangi@gmail.com" })).toHaveAttribute("href", "mailto:banu.munnangi@gmail.com");
  await expect(page.getByRole("link", { name: "banumunnangi.com" })).toHaveAttribute("href", "https://banumunnangi.com");
  await expect(page.locator(".contact-card")).toContainText("Banu Munnangi");
});

test("no jump on reload: the saved tower shows before the engine is ready", async ({ page }) => {
  await ready(page);
  await page.getByLabel("Open a gallery tower").selectOption("stop_loss");
  await expect(page.locator(".title-overlay.title")).toHaveValue("Stop loss on the net account");
  await page.reload();
  // Straight after reload, before the engine answers, the canvas already shows the saved tower.
  await expect(page.locator(".canvas-frame")).toContainText("Stop loss on the net account", { timeout: 3000 });
  await expect(page.locator(".footer-meta")).toContainText(/engine \d/, { timeout: 90_000 });
  await expect(page.locator(".title-overlay.title")).toHaveValue("Stop loss on the net account");
});
for (const path of ["/contact/"]) {
  test(`no serious accessibility violations on ${path}`, async ({ page }) => {
    const AxeBuilder = (await import("@axe-core/playwright")).default;
    await page.goto(path);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  });
}
