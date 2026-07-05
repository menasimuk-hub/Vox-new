#!/usr/bin/env python3
"""Regenerate docs/COMMAND-LIST.md and docs/COMMAND-LIST.html from repo scripts.

Run from repo root:
  python scripts/generate-command-list.py

After HTML is updated, regenerate PDF (Windows):
  powershell scripts/regenerate-command-list-pdf.ps1
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT_MD = DOCS / "COMMAND-LIST.md"
OUT_HTML = DOCS / "COMMAND-LIST.html"

ROOT_SHELL = {
    "deploy-vps.sh": ("Full deploy (pull, migrate, build, restart)", "./deploy-vps.sh"),
    "vox.sh": ("VPS service control", "./vox.sh start|stop|restart|status|update"),
    "delete-salesman.sh": (
        "Delete salesman + org + ALL data (by email)",
        "./delete-salesman.sh EMAIL [--yes]",
    ),
    "seed-sales-demo.sh": (
        "Seed full salesman demo workspace (interviews, surveys, feedback QR)",
        "./seed-sales-demo.sh EMAIL [--reset]",
    ),
}

REPO_SCRIPTS_META = {
    "verify-billing-deploy.sh": ("Billing post-deploy health", "bash scripts/verify-billing-deploy.sh"),
    "vps-finance-smoke.sh": ("Finance release smoke", "bash scripts/vps-finance-smoke.sh"),
    "vps-verify-deploy.sh": ("General deploy verify", "bash scripts/vps-verify-deploy.sh"),
    "vps-verify-dashboard.sh": ("Dashboard wwwroot verify", "bash scripts/vps-verify-dashboard.sh"),
    "vps-sync-dashboard.sh": ("Rsync dashboard to wwwroot", "bash scripts/vps-sync-dashboard.sh"),
    "vps-sync-all-ui.sh": ("Sync all UI builds to wwwroot", "bash scripts/vps-sync-all-ui.sh"),
    "vps-update-ui.sh": ("Rebuild UI only", "bash scripts/vps-update-ui.sh"),
    "vps-setup-celery.sh": ("Install Celery worker + beat on VPS", "sudo bash scripts/vps-setup-celery.sh"),
    "vps-recover-api.sh": ("Recover crashed API", "bash scripts/vps-recover-api.sh"),
    "vps-fix-database-env.sh": ("Fix DB env on VPS", "bash scripts/vps-fix-database-env.sh"),
    "vps-check-auth-env.sh": ("Check auth env vars", "bash scripts/vps-check-auth-env.sh"),
    "vps-workflow-smoke.sh": ("Workflow smoke (API + UI)", "bash scripts/vps-workflow-smoke.sh"),
    "vps-test-wa-survey-create.sh": ("WA survey create test", "bash scripts/vps-test-wa-survey-create.sh"),
    "vps-deploy-production.sh": ("Production deploy variant", "bash scripts/vps-deploy-production.sh"),
    "vps-deploy-f290115-verify.sh": ("Legacy deploy verify", "bash scripts/vps-deploy-f290115-verify.sh"),
    "vps-finish-rollback-deploy.sh": ("Finish rollback deploy", "bash scripts/vps-finish-rollback-deploy.sh"),
    "vps-install-microsoft-well-known-nginx.sh": (
        "Microsoft well-known nginx",
        "bash scripts/vps-install-microsoft-well-known-nginx.sh",
    ),
    "retry-pending-voice-notes.sh": ("Retry pending voice notes", "bash scripts/retry-pending-voice-notes.sh"),
    "run-celery-worker.sh": ("Local Celery worker", "bash scripts/run-celery-worker.sh"),
    "run-celery-beat.sh": ("Local Celery beat", "bash scripts/run-celery-beat.sh"),
    "dev-api.mjs": ("Start API (npm hook)", "npm run dev:api"),
    "frontend-smoke.mjs": ("Frontend smoke", "npm run smoke:frontend"),
    "sync-brand-assets.mjs": ("Sync brand logos (prebuild hook)", "auto via npm prebuild"),
    "write-dashboard-build-info.mjs": ("Dashboard build metadata", "auto via npm prebuild"),
    "write-admin-build-info.mjs": ("Admin build metadata", "auto via npm prebuild"),
    "verify-unified-pricing.py": ("Pricing sanity check", "python scripts/verify-unified-pricing.py"),
    "verify_wa_survey_local.py": ("Local WA survey verify", "python scripts/verify_wa_survey_local.py"),
    "e2e_local_test.ps1": ("Windows local e2e", "powershell scripts/e2e_local_test.ps1"),
    "_vps_deploy.py": ("Internal deploy helper", "used by deploy scripts"),
    "_vps_ats_check.py": ("VPS ATS check", "python scripts/_vps_ats_check.py"),
    "_vps_ats_check2.py": ("VPS ATS check v2", "python scripts/_vps_ats_check2.py"),
    "generate-command-list.py": (
        "Regenerate this command list (MD + HTML)",
        "python scripts/generate-command-list.py",
    ),
    "regenerate-command-list-pdf.ps1": (
        "Regenerate COMMAND-LIST.pdf from HTML",
        "powershell scripts/regenerate-command-list-pdf.ps1",
    ),
}

FEEDBACK_META = {
    "push_all_feedback_to_meta_overnight.py": (
        "Overnight batch push: all Customer Feedback industries to Meta (safe rate limits)",
        "python -u scripts/push_all_feedback_to_meta_overnight.py --batch-size 5 --delay-sec 15",
    ),
    "push_feedback_industry_to_telnyx.py": (
        "Push all Customer Feedback templates for ONE industry to Meta (no batch delay)",
        "python scripts/push_feedback_industry_to_telnyx.py --industry-slug fitness",
    ),
    "push_feedback_template_to_telnyx.py": (
        "Push one Customer Feedback template to Meta",
        "python scripts/push_feedback_template_to_telnyx.py --help",
    ),
    "seed_feedback_industry_from_md.py": (
        "Import Customer Feedback templates from Markdown (+ optional batched Meta push)",
        "python scripts/seed_feedback_industry_from_md.py --industry fitness --md PATH --dry-run",
    ),
}

SEED_META = {
    "seed_sales_demo.py": (
        "Salesman workspace demo (20 interviews, WA + phone surveys, feedback QR)",
        "python -m scripts.seed_sales_demo --email EMAIL [--reset]",
    ),
    "seed_demo_user_account.py": (
        "Rich demo for any dashboard user (wallet debits, 3 campaigns)",
        "python scripts/seed_demo_user_account.py --email EMAIL --clear --auto-top-up",
    ),
    "seed_demo_all_dashboard_services.py": (
        "Enable all dashboard menu modules for an org",
        "python scripts/seed_demo_all_dashboard_services.py --email EMAIL",
    ),
    "seed_demo_appointments.py": ("Demo CRM appointments", "python scripts/seed_demo_appointments.py --help"),
    "seed_demo_booking_link.py": ("Demo public booking link", "python scripts/seed_demo_booking_link.py --help"),
    "seed_demo_survey_hubspot.py": (
        "HubSpot sync demo surveys",
        "python scripts/seed_demo_survey_hubspot.py --help",
    ),
    "seed_demo_survey_mixed.py": (
        "Mixed WA + AI phone survey demo data",
        "python scripts/seed_demo_survey_mixed.py --help",
    ),
    "seed_dummy_survey.py": ("Dummy completed AI-call survey", "python scripts/seed_dummy_survey.py --help"),
    "seed_dummy_interview.py": ("Dummy interview UI test data", "python scripts/seed_dummy_interview.py --help"),
    "seed_sales_ai_survey_agent.py": (
        "Sales AI survey demo agent (used by seed-sales-demo.sh)",
        "python scripts/seed_sales_ai_survey_agent.py",
    ),
    "seed_feedback_responses_mixed.py": (
        "Feedback QR results (happy/unhappy mix)",
        "python scripts/seed_feedback_responses_mixed.py --help",
    ),
    "seed_hubspot_appointment_test_data.py": (
        "HubSpot appointment test data",
        "python scripts/seed_hubspot_appointment_test_data.py --help",
    ),
    "seed_appointment_wa_survey_test_data.py": (
        "Appointment + WA survey E2E test data",
        "python scripts/seed_appointment_wa_survey_test_data.py --help",
    ),
    "seed_wa_survey_from_md.py": (
        "WA survey types from Markdown file",
        "python scripts/seed_wa_survey_from_md.py --help",
    ),
    "seed_wa_survey_all_industries_from_md.py": (
        "All WA industries from master MD",
        "python scripts/seed_wa_survey_all_industries_from_md.py --help",
    ),
    "seed_wa_survey_industries.py": (
        "WA survey industries + tags",
        "python scripts/seed_wa_survey_industries.py --help",
    ),
    "seed_wa_survey_test_pack.py": (
        "WA survey test pack (no OpenAI)",
        "python scripts/seed_wa_survey_test_pack.py --help",
    ),
    "seed_feedback_industry_from_md.py": (
        "Import Customer Feedback industry templates from Markdown (+ optional Meta push)",
        "python scripts/seed_feedback_industry_from_md.py --industry fitness --md seed-data/customer-feedback/fitness-gyms-20lang.md --dry-run",
    ),
    "seed_interview_regional_agents.py": (
        "12 regional interview voice agents",
        "python scripts/seed_interview_regional_agents.py",
    ),
    "seed_interview_gb_leo.py": (
        "Legacy wrapper for regional agents",
        "python scripts/seed_interview_gb_leo.py",
    ),
    "seed_interview_ar_sultan_agent.py": (
        "Gulf Arabic interview agent Sultan",
        "python scripts/seed_interview_ar_sultan_agent.py",
    ),
    "seed_interview_ar_jammal_agent.py": (
        "Egyptian Arabic agent Jammal",
        "python scripts/seed_interview_ar_jammal_agent.py",
    ),
    "seed_appointment_gb_agents.py": (
        "GB appointment voice agents",
        "python scripts/seed_appointment_gb_agents.py",
    ),
    "seed_survey_gb_agents.py": ("GB phone survey voice agents", "python scripts/seed_survey_gb_agents.py"),
}

CATEGORY_ORDER = [
    "Root shell wrappers",
    "Delete user",
    "Seed / demo data",
    "Deploy & VPS (scripts/)",
    "Billing / finance",
    "Test / smoke",
    "WhatsApp / Telnyx",
    "Interview / voice",
    "Customer feedback",
    "Diagnose",
    "Repair / cleanup",
    "Database",
    "Ops / utilities",
    "Frontend build hooks",
]


def first_docstring(path: Path) -> str | None:
    if path.suffix != ".py":
        return None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return None
    doc = ast.get_docstring(tree)
    if not doc:
        return None
    line = doc.strip().splitlines()[0].strip()
    return line[:120] if line else None


def default_cmd(rel: str) -> str:
    if rel.startswith("voxbulk-api/scripts/") and rel.endswith(".py"):
        name = Path(rel).stem
        if name.startswith("seed_"):
            return f"python scripts/{Path(rel).name} --help"
        return f"python scripts/{Path(rel).name} --help"
    if rel.endswith(".sh"):
        return f"bash {rel}"
    return "see file"


def categorize_api_script(name: str) -> str:
    if name.startswith("seed_"):
        return "Seed / demo data"
    if name in ("delete_salesman.py", "purge_user_billing_and_accounts.py"):
        return "Delete user"
    if name.startswith("diagnose_") or name.startswith("diagnose"):
        return "Diagnose"
    if (
        "backfill" in name
        or name.startswith("repair_")
        or name.startswith("fix_")
        or name.startswith("cleanup_")
        or name.startswith("clear_")
    ):
        return "Repair / cleanup"
    if "finance" in name or "billing" in name or name.startswith("purge_"):
        return "Billing / finance"
    if name.startswith(("test_", "e2e_", "send_", "workflow", "verify_")):
        return "Test / smoke"
    if "telnyx" in name or "wa_" in name or name.startswith("push_") or "template" in name:
        return "WhatsApp / Telnyx"
    if "interview" in name or "voice" in name:
        return "Interview / voice"
    if "feedback" in name:
        return "Customer feedback"
    if name.startswith(("bootstrap", "local_mysql", "setup-local")):
        return "Database"
    return "Ops / utilities"


def discover_entries() -> list[tuple[str, str, str, str]]:
    entries: list[tuple[str, str, str, str]] = []

    for fname, (title, cmd) in ROOT_SHELL.items():
        rel = fname.replace("\\", "/")
        entries.append(("Root shell wrappers", rel, title, cmd))

    for path in sorted((ROOT / "scripts").rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".sh", ".ps1", ".mjs", ".py"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel == "scripts/lib/vps-git-sync.sh":
            entries.append(
                ("Deploy & VPS (scripts/)", rel, "Git sync helper (sourced by deploy)", "internal")
            )
            continue
        base = path.name
        title, cmd = REPO_SCRIPTS_META.get(base, (first_docstring(path) or base, default_cmd(rel)))
        entries.append(("Deploy & VPS (scripts/)", rel, title, cmd))

    for path in sorted((ROOT / "voxbulk-api" / "scripts").iterdir()):
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".sh", ".sql"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        name = path.name
        cat = categorize_api_script(name)
        if name in SEED_META:
            title, cmd = SEED_META[name]
        elif name == "delete_salesman.py":
            title, cmd = (
                "Delete salesman + org (Python; see delete-salesman.sh)",
                "python -m scripts.delete_salesman --email EMAIL [--yes]",
            )
        elif name == "purge_user_billing_and_accounts.py":
            title, cmd = (
                "Purge billing + hard-delete by user UUID",
                "python scripts/purge_user_billing_and_accounts.py --apply --confirm PURGE_TEST_USERS ...",
            )
        elif name in FEEDBACK_META:
            title, cmd = FEEDBACK_META[name]
        else:
            title = first_docstring(path) or name.replace("_", " ").replace(".py", "").replace(".sh", "")
            cmd = default_cmd(rel)
        entries.append((cat, rel, title, cmd))

    for rel, title, cmd in [
        (
            "voxbulk.com/frontend/scripts/fix-preview-server.mjs",
            "Fix Vite preview host check (voxbulk.com allowedHosts)",
            "node voxbulk.com/frontend/scripts/fix-preview-server.mjs",
        ),
        (
            "dashboard.voxbulk.com/dashboard-web/scripts/sync-integration-logos.mjs",
            "Sync integration logos (dashboard prebuild hook)",
            "auto via npm prebuild",
        ),
    ]:
        if (ROOT / rel).is_file():
            entries.append(("Frontend build hooks", rel, title, cmd))

    return entries


def build_feedback_meta_sync_section_md() -> str:
    return """## CUSTOMER FEEDBACK → META SYNC (VPS)

