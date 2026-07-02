# WA UTILITY migration — VPS runbook

WABA ID: `1033532842963987` (verify with `python scripts/verify_wa_utility_waba.py`)

## Before phase 1

```bash
cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
python scripts/export_wa_template_baseline.py
bash scripts/run_wa_utility_migration_phase.sh 0
```

## Phases (OpenAI rewrite → save → push)

| Phase | Scope |
|-------|--------|
| 1 | WA Survey EN — 5 industries (~125 templates) |
| 2 | WA Survey EN — 5 industries (~125) |
| 3 | WA Survey EN — 4 industries (~100) |
| 4 | Feedback EN+AR (7 industries) + Interview EN (4) |

```bash
# Preview
python scripts/migrate_wa_templates_utility.py --phase 1 --dry-run --json

# Save + push + dedup
python scripts/migrate_wa_templates_utility.py --phase 1 --save --push --dedup --audit

# Phase 4 (feedback + interview + Arabic)
python scripts/migrate_wa_templates_utility.py --phase 4 --save --push --translate-ar --dedup --audit
```

Or: `bash scripts/run_wa_utility_migration_phase.sh N --save --push --dedup`

Reports: `seed-data/wa-survey/migration-reports/migration-phaseN-*.json`

## Audit / dedup only

```bash
python scripts/audit_wa_template_db.py --json
python scripts/audit_wa_template_db.py --dedup --dry-run
python scripts/audit_wa_template_db.py --dedup
```
