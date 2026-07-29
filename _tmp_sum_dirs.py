import json
d = json.load(open("/tmp/exhibition_dirs.json", encoding="utf-8"))
print("KNOWN", len(d["known"]))
for n, u in d["known"]:
    print(f"K|{n}|{u}")
print("FOUND")
for x in d["found"]:
    b = x.get("best") or {}
    print(f"F|{x['name']}|{b.get('score')}|{b.get('url')}")
