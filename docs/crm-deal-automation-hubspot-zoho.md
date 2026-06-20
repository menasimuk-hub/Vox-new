# CRM deal-stage survey automation — HubSpot & Zoho

**Date:** 2026-06-20  
**Branch:** `main`  
**Commit:** `3dca55b` — `feat(crm): HubSpot and Zoho deal-stage survey automation`  
**Scope:** Extend Pipedrive deal-stage automation to HubSpot CRM and Zoho CRM.

---

## Summary

Survey campaigns can poll the connected CRM every **15 minutes**, detect deals in selected pipeline stages, wait a configurable delay, then send the survey on the campaign channel (WhatsApp or AI call). One send per deal per campaign (deduped).

Previously this worked for **Pipedrive only**. It now supports **HubSpot** and **Zoho CRM** with the same dashboard UI (`crm-survey-automation-card` on survey launch steps).

---

## Provider parity

| Capability | Pipedrive | HubSpot | Zoho CRM |
|------------|-----------|---------|----------|
| List deal stages | ✅ | ✅ | ✅ |
| Poll deals in selected stages | ✅ | ✅ | ✅ |
| Contact phone resolution | ✅ | ✅ | ✅ |
| Dry-run test (launch wizard) | ✅ | ✅ | ✅ |
| Celery poll + due send dispatch | ✅ | ✅ | ✅ |
| Dedupe (1× per deal per order) | ✅ | ✅ | ✅ |
| DD subscription gate (not PAYG) | ✅ | ✅ | ✅ |

---

## Files changed

| File | Change |
|------|--------|
| `voxbulk-api/app/services/crm_deal_survey_automation_service.py` | HubSpot/Zoho stage listing, deal fetch, contact resolution; shared `_fetch_deals_for_stages` router |
| `voxbulk-api/app/services/hubspot_connection_service.py` | OAuth scopes: `crm.objects.deals.read`, `crm.schemas.deals.read` |
| `voxbulk-api/tests/test_crm_deal_survey_automation.py` | 11 tests (HubSpot/Zoho list, dry-run, poll disconnect) |

---

## API (unchanged routes)

- `GET /service-orders/crm/deal-stages` — stages for active CRM
- `GET|PATCH /service-orders/{order_id}/crm-automation` — config + status
- `POST /service-orders/{order_id}/crm-automation/test` — dry-run preview

Celery beat: `crm.poll_deal_survey_automation` every **900s** (15 min).

---

## Gaps found during hard test & fixes

| Gap | Fix |
|-----|-----|
| Zoho deal search used stage **ID**; API expects **display name** | Map stage IDs → labels via pipeline API before search |
| HubSpot stage-entered time can be epoch milliseconds | `_parse_stage_change_time()` handles ISO + epoch |
| Dry-run / poll hard-coded to Pipedrive | Provider router for all three CRMs |
| HubSpot missing deal OAuth scopes | Added to `HUBSPOT_SCOPES` |

---

## Known limitations (production)

1. **HubSpot reconnect** — Orgs with HubSpot connected before this deploy must **re-authorize** once so the new deal read scopes are granted.
2. **Snapshot polling** — Triggers for deals *currently* in a watched stage, not webhook “just entered”. Re-entering a stage after a prior send does not re-trigger (by design).
3. **HubSpot poll cost** — One contact-association request per deal (OK up to ~100 deals per stage per tick).
4. **Tests are mocked** — No live HubSpot/Zoho API in CI; validate dry-run on a real org after deploy.

---

## Test results

```
11 passed  tests/test_crm_deal_survey_automation.py
25 passed  CRM suite (automation + wave2 + hubspot sync)
```

---

## VPS deploy

```bash
cd /www/voxbulk
git pull origin main
./deploy-vps.sh
```

Verify `build-info.json` `git_sha` matches the commit on `main`.

### Post-deploy checklist

1. **HubSpot:** Settings → Integrations → disconnect/reconnect HubSpot (new deal scopes).
2. Open a **survey** launch step (WA step 6 or phone step 3).
3. Enable **CRM deal automation**, select stage(s), set delay, acknowledge consent.
4. Click **Test** — preview should list deals with schedule/skip reasons.
5. Confirm Celery worker + beat are running (15m poll).

---

## Related (same release train)

Dashboard commit `e1c8267` — inline integration logos + Customer Feedback–only pricing UX (separate from this API change).
