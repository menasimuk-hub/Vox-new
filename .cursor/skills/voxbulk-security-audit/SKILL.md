---
name: voxbulk-security-audit
description: >-
  Audits VoxBulk code for security issues affecting tenant isolation, secrets
  (Fernet), webhooks, PII/user data, and VPS/API hardening. Use when the user
  asks for a security review, security audit, data protection check, OWASP
  review, IDOR/authz check, or says /security-audit, "is our data safe", or
  "check server security".
---

# VoxBulk Security Audit

Report-only by default. Do **not** fix findings unless the user explicitly asks.

For a quick **diff-only** pass, also use the built-in `security-review` subagent (`/review-security`). This skill is for **VoxBulk-aware** depth (tenancy, Fernet, webhooks, PII, VPS).

## Workflow

```
- [ ] 1. Confirm scope (see below)
- [ ] 2. Map entry points (routers, webhooks, auth, billing, uploads)
- [ ] 3. Run checklist sections that match the scope
- [ ] 4. Optionally launch security-review on branch/uncommitted diff
- [ ] 5. Deliver findings table + residual risk + next tests
```

### Scope (ask once if unclear)

| Scope | When |
|-------|------|
| **Recent diff** | PR, branch, or uncommitted changes |
| **Area** | e.g. `voxbulk-api/app/routers/auth.py`, expo, billing, WA webhooks |
| **Full pass** | Pre-release / “is production safe?” — sample high-risk paths; say what was not covered |

Default: **recent diff** if git shows changes; otherwise ask.

## Priority checklist (always apply matching sections)

### 1. Tenant isolation & authz (Critical)

- Multi-tenancy from **JWT principal** (`org_id` / organisation) — never trust a client-supplied org header or body field alone
- Every tenant read/write in services scoped to `principal.organisation_id` (or equivalent)
- Check IDOR: object IDs from the URL must still be owned by the caller’s org
- Org roles via `app/services/org_rbac.py` — sensitive actions require the right role (`owner` / `manager` / etc.)
- Admin vs dashboard vs public routes: no accidental privilege bleed
- Password hashing stays `pbkdf2_sha256` in `app/core/security.py`

### 2. Secrets & Fernet (Critical)

- Integration credentials encrypted at rest (`get_encryptor()` / Fernet, `ENCRYPTION_KEY`)
- Never log, return in API JSON, or put decrypted tokens in error messages
- Connection profiles: Meta/Telnyx tokens via `*_encrypted` columns + decrypt helpers — keep that boundary
- No secrets in commits, frontend bundles, `localStorage` for API keys, or chat paste of `.env`
- OAuth client secrets and webhook secrets only from settings/DB encrypted config

### 3. Webhooks (Critical)

Preserve signature verification; do not add unverified webhook handlers.

Known patterns in `app/routers/webhooks.py` + helpers:

| Provider | Verify via |
|----------|------------|
| Meta / WhatsApp | `verify_meta_webhook_signature` |
| Vapi | `verify_hmac_sha256_base64` |
| GoCardless | `verify_gocardless_signature_hex` |
| Stripe / Airwallex | payment service `verify_webhook_signature` |
| Twilio-style | `verify_twilio_signature` |

Also check: raw body used for HMAC (not re-serialized JSON); missing secret → reject; replay/idempotency where money or credits are involved.

### 4. PII & user data (High)

- Minimize phone, email, survey answers, interview audio paths in logs
- Export/download endpoints: authz + org scope; no cross-tenant CSV/report leakage
- Public/magic links: token entropy, expiry, single-use where appropriate
- Frontend: do not expose internal IDs/tokens beyond what the UI needs
- Email templates: never execute untrusted HTML as code; Admin owns template content

### 5. Injection, SSRF, uploads (High)

- SQLAlchemy parameterized queries only — no f-string / `.format` raw SQL with user input
- User-controlled URLs: allowlist before server-side fetch (SSRF)
- Uploads: size/type limits; no path traversal into `data/` or wwwroot
- XSS: React escapes by default — avoid `dangerouslySetInnerHTML` with untrusted content

### 6. VPS / server / deploy (High)

- API intended bind (`127.0.0.1:8000` behind nginx) — not accidentally public debug
- No `debug=True` / open CORS `*` for credentialed prod APIs
- OAuth redirect URIs locked to known hosts (`api.voxbulk.com`, dashboard)
- Redis/MySQL/Celery not exposed on public interfaces
- Long-running services via systemd/Supervisor (`Restart=always`) — not ad-hoc nohup-only
- Deploy does not commit `.env`; secrets stay on VPS only
- After review of deploy scripts: no leaking tokens in `deploy-vps.sh` logs

## Output format

One table, severity descending:

| Severity | Location | Finding | Impact | Fix |
|----------|----------|---------|--------|-----|
| Critical / High / Medium / Low / Info | `path:line` | Short issue | Who/what is at risk | Concrete remediation |

Then:

1. **Summary** — counts by severity (one line)
2. **Residual risk** — what was not fully proven (e.g. no live pen-test)
3. **Next tests** — 2–5 concrete checks (IDOR case, webhook with bad sig, cross-org export)

## Severity guide

| Level | Examples |
|-------|----------|
| **Critical** | Cross-tenant data access; unverified webhook that mutates billing/credits; plaintext secrets in repo |
| **High** | Missing authz on sensitive route; PII in logs; SSRF; broken signature check |
| **Medium** | Over-broad CORS; weak token expiry on magic links; verbose errors leaking internals |
| **Low / Info** | Hardening nits, missing rate limits, defense-in-depth |

## Guardrails

- Do not invent vulns without a code path — cite file/line
- Do not disable webhook verification “temporarily” in suggested fixes
- Do not suggest switching password hasher unless the user asks
- Prefer reading `app/core/security.py`, `org_rbac.py`, webhook routers, and the touched service

## Extra detail

For a longer per-area checklist, see [checklist.md](checklist.md).
