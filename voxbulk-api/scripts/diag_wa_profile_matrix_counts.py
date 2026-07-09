#!/usr/bin/env python3
"""Compare scoped vs account WA template counts (Meta/Telnyx profile matrix).

Run on VPS:
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python scripts/diag_wa_profile_matrix_counts.py --service customer_feedback
  python scripts/diag_wa_profile_matrix_counts.py --service survey
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

META_99 = "b19c8d5b-2406-4bd0-8d56-610574ab491b"
TELNYX_55 = "26dbf487-5ef5-4f51-b51c-059201083cd9"


def main() -> int:
    parser = argparse.ArgumentParser(description="Diag scoped vs account profile matrix counts")
    parser.add_argument("--service", default="customer_feedback", help="survey | customer_feedback")
    parser.add_argument("--meta-id", default=META_99)
    parser.add_argument("--telnyx-id", default=TELNYX_55)
    parser.add_argument("--list-marketing-cfs", action="store_true", help="List cfs_* marketing on Meta")
    args = parser.parse_args()

    from app.core.database import get_sessionmaker
    from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService
    from app.services.wa_template_product_scope import filter_remote_for_service_code
    from app.services.wa_template_sync_profile import summarize_for_connection_profile

    service = str(args.service or "customer_feedback").strip()
    db = get_sessionmaker()()

    out: dict = {"service_code": service, "profiles": []}
    for label, pid in (("meta", args.meta_id), ("telnyx", args.telnyx_id)):
        summary = summarize_for_connection_profile(db, pid, service_code=service)
        out["profiles"].append({"label": label, "profile_id": pid, "result": summary})

    if args.list_marketing_cfs and service == "customer_feedback":
        all_r = TelnyxWhatsappTemplateSyncService.fetch_from_meta(
            db,
            connection_profile_id=args.meta_id,
            service_code=service,
        )
        cfs = filter_remote_for_service_code(all_r, service)
        mkt = [
            {"name": i.get("name"), "status": i.get("status"), "category": i.get("category")}
            for i in sorted(cfs, key=lambda x: str(x.get("name") or ""))
            if "MARKET" in str(i.get("category") or "").upper()
        ]
        out["cfs_marketing_on_meta"] = mkt

    print(json.dumps(out, indent=2))
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
