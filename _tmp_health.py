import json, urllib.request
req = urllib.request.Request("http://127.0.0.1:8000/health/build", headers={"Host": "api.voxbulk.com"})
with urllib.request.urlopen(req, timeout=15) as r:
    d = json.load(r)
print(d.get("git_sha"), d.get("built_at"), d.get("app_version", "")[:80])
