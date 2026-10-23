// Measure seconds from navigation to "engine ready", measured inside the page.
// Usage: BASE=http://localhost:4310/ node scripts/time-to-ready.mjs [chromium|firefox|webkit]
import { chromium, firefox, webkit } from "@playwright/test";

setTimeout(() => { console.log("time-to-ready: gave up after 150s"); process.exit(2); }, 150_000).unref();
const engines = { chromium, firefox, webkit };
const name = process.argv[2] ?? "chromium";
const browser = await engines[name].launch();
const page = await browser.newPage();
page.on("pageerror", (e) => console.log("pageerror", e.message.slice(0, 200)));
await page.goto(process.env.BASE ?? "http://localhost:4310/");
const seconds = await page.evaluate(() => new Promise((resolve) => {
  const check = () => {
    const footer = document.querySelector(".footer-meta")?.textContent ?? "";
    const failed = document.querySelector(".engine-bar.failed")?.textContent;
    if (failed) resolve(`failed: ${failed.slice(0, 300)}`);
    else if (/engine \d/.test(footer) && document.querySelector("rect.shape-layer")) resolve((performance.now() / 1000).toFixed(1));
    else setTimeout(check, 100);
  };
  check();
}));
console.log(name, "ready after", seconds, "s");
await browser.close();