Push ~400 language rows per industry (~2,800 total across 7 industries) to Meta/Telnyx in **small batches** to avoid rate limits.

All commands run from **`voxbulk-api/`** with venv active.

### 1) Import templates from Markdown (optional — if not done in Admin)

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate

# Dry-run first
python scripts/seed_feedback_industry_from_md.py \\
  --industry fitness \\
  --md seed-data/customer-feedback/fitness-gyms-20lang.md \\
  --dry-run

# Import only (no Meta push)
python scripts/seed_feedback_industry_from_md.py \\
  --industry fitness \\
  --md seed-data/customer-feedback/fitness-gyms-20lang.md

# Import + push one industry (batched, 15s delay)
python scripts/seed_feedback_industry_from_md.py \\
  --industry fitness \\
  --md seed-data/customer-feedback/fitness-gyms-20lang.md \\
  --push --push-batch-size 5 --push-delay-sec 15
```

### 2) Push all industries overnight (~3 hours) — recommended

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate

# Dry-run (validate payloads, no Meta POST)
python -u scripts/push_all_feedback_to_meta_overnight.py --dry-run --industry-slug fitness

# Full run in background (use -u so log updates immediately)
nohup python -u scripts/push_all_feedback_to_meta_overnight.py \\
  --batch-size 5 --delay-sec 15 --industry-delay-sec 45 \\
  --no-resume \\
  > /tmp/cf-meta-push.log 2>&1 &

echo $!   # note PID
```

