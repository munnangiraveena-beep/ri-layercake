// After `next build`: hash every inline script in out/ and write a strict
// Content Security Policy to vercel.json; scripts/serve.mjs applies the same headers locally.
// Scripts run from this origin only, Pyodide gets wasm-unsafe-eval, and
// connect-src 'self' means programme data cannot be sent anywhere.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const web = path.join(import.meta.dirname, "..");
const out = path.join(web, "out");
const hashes = new Set();

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p);
    else if (entry.name.endsWith(".html")) {
      const html = fs.readFileSync(p, "utf8");
      for (const m of html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)) {
        if (m[1].trim()) hashes.add(`'sha256-${createHash("sha256").update(m[1]).digest("base64")}'`);
      }
    }
  }
}
walk(out);

const csp = [
  "default-src 'self'",
  `script-src 'self' 'wasm-unsafe-eval' ${[...hashes].sort().join(" ")}`,
  "worker-src 'self'",
  "connect-src 'self'",
  "img-src 'self' blob: data:",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self' data:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join("; ");

const security = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), interest-cohort=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const vercel = {
  $schema: "https://openapi.vercel.sh/vercel.json",
  outputDirectory: "out",
  trailingSlash: true,
  headers: [
    { source: "/(.*)", headers: security },
    { source: "/py/(.*)", headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }] },
    { source: "/py/manifest.json", headers: [{ key: "Cache-Control", value: "no-cache" }] },
    { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache" }] },
  ],
};
fs.writeFileSync(path.join(web, "vercel.json"), JSON.stringify(vercel, null, 2) + "\n");

console.log(`CSP written: ${hashes.size} inline script hashes`);
