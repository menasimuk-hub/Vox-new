from app.core.database import get_sessionmaker
from app.models.ai_team_apify_run import AiTeamApifyRun
from sqlalchemy import select
import json

db = get_sessionmaker()()
rows = db.execute(select(AiTeamApifyRun).order_by(AiTeamApifyRun.created_at.desc()).limit(12)).scalars().all()
for r in rows:
    try:
        d = json.loads(r.stats_json or "{}")
    except Exception:
        d = {}
    print(
        r.status,
        "items",
        r.item_count,
        "prov",
        d.get("provider"),
        "emails",
        d.get("emails_found"),
        "stands",
        d.get("stands_found"),
        (r.expo_url or "")[:70],
    )
db.close()