### 3) Monitor while running

```bash
# Live log (should show new batch lines every ~20–60 sec)
tail -f /tmp/cf-meta-push.log

# Process still alive?
ps -p PID -o pid,etime,cmd

# Progress state file (offset increases each batch)
cat seed-data/customer-feedback/push-reports/push_all_feedback_state.json

# Reports folder (from inside voxbulk-api/)
ls -lt seed-data/customer-feedback/push-reports/
```

**Working:** log shows `=== Customer Feedback -> Meta overnight push ===`, then `batch 1 offset=0`, then `Pushed batch 1–5 of 400…`.

**Resume after interrupt:**

```bash
python -u scripts/push_all_feedback_to_meta_overnight.py --resume
```

### 4) Push one industry only (foreground)

```bash
python -u scripts/push_all_feedback_to_meta_overnight.py \\
  --industry-slug restaurant --batch-size 5 --delay-sec 15
```

### 5) Push one industry — fast (no batch delays, use with care)

```bash
python scripts/push_feedback_industry_to_telnyx.py --industry-slug fitness
python scripts/push_feedback_industry_to_telnyx.py --industry-slug fitness --dry-run
```

### 6) When finished

```bash
tail -30 /tmp/cf-meta-push.log
# Expect: DONE | Industries completed: 7/7 | Failed: 0
cat seed-data/customer-feedback/push-reports/push-all-feedback-*.json
```

