// Local static server for out/ that applies the same headers as vercel.json,
// including the full Content Security Policy. Usage: node scripts/serve.mjs [port]
import fs from "node:fs";
import http from "node:http";
import path from "node:path";

const web = path.join(import.meta.dirname, "..");
const root = path.join(web, "out");
const port = Number(process.argv[2] ?? process.env.PORT ?? 4310);
// Read on every request, so a rebuild's new script hashes apply without a restart.
function rules() {
  const vercel = JSON.parse(fs.readFileSync(path.join(web, "vercel.json"), "utf8"));
  return vercel.headers.map((r) => ({ re: new RegExp("^" + r.source.replace(/\(\.\*\)/g, "(.*)") + "$"), headers: r.headers }));
}
const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".woff": "font/woff",
  ".ttf": "font/ttf", ".wasm": "application/wasm", ".zip": "application/zip", ".whl": "application/zip",
};

http.createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  let rel = decodeURIComponent(url.pathname);
  let file = path.join(root, rel);
  if (!file.startsWith(root)) {
    res.writeHead(403).end();
    return;
  }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) {
    if (!rel.endsWith("/")) {
      res.writeHead(308, { Location: rel + "/" + url.search }).end();
      return;
    }
    file = path.join(file, "index.html");
  }
  const status = fs.existsSync(file) ? 200 : 404;
  if (status === 404) file = path.join(root, "404.html");
  for (const rule of rules()) if (rule.re.test(rel)) for (const h of rule.headers) res.setHeader(h.key, h.value);
  res.setHeader("Content-Type", TYPES[path.extname(file)] ?? "application/octet-stream");
  res.writeHead(status);
  fs.createReadStream(file).pipe(res);
}).listen(port, () => console.log(`Serving out/ at http://localhost:${port} with vercel.json headers`));
