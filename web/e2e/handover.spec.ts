import { expect, test } from "@playwright/test";

test("Show code opens the tower's Python in How to use", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/engine \d+\.\d+\.\d+/)).toBeVisible({ timeout: 90_000 });
  await page.getByRole("button", { name: "Show code" }).click();
  await expect(page.locator(".code-panel pre code")).toContainText("Tower", { timeout: 30_000 });
  await page.getByRole("link", { name: "Open in How to use" }).click();
  await expect(page.getByRole("heading", { name: "From the Playground" })).toBeVisible({ timeout: 30_000 });
});

test("a link cannot put code into a notebook cell", async ({ page }) => {
  await page.goto("/how-to-use/#code=" + encodeURIComponent("print('from a link')"));
  await expect(page.locator(".nb-cell").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "From the Playground" })).toHaveCount(0);
  await expect(page.getByText("from a link")).toHaveCount(0);
});