Check **Admin → Customer Feedback → industry → Sync status**, or **WhatsApp Manager** for names prefixed `voxbulk_cf_`.

### 7) System templates — local vs Meta sync (Survey + Feedback)

In **Admin → WA Templates → Survey or Feedback tab → System templates**:

| Mode | Behaviour |
|------|-----------|
| **Keep local** (default) | Admin draft/body is source of truth; **Sync** pushes local → Meta; pull updates status only |
| **Sync from Meta** | **Pull all from Meta** imports approved body/buttons into local; sends route from Meta mirror |

API (optional):

```bash
# Survey
curl -X PATCH .../admin/wa-survey/system-templates/routing -d '{"template_source":"meta_sync"}'
curl -X POST .../admin/wa-survey/system-templates/pull-from-meta

# Feedback
curl -X PATCH .../admin/customer-feedback/system-templates/routing -d '{"template_source":"local"}'
curl -X POST .../admin/customer-feedback/system-templates/pull-from-meta
```
"""


def build_seed_section_md() -> str:
    return """## SEED / DEMO DATA (start here)

All seed scripts run from **`voxbulk-api/`** with the project venv active unless noted.

### Quick start — full salesman demo (VPS)

```bash
cd /www/voxbulk
./seed-sales-demo.sh salesman1@voxbulk.com          # seed
./seed-sales-demo.sh salesman1@voxbulk.com --reset  # wipe + re-seed
```

