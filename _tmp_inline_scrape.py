from app.services.ai_team_service import AiTeamService
from app.core.database import get_sessionmaker

db = get_sessionmaker()()
out = AiTeamService.start_directory_scrape(
    db,
    expo_url="https://takeawayexpo.co.uk/exhibitors",
    follow_websites=False,
    wait=False,
    max_stands=500,
)
run = out.get("run") or {}
print("queued_via", out.get("queued_via"))
print("message", out.get("message"))
print("status", run.get("status"))
print("provider", run.get("provider") or out.get("provider"))
print("emails", out.get("emails_found") or run.get("emails_found") or run.get("item_count"))
db.close()
