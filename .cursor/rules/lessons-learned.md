# Lessons learned — VoxBulk agent mistakes

Read this file **before** making changes. Add a new section when a mistake repeats.

Production VPS: **`198.244.178.240`** (`qusay`). **`161.97.159.253` is decommissioned** — never use it.

---

## Wrong production VPS

- **Mistake:** SSH'd to `161.97.159.253`, concluded Meta was not deployed, and planned around "Meta blocked until verification."
- **Fix:** Confirm host via `api.voxbulk.com` / repo deploy rules; read `meta_whatsapp_service.py` usage and query live `provider_configs` on **`198.244.178.240`** before claiming prod state.
- **Rule:** Never assert production integration status without reading code **and** checking the correct VPS (`198.244.178.240`).

---

## WA sync model assumed without asking

- **Mistake:** Flip-flopped between three models in one audit: (1) dual-push as missing bugs, (2) single-profile failover only, (3) dual-catalog sync with Meta 99 default sends — without locking spec first.
- **Fix:** Read `docs/wa-template-sync-contract.md` and ask: default profile for sends, push to both profiles or one, pull status-only, naming prefixes, which entry points (hub row, industry button, toolbar, scripts).
- **Rule:** For WA template/sync work, confirm the operational model in chat **before** listing bugs or writing fix code.

---

## Customer Feedback prefix wrong (`voxbulk_cf_*` vs `cfs_*`)

- **Mistake:** Described CF templates as `voxbulk_cf_*` and implied renames; user had to correct that names must not change.
- **Fix:** Canonical CF prefix is **`cfs_{industry}_{topic}_{lang}_v1`** per sync contract; legacy `voxbulk_cf_*` may still exist on Meta until pushed — filters and counts must handle both, never rename in routine sync.
- **Rule:** Never propose or document CF renames; use `cfs_*` as canonical and treat `voxbulk_cf_*` as legacy remote-only.

---

## WABA-wide counts shown as product-scoped

- **Mistake:** Reported ~3,992 "survey" templates when ~3,680 were `voxbulk_cf_*` on the same WABA; profile matrix mixed scoped utility/marketing with whole-account totals (`371/774`).
- **Fix:** Use `wa_template_product_scope.py` / `filter_remote_for_service_code()`; show **scoped / account** pairs (e.g. `18 / 49` marketing) on the active tab.
- **Rule:** Any WA template count must state the prefix filter (`was_*`, `cfs_*`, whole WABA) and match Meta Manager account totals on the right-hand number.

---

## Buttonless templates flagged as sync bugs

- **Mistake:** Treated interview templates and buttonless system templates (thank-you, tell-us-more) as "not syncing to Meta" bugs.
- **Fix:** Buttonless paths send **session text from server** via default profile; only **buttoned** system templates (welcome, opt-in) are pushed to Meta.
- **Rule:** Before filing a sync bug, check whether the template is buttonless — if so, verify the session-text send path, not Meta push.

---

## DB pull overwrote local content (assumed or implemented)

- **Mistake:** Audits and early code paths treated Meta catalog import as normal sync; hub "sync" sometimes implied body/name import.
- **Fix:** Pull = **status only** (`status`, `rejection_reason`, remote IDs); push = DB → Meta/Telnyx with explicit `connection_profile_id`.
- **Rule:** Never set `existing.name` or `draft_components_json` from Meta on routine pull; hub step 1 must use `status_only: true`.

---

## Claimed "fixed" without end-to-end verification

- **Mistake:** Survey CF fixes (`9095806`, `0ea1feb`) fixed voice/send **paths** but not **triggers** (tell-us-more never fired); told user it was fixed while production still ran an older build SHA.
- **Fix:** Trace full flow (rating → branch → conv flags → send method); compare `curl /health/build` SHA to `git rev-parse HEAD` on VPS after deploy; ask user to confirm on real number.
- **Rule:** Do not say a production bug is fixed until the full user-visible path is traced in code **and** build SHA on VPS matches the fix commit.

---

## Partial fix on one sync entry point

- **Mistake:** Fixed hub row sync or backend push but left industry button, toolbar "Push changed", mirror script, or send/dispatch paths on old behaviour.
- **Fix:** Grep all entry points: `WaTemplatesHub.jsx`, `WaIndustryBrowser.jsx`, `sync_wa_templates_both_profiles.py`, `push_template_to_both_profiles`, dispatch services.
- **Rule:** Every WA sync change must list and update **all** entry points from `agent-commit-and-clarify.mdc`, not just the one the user mentioned.

---

## CF import `replace=True` deletes Meta templates

- **Mistake:** Considered `FeedbackMdImportService` with `replace=True` for DB updates without noting it calls Meta to **delete** remote templates.
- **Fix:** Use targeted `body_text` / `buttons_json` updates on existing rows, or `replace=False` merge; never delete/push Meta when user said "DB only" or "no Meta push."
- **Rule:** Before any feedback import/seed, read whether the code path calls `_delete_industry_templates` or Meta delete APIs.

---

## UTILITY rewrite used wrong anchors and dates

- **Mistake:** v1 reframes used "today" / same-day wording and generic satisfaction lines; failed Meta UTILITY lint and user review.
- **Fix:** Use **transaction anchor** ("recent visit/stay/purchase") without calendar dates; topic-specific reframes for recommend/return-intent; run `lint_utility_template` per row.
- **Rule:** CF UTILITY copy must include a transaction anchor, avoid promotional/recommend phrasing, and never use "today" as the visit date.

