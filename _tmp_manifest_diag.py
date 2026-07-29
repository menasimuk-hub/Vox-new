import json
from collections import Counter
from pathlib import Path

p = Path("/www/voxbulk/voxbulk-api/seed-data/wa-survey/migration-reports/marketing-utility-review/remaining-38-20260712/manifest.json")
m = json.loads(p.read_text(encoding="utf-8"))
items = [i for g in (m.get("groups") or []) for i in (g.get("items") or [])]
print("n", len(items))
print("status", Counter(i.get("status") for i in items))
print("lint_ok", Counter(i.get("lint_ok") for i in items))
print("rewritten", Counter(i.get("rewritten") for i in items))
print("skip", Counter(i.get("skip_reason") for i in items))
if items:
    print("sample0 keys", sorted(items[0].keys()))
    print("sample0", {k: items[0].get(k) for k in ["remote_name", "new_meta_name", "status", "lint_ok", "rewritten", "skip_reason", "delete_old_remote_name", "action"]})
print("status_counts", m.get("status_counts"))