### Quick start — rich demo for any dashboard user

```bash
cd /www/voxbulk/voxbulk-api
source .venv/bin/activate
python scripts/seed_demo_user_account.py --email user@example.com --clear --auto-top-up
```

**Windows (local):**

```powershell
cd c:\\Users\\zaghlol\\Downloads\\voxbulk.com\\voxbulk-api
.\\.venv\\Scripts\\Activate.ps1
python scripts/seed_demo_user_account.py --email user@example.com --clear --auto-top-up
```

### Enable all dashboard modules

```bash
python scripts/seed_demo_all_dashboard_services.py --email user@example.com
```

See the **full seed script table** below for every `seed_*` script.
"""


def build_delete_section_md() -> str:
    return """## DELETE USER COMPLETELY (IRREVERSIBLE)

### A) Salesman + org + all data (by email) — easiest

| | |
|---|---|
| **Shell wrapper** | `delete-salesman.sh` |
| **Python** | `voxbulk-api/scripts/delete_salesman.py` |

**VPS:**
```bash
cd /www/voxbulk
./delete-salesman.sh user@example.com          # dry run
./delete-salesman.sh user@example.com --yes    # DELETE EVERYTHING
```

**Windows:**
```powershell
cd c:\\Users\\zaghlol\\Downloads\\voxbulk.com\\voxbulk-api
.\\.venv\\Scripts\\Activate.ps1
python -m scripts.delete_salesman --email user@example.com
python -m scripts.delete_salesman --email user@example.com --yes
```

### B) Purge billing + hard-delete by user UUID

