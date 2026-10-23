import { expect, test } from "@playwright/test";

test("engine boots under CSP, draws the tower and exports a PPTX", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (m) => (m.type() === "error" ? problems.push(m.text()) : undefined));
  page.on("pageerror", (e) => problems.push(e.message));
  await page.goto("/");
  await expect(page.getByText(/engine \d+\.\d+\.\d+/)).toBeVisible({ timeout: 90_000 });
  await expect(page.locator(".canvas-svg rect.shape-layer").first()).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PowerPoint" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.pptx$/);
  expect(problems.filter((p) => /Content Security Policy|Refused/.test(p))).toEqual([]);
});
