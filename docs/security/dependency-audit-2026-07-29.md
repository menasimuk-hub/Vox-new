# Dependency audit report — 2026-07-29 (Phase 10 / I6)

Read-only scan of pinned dependencies. **No version bumps in this PR** — treat findings as an upgrade backlog and verify compatibility before changing `requirements.txt` / lockfiles.

Raw tool output: [`reports/`](reports/).

## Commands run

```bash
cd voxbulk-api
pip-audit -r requirements.txt

cd dashboard.voxbulk.com/dashboard-web && npm audit
cd admin.voxbulk.com/adim-web && npm audit
cd voxbulk.com/frontend && npm audit
```

## Python (`voxbulk-api/requirements.txt`)

`pip-audit` reported **22 advisories across 6 packages** (tool exit code 0 in this environment; treat as fail-open — review the table).

| Package | Pinned | Advisories (sample IDs) | Suggested direction |
|---------|--------|-------------------------|---------------------|
| `python-jose` | 3.3.0 | PYSEC-2024-232/233, PYSEC-2025-185 | Move to 3.4.x **or** evaluate `PyJWT` (jose uses vulnerable `ecdsa` path) |
| `cryptography` | 43.0.3 | PYSEC-2026-35, -1284, -2141, GHSA-537c-gmf6-5ccf | Bump toward current stable (44+/46+); re-test Fernet + TLS clients |
| `starlette` | 0.37.2 (via FastAPI 0.111.0) | several PYSEC-2026-* | Bump FastAPI / Starlette together; re-test middleware + websockets |
| `weasyprint` | 68.1 | PYSEC-2026-3412 | Check advisory + upgrade when invoice PDF path validated |
| `ecdsa` | 0.19.2 (transitive via jose) | PYSEC-2026-1325 | Cleared by replacing/upgrading jose |
| `pytest` | 8.3.3 | PYSEC-2026-1845 | Dev-only; bump in test env |

## npm

| App | Path | Total | Critical | High | Moderate | Low |
|-----|------|------:|---------:|-----:|---------:|----:|
| Dashboard | `dashboard.voxbulk.com/dashboard-web` | 8 | 0 | 4 | 3 | 1 |
| Admin | `admin.voxbulk.com/adim-web` | 13 | 2 | 4 | 6 | 1 |
| Public site | `voxbulk.com/frontend` | 23 | 3 | 10 | 8 | 2 |

Recurring themes in tool output:

- `vite` 7.x advisories (Windows path / launch-editor) — mostly **dev-server** risk; still upgrade on next frontend maintenance.
- `@telnyx/webrtc` → `uuid` / `@peermetrics/webrtc-stats` — `npm audit fix --force` proposes breaking `@telnyx/webrtc@1.0.9`; **do not force** without WebRTC call regression tests.
- Public `ws` high severity — upgrade with vite/tooling stack.

Safe first pass (non-force): `npm audit fix` in each app, then `npm run build` + smoke.

## Explicit non-actions in Phase 10

- No silent major upgrades without a dedicated PR.
- No claim that production is “clean” — this is a baseline inventory.
- Live credential rotation is an **ops checklist** (see `AUDIT_PRODUCT_INFRASTRUCTURE.md` § Code Audit Findings), not automated here.
