// Pyodide check for CI: install the self-hosted wheels in Node's Pyodide, run a
// core subset of the engine, and confirm the PPTX matches what CPython writes.
import fs from "node:fs";
import path from "node:path";
import { loadPyodide } from "pyodide";

const py = process.env.PY_DIR ?? path.join(process.cwd(), "public", "py");
const manifest = JSON.parse(fs.readFileSync(path.join(py, "manifest.json"), "utf8"));
const pyodide = await loadPyodide({ indexURL: py + "/" });
await pyodide.loadPackage(["lxml", "pillow", "typing-extensions", "numpy"]);
const site = pyodide.runPython("import site; site.getsitepackages()[0]");
for (const w of manifest.wheels.filter((w) => w.endsWith("-none-any.whl") && !w.startsWith("typing_extensions"))) {
  const buf = fs.readFileSync(path.join(py, w));
  // A Node Buffer can be a view into a shared pool; hand Pyodide its own bytes.
  const bytes = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  try {
    pyodide.unpackArchive(bytes, "wheel", { extractDir: site });
  } catch (e) {
    console.error(`unpack ${w} failed:`, e.name, e.errno ?? "", String(e.message ?? "").slice(0, 300));
    process.exit(1);
  }
}
let out;
try {
  out = pyodide.runPython(`
import json
from decimal import Decimal as D
import ri_layercake as lc
from ri_layercake import bridge, gallery

t = lc.Tower.from_text("10 ret, 40 xs 10, 50 xs 50 @ 75%")
r = t.drop_loss(75)
assert r.retained == D("16.25") * 10**6 and r.retained + r.recovered == 75 * 10**6
assert {d.code for d in gallery.load("gap_overlap").validate()} == {"gap", "overlap"}
assert lc.Tower.from_paste("Limit\\tExcess\\n40\\t10\\n50\\t50\\n").to_text() == "£40m xs 10, 50 xs 50"
res = json.loads(bridge.run("export", json.dumps({"tower": gallery.load("property_cat").to_dict()})))
assert res["ok"], res
risk = json.loads(bridge.run("risk", json.dumps({"tower": gallery.load("credit_surety").to_dict(),
                                                  "settings": {"sims": 4000}})))
assert risk["ok"], risk  # 32-bit numpy in the browser: index types must be the platform's
data = gallery.load("property_cat").to_pptx(deterministic=True)
data.hex()
`);
} catch (e) {
  console.error(String(e.message ?? e).split("\n").slice(-12).join("\n"));
  process.exit(1);
}
const expected = process.env.EXPECTED_PPTX;
if (expected && Buffer.from(out, "hex").compare(fs.readFileSync(expected)) !== 0) {
  console.error("Pyodide PPTX differs from CPython");
  process.exit(1);
}
console.log(`Pyodide ${manifest.pyodide}: engine ${manifest.version} core subset passed`);
