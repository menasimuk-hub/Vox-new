"""Structural check: Smart Card / Expo token routes nest under layouts (not root)."""
from pathlib import Path
import re
import sys

rt = Path(__file__).resolve().parents[1] / "src" / "routeTree.gen.ts"
text = rt.read_text(encoding="utf-8")
errors = []

def must(cond, msg):
    if not cond:
        errors.append(msg)

must("ExpoRouteWithChildren" in text, "missing ExpoRouteWithChildren")
must("SmartCardRouteWithChildren" in text, "missing SmartCardRouteWithChildren")
must("getParentRoute: () => ExpoRoute" in text, "Expo token/index not parented to ExpoRoute")
must("getParentRoute: () => SmartCardRoute" in text, "Smart Card token/index not parented to SmartCardRoute")

# Token routes must NOT be root children
root_block = re.search(r"const rootRouteChildren[^{]+\{([^}]+)\}", text, re.S)
must(root_block is not None, "rootRouteChildren missing")
if root_block:
    body = root_block.group(1)
    must("ExpoTokenRoute" not in body, "ExpoTokenRoute still in rootRouteChildren")
    must("SmartCardTokenRoute" not in body, "SmartCardTokenRoute still in rootRouteChildren")
    must("ExpoRouteWithChildren" in body, "Expo layout missing from root")
    must("SmartCardRouteWithChildren" in body, "Smart Card layout missing from root")

must(Path(__file__).resolve().parents[1].joinpath("src/routes/smart-card.tsx").read_text(encoding="utf-8").count("Outlet") >= 1, "smart-card layout missing Outlet")
must(Path(__file__).resolve().parents[1].joinpath("src/routes/expo.tsx").read_text(encoding="utf-8").count("Outlet") >= 1, "expo layout missing Outlet")
must('createFileRoute("/smart-card/")' in Path(__file__).resolve().parents[1].joinpath("src/routes/smart-card.index.tsx").read_text(encoding="utf-8"), "smart-card index path wrong")
must('createFileRoute("/expo/")' in Path(__file__).resolve().parents[1].joinpath("src/routes/expo.index.tsx").read_text(encoding="utf-8"), "expo index path wrong")

if errors:
    print("FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("PASS: route nesting structure looks correct")