---

## Generator shared keys across industries

- **Mistake:** `TRANSLATIONS.setdefault(key, {})` caused cross-industry topic collisions in `generate_customer_feedback_utility_review.py`.
- **Fix:** Key translations as `f"{industry}:{topic_key}"`; clamp button labels with `clamp_utility_button_labels` (Meta 20-char limit).
- **Rule:** Any multi-industry template generator must namespace keys by industry and clamp button labels before lint/push.

---

## Arabic lint false positive on delivery wording

- **Mistake:** Arabic `توصيل` (delivery) tripped recommend-pattern lint (`توص` substring).
- **Fix:** Use `تسليم` for delivery in AR utility copy when lint flags `توصيل`.
- **Rule:** When non-English UTILITY lint fails on "recommend", check substring false positives before rewriting the whole line.

---

## Bulk rewrite changed entire corpus unexpectedly

- **Mistake:** Dry-run showed **2,426 / 2,804** rows changing when user expected only high-risk topics; anchor normalization touched almost every row.
- **Fix:** Produce per-industry before/after plan; separate "must-change" (marketing triggers) from "cosmetic" (anchor only); get sign-off before DB write.
- **Rule:** For bulk CF/survey DB updates, run dry-run first and report changed vs unchanged counts before writing anything.

---

## Parser treated `/` in body as button row

- **Mistake:** Feedback MD import treated `check-in/check-out` as a button line because of `/`.
- **Fix:** `_looks_like_options_line` rejects lines with `?`, length > 100, or survey-style phrasing before treating `/` as button separator.
- **Rule:** When parsing WA template markdown, require short (≤80 char) slash-separated segments and no question marks before classifying a line as buttons.

---

## Layout/theme changed without approval

- **Mistake:** Proposed or implemented admin UI layout changes instead of matching provided HTML mock exactly (Connection Profiles, Products hub).
- **Fix:** User HTML/design file is source of truth; change copy/data wiring only unless user explicitly approves layout changes.
- **Rule:** Never change admin layout, colours, spacing, or HTML structure without explicit user approval — match provided design files 100%.

---

## Profile display name treated as functional

- **Mistake:** Debugged "Meta 99" vs "Meta 2099" as a routing bug; renamed profile on server unnecessarily.
- **Fix:** Routing uses `connection_profile_id` UUID and stored credentials; display name is cosmetic only.
- **Rule:** WA sync/send issues must be debugged via profile UUID, WABA ID, and phone number — not profile label text.

---

## Platform Meta fallback when profile selected

- **Mistake:** Push/pull without `connection_profile_id` fell back to Admin → Integrations platform Meta config, causing wrong-WABA pushes while UI showed Meta 99 selected.
- **Fix:** `resolve_meta_api_config(..., connection_profile_id=...)` must use profile credentials only; hub must always send selected profile UUID.
- **Rule:** Every admin WA push/pull request must pass `connection_profile_id`; never rely on platform Meta fallback when a profile is selected in the hub.

---

## Stale API process after deploy

- **Mistake:** Claimed fixes were live while `health/build` SHA lagged `git HEAD` — old uvicorn still serving.
- **Fix:** After deploy, verify `curl -sf http://127.0.0.1:8000/health/build` matches `git rev-parse --short HEAD`; `pkill -f 'uvicorn.*main:app'` + `./vox.sh restart` if not.
- **Rule:** Never tell the user a backend fix is on production until `/health/build` commit matches the pushed git commit.

---

## Chunked CF push resume on batch failure

- **Mistake:** Chunk state did not resume correctly after a failed language batch; Telnyx 503s aborted runs without retry.
- **Fix:** Persist batch cursor in `chunk-state/*.json`; retry Telnyx 503 with backoff; resume from last failed batch, not industry start.
- **Rule:** Long-running VPS push scripts must be idempotent with persisted cursor + provider retry — never assume a single batch run completes cleanly.

---

## Marketing purge scope too broad

- **Mistake:** Early marketing purge plans touched local DB deletes and broad catalog changes beyond survey rewrite.
- **Fix:** Purge rewrites **survey** `was_*` bodies for UTILITY; narrow scope; never delete local DB rows in routine purge; use `cfs_*` not legacy prefixes in new tooling.
- **Rule:** Marketing/utility remediation scripts must state exactly which prefixes and tables they touch and must not delete local template rows unless explicitly requested.

---

## Guessing DB topic mapping

- **Mistake:** Assumed `template_key` / industry slug mapping to DB UUIDs without querying production `feedback_wa_templates` rows.
- **Fix:** SSH query sample rows per industry (`industry_id`, `template_key`, `language`, `meta_template_name`) before writing update scripts.
- **Rule:** Before any CF DB seed/update script, query at least one industry's live row shape on VPS — do not infer UUID mapping from seed files alone.

---

## Commits and repo changes without explicit ask

- **Mistake:** Edited repo files, created diag scripts, or committed when user asked for paste-in-chat review, plan only, or "do not change."
- **Fix:** Follow `no-changes-without-approval.mdc`; deliver copy in chat when asked; commit only when user requested implementation (or workspace rule explicitly requires it for that task).
- **Rule:** If the task is review/plan/"paste in chat," make zero repo edits unless the user explicitly asks to implement.
