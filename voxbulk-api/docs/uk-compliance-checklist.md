# UK compliance baseline (PECR / UK GDPR / DPA 2018)

This document describes the **technical baseline** implemented in the VoxBulk codebase. It is **not legal advice** — policy and DPIA text still require review by your DPO or counsel.

## What was implemented

### A. Consent / lawful basis
- Per-order `config.compliance` object (merged with org defaults from `organisation_compliance_configs`).
- Fields: `lawful_basis`, `message_purpose`, `special_category_data_present`, `article9_condition`.
- **Launch/send blocked** when validation fails (`UkComplianceService.assert_order_launch_allowed`).
- Gates: `PlatformCatalogService.start_order`, `InterviewLaunchService.launch_after_payment`, `InterviewBookingService.send_invites`, `SurveyDispatchService._dispatch_one`.

### B. PECR / direct messaging
- `message_purpose`: `transactional`, `survey`, `interview`, `direct_marketing` (marketing requires `lawful_basis=consent`).
- Central STOP regex: `app/services/uk_compliance_opt_out.py` (`STOP`, `STOPALL`, `UNSUBSCRIBE`, `CANCEL`, `END`, `QUIT`).
- **Survey WA**: existing handler; uses shared regex; opt-out **not** stored as answers; org suppression via `OrgOptOutService`.
- **Interview WA**: separate handler; STOP → org suppression only (no survey recipient mutation).
- Outbound: `should_block_outbound_phone` before survey WA dispatch and interview WA invites.

### C. Transparency
- Org fields: `privacy_notice_url`, `contact_email`, `dpo_email`, `privacy_intro_text_default`.
- Email templates (`email_templates`): `lawful_basis`, `privacy_notice_url`, `contact_email` on every outbound template (Admin → Email → edit template).
- Launch merge order: order `config.compliance` → org defaults → launch outbound email templates → platform defaults.
- Survey WA intro appends privacy footer from merged compliance config.
- Simulator: synthetic phone (`+447700900…`), name `Sim Respondent`, `simulator_synthetic_only` flag.

### D. Data minimisation
- `collect_minimal_data` / `collect_minimal_data_default` flags on order/org config.
- Simulator defaults to minimal/synthetic data.

### E. Retention
- Org retention day fields on `organisation_compliance_configs` (`retention_days_messages`, `retention_days_responses`, `retention_days_recordings`, `retention_days_transcripts`).
- Daily job: `uk_compliance_retention_scheduler_loop` in `main.py` (leader lock, every 24h after a 5-minute startup delay).
- Uses **per-org** day counts when set; otherwise platform defaults from `uk_compliance_constants.py`.
- Anonymises aged `whatsapp_logs.body`, WhatsApp `media_json` (recordings window), recipient `result_json`, completed order `report_json`.
- Admin dry-run (no writes): Admin → Compliance → Consent / opt-out → **Retention dry-run**, which calls `POST /admin/compliance/retention/run?dry_run=true`.
- Live pass (writes): same endpoint with `dry_run=false` (ops only). Confirm counts in the returned `stats` and in `retention.pass` audit events.

### I. Data subject access / portability
- Dashboard owners and managers: **Settings → Profile → Download ZIP**, or `GET /organisations/me/data-export`.
- ZIP contains organisation profile, memberships, opt-outs, email prefs, audit summary, and survey/interview **metadata** (no recordings, CVs, or full result payloads; no decrypted credentials).

### F. Security / audit
- Table: `platform_compliance_audit_events`.
- Events: `opt_out.received`, `send.blocked`, `workflow.launch`, `template.deleted`, `consent.*`, `retention.pass`.
- Admin routes: `app/routers/admin_compliance.py` (requires `CAP_ORG_OPS`).
- WA Survey template routes remain `CAP_INTEGRATION` — unchanged RBAC split.

### G. Admin UI
- **Consent / opt-out**: `/compliance/consent` → `ComplianceSettings.jsx` (org defaults + recent audit).
- **Audit logs**: `/compliance/audit` → `ComplianceAudit.jsx`.
- Order readiness API: `GET /admin/compliance/orders/{order_id}/readiness`.

### H. Isolation (unchanged)
- Survey WA: `survey_whatsapp_conversation_service.py` only.
- Interview WA: `interview_whatsapp_inbound_service.py` only.
- Telnyx ingress order: survey → interview → sales (`telnyx_inbound_messaging_service.py`).

## Where to configure

| Area | Location |
|------|----------|
| Org defaults | Admin → Compliance → Consent / opt-out, or `PUT /admin/compliance/organisations/{org_id}` |
| Per order | `PUT /admin/compliance/orders/{order_id}` with `{ "compliance": { … } }` |
| Onboarding | New orgs get defaults in `OrganisationOnboardingService.get_or_create_compliance` |
| Customer opt-outs | Dashboard → org opt-outs API (`/organisations/me/opt-outs`) |

## Migrations

Run: `alembic upgrade head` (revisions `0097_uk_compliance_baseline`, `0100_email_template_compliance_fields`).

## Still needs policy / legal review

- Lawful basis choices per customer vertical (especially health / recruitment).
- Article 9 condition mapping for special-category surveys or interviews.
- Retention periods vs customer contracts and ICO guidance.
- Full DPIA documentation and RoPA — not generated by this code.
- Email/SMS PECR flows beyond WhatsApp (partially covered by voice opt-out helpers).

## Known limitations

- Retention pass honours per-org day fields; null fields still fall back to platform defaults.
- `direct_marketing` purpose is validated but not wired to a separate marketing automation product.
- Compliance audit does not yet cover every admin export endpoint.
- Interview WA STOP does not mark booking tokens cancelled (org suppression only).

## Tests

```bash
pytest tests/test_uk_compliance_baseline.py tests/test_uk_compliance_retention.py tests/test_org_data_export.py tests/test_survey_wa_workflow_hardening.py -q
```
