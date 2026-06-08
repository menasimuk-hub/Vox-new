#!/usr/bin/env python3
"""Post-deploy check: WA survey launch + interview use VoxBulk pricing (not legacy bundles)."""

from __future__ import annotations

import json
import sys
import urllib.request


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "https://api.voxbulk.com").rstrip("/")
    build = get(f"{base}/health/build")
    sha = str(build.get("git_sha") or "")
    print(f"API: {base}")
    print(f"git_sha: {sha} (need >= 92dfb28 for unified WA launch pricing)")

    expected_prefix = "92dfb28"
    if not sha.startswith(expected_prefix):
        print(f"FAIL: Production is on {sha}, not {expected_prefix}. Run VPS deploy:")
        print("  cd /www/voxbulk && VOX_GIT_BRANCH=fix/wa-interview-platform-templates ./deploy-vps.sh")
        return 1

    print("OK: Deploy SHA includes unified pricing migration.")
    print("")
    print("Manual checks after deploy (dashboard):")
    print("  1. PAYG WA survey, 1 contact -> Pay & launch shows 49p (not 10/15 GBP bundles)")
    print("  2. Package, 0 WA left -> Launch enabled; Extra recipients: 49p each")
    print("  3. Interview quote -> connection + minutes; Interview WhatsApp: included")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
