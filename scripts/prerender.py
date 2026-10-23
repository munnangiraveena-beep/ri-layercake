"""Write the pre-rendered gallery scene the Playground shows while the engine loads.

Usage: python scripts/prerender.py web/public/prerender/property_cat.json
"""

import json
import os
import sys

from ri_layercake import bridge

out = json.loads(bridge.run("gallery", json.dumps({"name": "per_risk_xol"})))
out.pop("ok")
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False)
print(f"{sys.argv[1]}: pre-rendered per_risk_xol")