**Script:** `voxbulk-api/scripts/purge_user_billing_and_accounts.py`

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
python scripts/purge_user_billing_and_accounts.py --dry-run --user-id UUID --delete-users --delete-solo-orgs
python scripts/purge_user_billing_and_accounts.py --apply --confirm PURGE_TEST_USERS --user-id UUID --delete-users --delete-solo-orgs
```
"""


def render_md(entries: list[tuple[str, str, str, str]]) -> str:
    today = date.today().isoformat()
    by_cat: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for cat, rel, title, cmd in entries:
        by_cat[cat].append((rel, title, cmd))

    lines = [
        "# VoxBulk command list",
        "",
        f"**Generated:** {today} · **Total scripts:** {len(entries)}",
        "",
        "**Local repo:** `c:\\Users\\zaghlol\\Downloads\\voxbulk.com`",
        "**VPS repo:** `/www/voxbulk`",
        "",
        "> **Keep this list updated:** when you add or rename an ops script, run:",
        "> ```bash",
        "> python scripts/generate-command-list.py",
        "> powershell scripts/regenerate-command-list-pdf.ps1   # Windows PDF",
        "> ```",
        "",
        "**Colored printable version:** `docs/COMMAND-LIST.html` → Print → Save as PDF",
        "",
        "---",
        "",
        build_delete_section_md(),
        "",
        "---",
        "",
        build_seed_section_md(),
        "",
        "---",
        "",
        build_feedback_meta_sync_section_md(),
        "",
        "---",
        "",
        "## TEST NEW BILLING (Stripe / Airwallex / GoCardless)",
        "",
        "```bash",
        "cd /www/voxbulk && git pull origin main && ./deploy-vps.sh",
        "bash scripts/verify-billing-deploy.sh",
        "```",
        "",
        "```powershell",
        "cd voxbulk-api",
        "pytest tests/test_card_subscription_checkout.py tests/test_stripe_subscription_renewal.py \\",
        "  tests/test_airwallex_subscription_renewal.py tests/test_card_renewal_lifecycle.py tests/test_card_plan_change.py -q",
        "```",
        "",
        "---",
        "",
        "## ALL SCRIPTS (complete inventory)",
        "",
    ]

    for cat in CATEGORY_ORDER:
        items = by_cat.get(cat)
        if not items:
            continue
        lines.append(f"### {cat} ({len(items)})")
        lines.append("")
        lines.append("| Path | Description | Example command |")
        lines.append("|------|-------------|-----------------|")
        for rel, title, cmd in sorted(items, key=lambda x: x[0].lower()):
            title = title.replace("|", "\\|")
            lines.append(f"| `{rel}` | {title} | `{cmd}` |")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## LOCAL DEV (Windows)",
            "",
            "```powershell",
            "cd c:\\Users\\zaghlol\\Downloads\\voxbulk.com",
            "npm run dev              # API + public + admin",
            "npm run dev:api",
            "",
            "cd voxbulk-api",
            ".\\.venv\\Scripts\\Activate.ps1",
            "alembic upgrade head",
            "uvicorn main:app --reload --host 0.0.0.0 --port 8000",
            "",
            "cd dashboard.voxbulk.com\\dashboard-web",
            "npm run dev              # port 5175",
            "```",
            "",
            "## GIT",
            "",
            "```bash",
            "git pull origin main",
            "git push origin main",
            "```",
            "",
            "Remote: `https://github.com/menasimuk-hub/Vox-new.git` branch `main`",
            "",
        ]
    )
    return "\n".join(lines)


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_html(entries: list[tuple[str, str, str, str]], md_body_sections: str) -> str:
    today = date.today().isoformat()
    by_cat: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for cat, rel, title, cmd in entries:
        by_cat[cat].append((rel, title, cmd))

    cat_blocks = []
    colors = {
        "Root shell wrappers": "#1e40af",
        "Delete user": "#b91c1c",
        "Seed / demo data": "#047857",
        "Deploy & VPS (scripts/)": "#7c3aed",
        "Billing / finance": "#c2410c",
        "Test / smoke": "#0369a1",
        "WhatsApp / Telnyx": "#0d9488",
        "Interview / voice": "#9333ea",
        "Customer feedback": "#ca8a04",
        "Diagnose": "#64748b",
        "Repair / cleanup": "#dc2626",
        "Database": "#2563eb",
        "Ops / utilities": "#475569",
        "Frontend build hooks": "#0891b2",
    }

    for cat in CATEGORY_ORDER:
        items = by_cat.get(cat)
        if not items:
            continue
        color = colors.get(cat, "#334155")
        rows = []
        for rel, title, cmd in sorted(items, key=lambda x: x[0].lower()):
            rows.append(
                f"<tr><td><code>{esc(rel)}</code></td>"
                f"<td>{esc(title)}</td>"
                f"<td><code>{esc(cmd)}</code></td></tr>"
            )
        cat_blocks.append(
            f'<section class="cat"><h2 style="border-color:{color}">{esc(cat)} ({len(items)})</h2>'
            f'<table><thead><tr><th>Path</th><th>Description</th><th>Example command</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></section>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>VoxBulk Command List</title>
<style>
  body {{ font-family: Segoe UI, system-ui, sans-serif; margin: 2rem; color: #0f172a; line-height: 1.45; }}
  h1 {{ color: #1e3a8a; }}
  .meta {{ background: #f1f5f9; padding: 1rem 1.25rem; border-radius: 8px; margin-bottom: 1.5rem; }}
  .seed-box {{ background: #ecfdf5; border: 2px solid #059669; padding: 1rem 1.25rem; border-radius: 8px; margin: 1rem 0; }}
  .feedback-sync-box {{ background: #fffbeb; border: 2px solid #ca8a04; padding: 1rem 1.25rem; border-radius: 8px; margin: 1rem 0; }}
  .delete-box {{ background: #fef2f2; border: 2px solid #dc2626; padding: 1rem 1.25rem; border-radius: 8px; margin: 1rem 0; }}
  pre {{ background: #1e293b; color: #e2e8f0; padding: 1rem; border-radius: 6px; overflow-x: auto; font-size: 0.9rem; }}
  code {{ font-family: Consolas, monospace; font-size: 0.88em; }}
  table {{ width: 100%; border-collapse: collapse; margin: 0.5rem 0 1.5rem; font-size: 0.85rem; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 0.4rem 0.55rem; text-align: left; vertical-align: top; }}
  th {{ background: #e2e8f0; }}
  tr:nth-child(even) {{ background: #f8fafc; }}
  .cat h2 {{ border-left: 6px solid; padding-left: 0.6rem; margin-top: 2rem; }}
  @media print {{ body {{ margin: 1cm; }} .cat {{ break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>VoxBulk command list</h1>
<div class="meta">
  <strong>Generated:</strong> {today} &nbsp;|&nbsp; <strong>Total scripts:</strong> {len(entries)}<br/>
  <strong>Regenerate:</strong> <code>python scripts/generate-command-list.py</code> then
  <code>powershell scripts/regenerate-command-list-pdf.ps1</code>
</div>

<div class="delete-box">
<h2>Delete user completely</h2>
<pre>cd /www/voxbulk
./delete-salesman.sh user@example.com          # dry run
./delete-salesman.sh user@example.com --yes    # DELETE</pre>
</div>

<div class="seed-box">
<h2>Seed / demo data (most common)</h2>
<pre>cd /www/voxbulk
./seed-sales-demo.sh salesman1@voxbulk.com [--reset]

cd voxbulk-api && source .venv/bin/activate
python scripts/seed_demo_user_account.py --email user@example.com --clear --auto-top-up
python scripts/seed_demo_all_dashboard_services.py --email user@example.com</pre>
</div>

<div class="feedback-sync-box">
<h2>Customer Feedback → Meta sync (overnight)</h2>
<pre>cd /www/voxbulk/voxbulk-api && source .venv/bin/activate

# Dry-run one industry
python -u scripts/push_all_feedback_to_meta_overnight.py --dry-run --industry-slug fitness

# Full overnight run (~3h) — use python -u for live nohup log
nohup python -u scripts/push_all_feedback_to_meta_overnight.py \\
  --batch-size 5 --delay-sec 15 --industry-delay-sec 45 --no-resume \\
  > /tmp/cf-meta-push.log 2>&1 &amp;

# Monitor
tail -f /tmp/cf-meta-push.log
ps -p PID -o pid,etime,cmd
cat seed-data/customer-feedback/push-reports/push_all_feedback_state.json

# Resume if stopped
python -u scripts/push_all_feedback_to_meta_overnight.py --resume</pre>
</div>

<h2>Complete script inventory</h2>
{''.join(cat_blocks)}
</body>
</html>
"""


def main() -> None:
    entries = discover_entries()
    DOCS.mkdir(parents=True, exist_ok=True)
    md = render_md(entries)
    OUT_MD.write_text(md, encoding="utf-8")
    html = render_html(entries, md)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_MD} ({len(entries)} scripts)")
    print(f"Wrote {OUT_HTML}")


if __name__ == "__main__":
    main()
