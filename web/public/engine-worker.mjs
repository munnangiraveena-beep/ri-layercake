// Engine worker: loads Pyodide and the exact ri_layercake wheel named in
// /py/manifest.json, then answers run(command, payload) messages with JSON.
// All parsing, maths, layout and export happen here, inside the browser.
import { loadPyodide } from "/py/pyodide.mjs";

let run = null;
const queue = [];

function progress(step, total, label) {
  postMessage({ type: "progress", step, total, label });
}

async function sha256(buf) {
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function boot() {
  const total = 5;
  progress(0, total, "Loading engine");
  const manifest = await (await fetch("/py/manifest.json", { cache: "no-cache" })).json();
  const pyodide = await loadPyodide({ indexURL: "/py/", fullStdLib: false });
  progress(1, total, "Loading lxml and Pillow");
  await pyodide.loadPackage(["lxml", "pillow", "typing-extensions"], { checkIntegrity: true });
  progress(2, total, "Loading python-pptx");
  const sitePackages = pyodide.runPython("import site; site.getsitepackages()[0]");
  const pure = manifest.wheels.filter((w) => w.endsWith("-none-any.whl") && !w.startsWith("typing_extensions"));
  for (const wheel of pure) {
    const want = manifest.files[wheel]?.sha256;
    if (!want) throw new Error(`${wheel} is missing from the manifest`);
    // The content hash in the URL means a rebuilt wheel with the same version is never served from an old cache.
    let buf = await (await fetch(`/py/${wheel}?sha=${want.slice(0, 16)}`)).arrayBuffer();
    if ((await sha256(buf)) !== want) {
      buf = await (await fetch(`/py/${wheel}?sha=${want.slice(0, 16)}`, { cache: "reload" })).arrayBuffer();
      if ((await sha256(buf)) !== want) throw new Error(`Integrity check failed for ${wheel}`);
    }
    pyodide.unpackArchive(buf, "wheel", { extractDir: sitePackages });
  }
  progress(3, total, "Starting engine");
  pyodide.runPython(`
import importlib, os
importlib.invalidate_caches()
os.makedirs("/home/pyodide/work", exist_ok=True)
os.chdir("/home/pyodide/work")
from ri_layercake.bridge import run as _run
`);
  run = pyodide.globals.get("_run");
  py = pyodide;
  progress(4, total, "Ready");
  postMessage({ type: "ready", version: manifest.version, pyodide: manifest.pyodide });
  while (queue.length) handle(queue.shift());
}

let py = null;
let chain = Promise.resolve();

function handle(msg) {
  // Calls run strictly in order; a notebook cell may first load packages it imports (pandas).
  chain = chain.then(async () => {
    const { id, command, payload } = msg;
    let result;
    try {
      // The risk view simulates with numpy, self-hosted and loaded the first time it is used.
      if (command === "risk") await py.loadPackage("numpy");
      if (command === "run_cell" && payload?.code) {
        await py.loadPackagesFromImports(payload.code);
        // tower.plot() and walk.plot() use matplotlib without importing it in the cell
        if (/\.plot\(|matplotlib/.test(payload.code)) await py.loadPackage("matplotlib");
      }
      result = JSON.parse(run(command, JSON.stringify(payload ?? {})));
    } catch (e) {
      result = { ok: false, error: String(e?.message || e) };
    }
    postMessage({ type: "result", id, result });
  });
}

onmessage = (event) => {
  if (run) handle(event.data);
  else queue.push(event.data);
};

boot().catch((e) => postMessage({ type: "failed", error: String(e?.message || e) }));
