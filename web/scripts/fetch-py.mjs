// Self-host Pyodide and every wheel the engine needs under public/py/, with a
// manifest of sha256 hashes. Run after building the ri_layercake wheel.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const root = import.meta.dirname;
const out = path.join(root, "..", "public", "py");
const pyodideDir = path.join(root, "..", "node_modules", "pyodide");
const lock = JSON.parse(fs.readFileSync(path.join(pyodideDir, "pyodide-lock.json"), "utf8"));
const version = JSON.parse(fs.readFileSync(path.join(pyodideDir, "package.json"), "utf8")).version;
const CDN = `https://cdn.jsdelivr.net/pyodide/v${version}/full/`;
const sha = (buf) => createHash("sha256").update(buf).digest("hex");
const sri = (buf) => "sha384-" + createHash("sha384").update(buf).digest("base64");

fs.mkdirSync(out, { recursive: true });

// Pyodide core
for (const f of ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]) {
  fs.copyFileSync(path.join(pyodideDir, f), path.join(out, f));
}

async function fetchTo(url, file) {
  const cached = path.join(pyodideDir, path.basename(file));
  let buf;
  if (fs.existsSync(cached)) buf = fs.readFileSync(cached);
  else {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url}: ${res.status}`);
    buf = Buffer.from(await res.arrayBuffer());
  }
  fs.writeFileSync(path.join(out, file), buf);
  return buf;
}

async function pypiWheel(name, version) {
  const meta = await (await fetch(`https://pypi.org/pypi/${name}/${version}/json`)).json();
  const whl = meta.urls.find((u) => u.filename.endsWith("-none-any.whl"));
  if (!whl) throw new Error(`No pure wheel for ${name} ${version}`);
  await fetchTo(whl.url, whl.filename);
  return whl.filename;
}

const wheels = [];
// Compiled packages from the Pyodide distribution, loaded at boot
for (const name of ["lxml", "pillow", "typing-extensions"]) {
  const pkg = lock.packages[name];
  await fetchTo(CDN + pkg.file_name, pkg.file_name);
  wheels.push(pkg.file_name);
}
// pandas and its dependencies: self-hosted, loaded only when a How to use cell imports it
const lazy = new Set();
const walk = (name) => {
  if (lazy.has(name)) return;
  lazy.add(name);
  for (const dep of lock.packages[name].depends) walk(dep);
};
walk("pandas");
walk("matplotlib");
for (const name of lazy) await fetchTo(CDN + lock.packages[name].file_name, lock.packages[name].file_name);
// Pure-Python dependencies from PyPI, pinned
wheels.push(await pypiWheel("python-pptx", "1.0.2"));
wheels.push(await pypiWheel("XlsxWriter", "3.2.3"));
wheels.push(await pypiWheel("openpyxl", "3.1.5"));
wheels.push(await pypiWheel("et_xmlfile", "2.0.0"));

// The engine wheel built from ../python
const dist = path.join(root, "..", "..", "python", "dist");
const engine = fs.readdirSync(dist).filter((f) => f.startsWith("ri_layercake-") && f.endsWith(".whl")).sort().pop();
if (!engine) throw new Error("Build the wheel first: (cd python && pip wheel --no-deps -w dist .)");
fs.copyFileSync(path.join(dist, engine), path.join(out, engine));
const engineVersion = engine.split("-")[1];

const files = {};
for (const f of fs.readdirSync(out)) {
  if (f === "manifest.json") continue;
  const buf = fs.readFileSync(path.join(out, f));
  files[f] = { sha256: sha(buf), integrity: sri(buf), bytes: buf.length };
}
const manifest = { version: engineVersion, wheel: engine, sha256: files[engine].sha256, pyodide: version, wheels: [...wheels, engine], files };
fs.writeFileSync(path.join(out, "manifest.json"), JSON.stringify(manifest, null, 2));
console.log(`public/py ready: engine ${engineVersion}, pyodide ${version}, ${Object.keys(files).length} files`);
