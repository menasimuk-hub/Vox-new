$ErrorActionPreference = "Stop"

$API = "http://127.0.0.1:8000"

Write-Host ""
Write-Host "=== Retover local E2E helper ==="
Write-Host "API: $API"
Write-Host ""

if (-not $env:BOOTSTRAP_TOKEN) {
  Write-Host "Missing BOOTSTRAP_TOKEN env var (required for admin bootstrap)." -ForegroundColor Yellow
  Write-Host "Set it for this shell then re-run, e.g.:" -ForegroundColor Yellow
  Write-Host '  $env:BOOTSTRAP_TOKEN="..."' -ForegroundColor Yellow
  exit 1
}

$bootstrapToken = $env:BOOTSTRAP_TOKEN

# 1) Bootstrap admin (idempotent-ish: backend returns 409 if already bootstrapped)
$adminEmail = "admin@retover.local"
$adminPassword = "AdminPassword123!"

Write-Host "Bootstrapping admin (may 409 if already bootstrapped)…"
try {
  Invoke-RestMethod -Method Post -Uri "$API/admin/bootstrap" -Headers @{ "X-Bootstrap-Token" = $bootstrapToken } `
    -Body @{ organisation_name = "Platform Admin Org"; admin_email = $adminEmail; admin_password = $adminPassword } | Out-Null
  Write-Host "Bootstrap: OK"
} catch {
  $msg = $_.Exception.Message
  if ($msg -match "409") {
    Write-Host "Bootstrap: already done (OK)"
  } else {
    throw
  }
}

# 2) Issue admin token
Write-Host "Issuing admin token…"
$adminTokenRes = Invoke-RestMethod -Method Post -Uri "$API/auth/token" -ContentType "application/x-www-form-urlencoded" `
  -Body ("username=$adminEmail&password=$adminPassword")
$adminToken = $adminTokenRes.access_token

# 3) Create an org via admin API
$orgName = "E2E Dental Clinic"
Write-Host "Creating org '$orgName'…"
$org = Invoke-RestMethod -Method Post -Uri "$API/admin/organisations" -Headers @{ Authorization = "Bearer $adminToken" } `
  -ContentType "application/json" -Body (@{ name = $orgName } | ConvertTo-Json)

# 4) Register user (creates its own org too). For the E2E flow we want user in the org you created:
#    fastest path: register user (creates user), then admin can add membership later — but we haven't built that UI/API.
#    So for now, we register the user and use its created org as the tenant used in dashboard.
$userEmail = "e2e.user@example.com"
$userPassword = "Password123!"
Write-Host "Registering user '$userEmail' (creates user + org + membership)…"
$userReg = Invoke-RestMethod -Method Post -Uri "$API/auth/register" -ContentType "application/json" `
  -Body (@{ email = $userEmail; password = $userPassword; organisation_name = $orgName } | ConvertTo-Json)
$userToken = $userReg.access_token

# 5) Set role
Write-Host "Setting user role to 'dental'…"
Invoke-RestMethod -Method Post -Uri "$API/auth/me/role" -Headers @{ Authorization = "Bearer $userToken" } `
  -ContentType "application/json" -Body (@{ role = "dental" } | ConvertTo-Json) | Out-Null

Write-Host ""
Write-Host "=== COPY/PASTE into browser DevTools console ==="
Write-Host ""
Write-Host "Admin UI (http://localhost:5174):"
Write-Host "localStorage.setItem('retover_admin_access_token', '$adminToken')"
Write-Host ""
Write-Host "Dashboard UI (http://localhost:5175):"
Write-Host "localStorage.setItem('retover_access_token', '$userToken')"
Write-Host "localStorage.setItem('retover_org_id', '$($userReg.org_id)')"
Write-Host "localStorage.setItem('retover_user_id', '$($userReg.user_id)')"
Write-Host ""
Write-Host "=== Test data ==="
Write-Host "Admin email: $adminEmail"
Write-Host "Admin password: $adminPassword"
Write-Host "User email: $userEmail"
Write-Host "User password: $userPassword"
Write-Host "Org created (admin): $($org.id) $($org.name)"
Write-Host "Org created (user register): $($userReg.org_id) $orgName"
Write-Host ""

