## Local end-to-end test (fast path)

### URLs (fixed ports)
- API: `http://127.0.0.1:8000`
- Admin UI: `http://localhost:5174`
- Public frontend: `http://localhost:5173`
- Dashboard UI: `http://localhost:5175`

### Env vars (create `.env` from `.env.example`)
- `admin.voxbulk.com/adim-web/.env`: `VITE_API_BASE_URL=http://127.0.0.1:8000`
- `voxbulk.com/frontend/.env`: `VITE_API_BASE_URL=http://127.0.0.1:8000`
- `dashboard.voxbulk.com/dashboard-web/.env`: `VITE_API_BASE_URL=http://127.0.0.1:8000`

### Start commands

API:
```powershell
cd C:\Users\zaghlol\Downloads\voxbulk.com\retover-api
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Admin UI:
```powershell
cd C:\Users\zaghlol\Downloads\voxbulk.com\admin.voxbulk.com\adim-web
npm run dev
```

Public frontend:
```powershell
cd C:\Users\zaghlol\Downloads\voxbulk.com\voxbulk.com\frontend
npm run dev
```

Dashboard UI:
```powershell
cd C:\Users\zaghlol\Downloads\voxbulk.com\dashboard.voxbulk.com\dashboard-web
npm run dev
```

### Flow A — Invite / admin-created organisation (happy path)
1) Bootstrap admin + set admin token (one-time)
   - `POST /admin/bootstrap` (requires `BOOTSTRAP_TOKEN`)
   - `POST /auth/token` to get admin bearer token
   - In Admin UI DevTools:
     - `localStorage.setItem("retover_admin_access_token", "<TOKEN>")`

2) Admin creates org
   - Open `http://localhost:5174/organisations`
   - Click **New organisation**
   - Open the org profile

3) Admin opens org-linked signup
   - In org profile, click **Open signup page** (or **Copy signup link**)

4) User signs up + picks role
   - Complete signup in `http://localhost:5173/signin?...`
   - Go to `http://localhost:5173/onboarding` and pick role (e.g. Dental)

5) Validate
   - Admin org profile shows the user + role
   - Dashboard `http://localhost:5175` loads authenticated

### Flow B — Self-serve onboarding (pending approval)
1) User submits self-serve request
   - Open `http://localhost:5173/signin` (no `org_id`)
   - Switch to **Sign up**
   - Fill: email/password/clinic name/package
   - Submit → you should see **Pending approval**

2) Admin approves
   - Open `http://localhost:5174/onboarding/pending-signups`
   - Click **Approve**

3) User logs in + opens dashboard
   - Back to `http://localhost:5173/signin` → Sign in
   - Open dashboard `http://localhost:5175`

### If the public frontend cannot install/run
If `npm install` fails with `UNABLE_TO_VERIFY_LEAF_SIGNATURE` (machine/cert issue), you can still run the full E2E test using the helper:

```powershell
cd C:\Users\zaghlol\Downloads\voxbulk.com
$env:BOOTSTRAP_TOKEN="YOUR_BOOTSTRAP_TOKEN"
.\scripts\e2e_local_test.ps1
```

