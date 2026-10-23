import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function ready(page: Page) {
  await page.goto("/");
  await page.evaluate(() => localStorage.clear());
  await page.goto("/");
  await expect(page.locator(".footer-meta")).toContainText(/engine \d+\.\d+\.\d+/, { timeout: 90_000 });
  await expect(page.locator(".preview-badge")).toHaveCount(0);
}

const layerCount = (page: Page) => page.locator(".layer-grid tbody tr").count();

test("paste an Excel block anywhere replaces the layers", async ({ page }) => {
  await ready(page);
  await page.locator("body").click({ position: { x: 5, y: 300 } });
  await page.evaluate(() => {
    // Firefox ignores clipboardData on synthetic events, so attach it explicitly.
    const dt = new DataTransfer();
    dt.setData("text/plain", "Limit\tExcess\t% Placed\n40\t10\t100%\n50\t50\t75%\n");
    const event = new Event("paste", { bubbles: true, cancelable: true });
    Object.defineProperty(event, "clipboardData", { value: dt });
    document.body.dispatchEvent(event);
  });
  await expect(page.locator(".mapping")).toBeVisible();
  await expect.poll(() => layerCount(page)).toBe(2);
  await expect(page.locator("#shorthand")).toHaveValue(/40 xs 10, 50 xs 50 @ 75%/);
});

test("drag a top edge changes the limit, and undo restores it", async ({ page }) => {
  await ready(page);
  await page.locator("#shorthand").fill("10 ret, 40 xs 10, 50 xs 50");
  await expect.poll(() => layerCount(page)).toBe(3);
  await expect(page.locator(".preview-badge")).toHaveCount(0);
  const block = page.locator("rect.shape-layer").last(); // top layer, 50 xs 50
  const box = (await block.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 1);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y - 40, { steps: 8 });
  await expect(page.locator(".value-tag")).toBeVisible();
  await page.mouse.up();
  await expect(page.locator("#shorthand")).not.toHaveValue("epi £120m, 10 ret, 40 xs 10, 50 xs 50");
  await page.keyboard.press("Control+z");
  await expect(page.locator("#shorthand")).toHaveValue("epi £120m, 10 ret, 40 xs 10, 50 xs 50");
});

test("split from the context menu, then drop a loss", async ({ page }) => {
  await ready(page);
  await page.locator("#shorthand").fill("10 ret, 40 xs 10, 100 xs 50");
  await expect.poll(() => layerCount(page)).toBe(3);
  const block = page.locator("rect.shape-layer").last();
  await block.click({ button: "right" });
  await page.getByRole("menuitem", { name: /Split here/ }).click();
  await expect.poll(() => layerCount(page)).toBe(4);

  await page.getByRole("textbox", { name: "Loss amount" }).fill("75");
  await expect(page.locator(".loss-table")).toBeVisible();
  await expect(page.locator(".loss-table")).toContainText("exhausted");
  await expect(page.locator(".loss-fill").first()).toBeAttached();
});

test("export downloads a PowerPoint file", async ({ page }) => {
  await ready(page);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PowerPoint" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("property-per-risk-xol-2027.pptx");
  const path = await file.path();
  const fs = await import("node:fs");
  expect(fs.readFileSync(path!).subarray(0, 2).toString()).toBe("PK");
});

test("keyboard only: select a layer and change its limit", async ({ page }) => {
  await ready(page);
  await page.locator("#shorthand").fill("40 xs 10, 50 xs 50");
  await expect.poll(() => layerCount(page)).toBe(2);
  await expect(page.locator("rect.shape-layer")).toHaveCount(2);
  await page.locator(".canvas-svg").focus();
  await expect(page.locator("#shorthand")).toHaveValue("epi £120m, 40 xs 10, 50 xs 50");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Shift+ArrowUp");
  await expect(page.locator("#shorthand")).toHaveValue("epi £120m, 40 xs 10, 52.5 xs 50");
  await expect(page.locator(".playground > [role=status]")).toContainText(/limit set to/);
});

test("no network requests while editing or exporting", async ({ page }) => {
  await ready(page);
  const requests: string[] = [];
  page.on("request", (r) => requests.push(r.url()));
  await page.locator("#shorthand").fill("10 ret, 40 xs 10, 50 xs 50 @ 75%");
  await expect.poll(() => layerCount(page)).toBe(3);
  await page.getByRole("radio", { name: "Linear" }).click();
  await page.getByRole("textbox", { name: "Loss amount" }).fill("60");
  await expect(page.locator(".loss-table")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PowerPoint" }).click();
  await download;
  expect(requests.filter((u) => !u.startsWith("blob:") && !u.startsWith("data:"))).toEqual([]);
});

for (const path of ["/", "/how-to-use/", "/formulas/"]) {
  test(`no serious accessibility violations on ${path}`, async ({ page }) => {
    if (path === "/") await ready(page);
    else await page.goto(path);
    await page.waitForTimeout(500);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`)).toEqual([]);
  });
}

test("How to use: a cell runs in the browser", async ({ page }) => {
  await page.goto("/how-to-use/");
  await expect(page.locator(".nb-cell").first()).toBeVisible();
  await expect(page.getByRole("status").first()).toContainText(/ready/, { timeout: 90_000 });
  const first = page.locator(".nb-cell").first();
  await first.getByRole("button", { name: "Run cell" }).click();
  await expect(first.locator(".count")).toHaveText("[1]");
  await expect(first.locator(".nb-outputs svg")).toBeVisible();
  await first.getByRole("button", { name: "Open in Playground" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator(".title-overlay.title")).toHaveValue("Property cat 2027");
});
