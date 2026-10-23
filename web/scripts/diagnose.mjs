// Load the served app in a browser and print console output, page errors and
// worker errors for 60 seconds. Usage: node scripts/diagnose.mjs [chromium|firefox|webkit]
import { chromium, firefox, webkit } from "@playwright/test";

const engines = { chromium, firefox, webkit };
setTimeout(() => { console.log("diagnose: giving up after 60s"); process.exit(2); }, 60_000).unref();
const browser = await engines[process.argv[2] ?? "chromium"].launch();
const page = await browser.newPage();
const t0 = Date.now();
const log = (...a) => console.log(`${((Date.now() - t0) / 1000).toFixed(1)}s`, ...a);
page.on("console", (m) => log("console", m.type(), m.text().slice(0, 300)));
page.on("pageerror", (e) => log("pageerror", e.message.slice(0, 300)));
page.on("requestfailed", (r) => log("requestfailed", r.url(), r.failure()?.errorText));
page.on("worker", (w) => {
  log("worker started", w.url());
  w.on("console", (m) => log("worker console", m.text().slice(0, 300)));
});
await page.addInitScript(() => {
  let last = performance.now();
  setInterval(() => {
    const now = performance.now();
    if (now - last > 1500) console.log(`heartbeat gap ${Math.round(now - last)}ms`);
    last = now;
  }, 500);
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) if (e.duration > 300) console.log(`longtask ${Math.round(e.duration)}ms at ${Math.round(e.startTime)}`);
  }).observe({ type: "longtask", buffered: true });
});
await page.goto(process.env.BASE ?? "http://localhost:4310/");
for (let i = 0; i < 20; i++) {
  await page.waitForTimeout(2000);
  const footer = await page.locator(".footer-meta").innerText().catch(() => "");
  const bar = await page.locator(".engine-bar").innerText().catch(() => "");
  log("footer:", footer.split("·")[0].trim(), "| bar:", bar.trim());
  if (/engine \d/.test(footer)) break;
}
await browser.close();
