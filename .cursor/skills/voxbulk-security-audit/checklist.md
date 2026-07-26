# VoxBulk security checklist (detail)

Use from `SKILL.md` when the audit is area-wide or pre-release. Tick only what you actually inspected.

## Auth & sessions

- [ ] Access tokens include `sub`, `org_id`, `tv` (token version); invalid/expired rejected
- [ ] Logout / password change / revoke bumps token version where implemented
- [ ] OAuth callbacks validate `state`; redirect allowlist matches Admin + provider console
- [ ] Social login does not attach accounts across orgs without explicit linking rules
- [ ] Rate limit or lockout considerations on login / OTP / magic link (note if missing)

## Tenant isolation (IDOR hunt)

- [ ] List endpoints filter by org before pagination
- [ ] Get-by-id / update / delete load resource then assert `organisation_id == principal.org`
- [ ] Nested resources (survey → responses, booth → payments) inherit parent org check
- [ ] Admin routes require admin auth — not reusable dashboard JWT
- [ ] Background jobs (Celery) re-derive org from stored job payload, not from an unverified client

## Fernet & integrations

- [ ] New secret fields use `*_encrypted` + encrypt on write / decrypt only in service boundary
- [ ] Admin “save integration” does not echo full secrets back in responses
- [ ] Connection profile seed/copy does not write plaintext to logs
- [ ] `ENCRYPTION_KEY` rotation story: note if decrypt-fail is handled safely (no crash loop dumping ciphertext)

## Webhooks & payments

- [ ] New webhook route verifies signature before parsing side effects
- [ ] Uses raw request body bytes for HMAC
- [ ] Rejects when secret unset/empty
- [ ] Payment/credit webhooks are idempotent (duplicate delivery safe)
- [ ] Meta verify-token challenge (GET) does not leak app secret

## PII / GDPR-minded

- [ ] Survey/feedback answers not in application info logs
- [ ] Support/debug endpoints gated; no unrestricted PII dump
- [ ] Data deletion / org offboarding paths do not leave orphaned files with phone numbers
- [ ] WhatsApp/Telnyx message content logging is redacted or off in prod where possible

## API & frontend surface

- [ ] Public marketing site does not call privileged APIs with embedded secrets
- [ ] Dashboard API client sends Authorization header only; no org_id override header
- [ ] `dangerouslySetInnerHTML` / admin HTML preview: trusted Admin content only
- [ ] CORS origins explicit for dashboard/admin/public hosts

## VPS & runtime

- [ ] nginx terminates TLS; API not exposed bare on 0.0.0.0:8000 to the internet
- [ ] Firewall: MySQL/Redis ports not public
- [ ] `voxbulk-api.service` / public preview / Celery supervised and restarting
- [ ] File permissions on `.env` and `data/` restrictive
- [ ] Deploy script does not print env secrets; git pull cannot overwrite `.env` from repo

## Suggested manual tests after code audit

1. As Org A, request Org B’s resource ID → expect 404/403
2. Replay webhook with invalid signature → expect 401/403, no DB change
3. Call sensitive export without auth → expect 401
4. Member/accountant role hits owner-only billing route → expect 403
5. Confirm decrypted integration token never appears in API response JSON
