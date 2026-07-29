"""Quick Meta account marketing count for CF leftovers."""
from __future__ import annotations

from collections import Counter

from app.core.database import get_sessionmaker
from app.services.survey_wa_utility_rewrite_service import discover_remote_marketing_templates
from app.services.wa_template_profile_push_service import WaTemplateProfilePushService
from app.services.wa_template_sync_profile import summarize_for_connection_profile

db = get_sessionmaker()()
try:
    pid = WaTemplateProfilePushService.resolve_primary_connection_profile_id(db, service_code="survey")
    summary = summarize_for_connection_profile(db, pid, service_code="survey")
    s = summary.get("summary") or {}
    print("profile_label:", summary.get("profile_label"))
    print("scoped_marketing:", s.get("marketing"))
    print("account_marketing:", (s.get("account") or {}).get("marketing"))
    print("account_utility:", (s.get("account") or {}).get("utility"))
    print("account_total:", (s.get("account") or {}).get("total"))
    overview, candidates = discover_remote_marketing_templates(db, name_contains="cfs_")
    print("unique_remote_marketing_cfs:", overview.get("unique_remote_marketing"))
    print("actionable:", overview.get("actionable_local_matches"))
    print("by_product:", overview.get("by_product"))
    cats = Counter()
    names = []
    for c in candidates:
        names.append(c.get("remote_name"))
        cats[str(c.get("category") or "?")] += 1
    print("candidate_categories:", dict(cats))
    print("remaining_names:")
    for n in sorted(x for x in names if x):
        print(" ", n)
finally:
    db.close()
