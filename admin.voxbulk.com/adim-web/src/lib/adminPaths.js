/** Mirrors backend coarse RBAC for navigation + lightweight route guarding. */

export function normalizeAdminRole(r) {
  const x = String(r || '').trim().toLowerCase()
  if (x === 'admin') return 'superadmin'
  if (x === 'superadmin' || x === 'accountant' || x === 'marketing' || x === 'technical' || x === 'support') return x
  return 'superadmin'
}

export function defaultAdminHome(role) {
  const r = normalizeAdminRole(role)
  if (r === 'marketing') return '/settings/email'
  if (r === 'accountant') return '/billing/subscriptions'
  return '/dashboard'
}

export function canAccessAdminPath(role, pathname) {
  const r = normalizeAdminRole(role)
  if (r === 'superadmin') return true

  const p = String(pathname || '/')

  const isUnder = (prefix) => p === prefix || p.startsWith(`${prefix}/`)

  if (isUnder('/integrations') || isUnder('/services-api') || p.includes('/social-login')) return false

  // Platform admins (distinct from Organisation → clinic users listed per tenant).
  if (p === '/platform/users' || p.startsWith('/platform/users/')) {
    return r === 'superadmin'
  }

  // Marketing is restricted to SMTP + templates (still uses integration-style APIs only under /admin/email).
  if (r === 'marketing') {
    return (
      isUnder('/settings/email') ||
      isUnder('/settings/legal') ||
      isUnder('/support') ||
      isUnder('/marketing/ai-team') ||
      isUnder('/marketing/frontpage-call-leads') ||
      isUnder('/marketing/lead-sources') ||
      isUnder('/marketing/lead-sales') ||
      isUnder('/marketing/lead-sales/settings') ||
      isUnder('/marketing/promo-offers')
    )
  }

  if (r === 'technical') {
    return (
      isUnder('/support') ||
      isUnder('/operations') ||
      isUnder('/settings/wa-survey') ||
      isUnder('/settings/wa-interview') ||
      isUnder('/analytics') ||
      isUnder('/ai/agents') ||
      p === '/ai/agent-demo' ||
      isUnder('/marketing/frontpage-call-leads') ||
      isUnder('/marketing/lead-sources') ||
      isUnder('/marketing/lead-sales') ||
      isUnder('/marketing/lead-sales/settings')
    )
  }

  if (r === 'support') {
    return (
      isUnder('/support') ||
      isUnder('/marketing/lead-sources') ||
      isUnder('/marketing/lead-sales') ||
      isUnder('/marketing/frontpage-call-leads') ||
      isUnder('/marketing/lead-sales/settings')
    )
  }

  if (r === 'accountant') {
    return (
      isUnder('/dashboard') ||
      isUnder('/billing') ||
      isUnder('/pricing') ||
      isUnder('/organisations') ||
      isUnder('/onboarding') ||
      isUnder('/customer-feedback') ||
      isUnder('/operations') ||
      isUnder('/settings/wa-survey') ||
      isUnder('/settings/wa-interview') ||
      isUnder('/ai') ||
      isUnder('/compliance') ||
      isUnder('/analytics') ||
      isUnder('/team') ||
      isUnder('/support') ||
      isUnder('/marketing') ||
      isUnder('/settings/global') ||
      isUnder('/settings/flags') ||
      isUnder('/settings/legal') ||
      isUnder('/settings/api-keys')
    )
  }

  return false
}

export function filterSidebarNav(adminRole, navTree) {
  const r = normalizeAdminRole(adminRole)
  const groups = navTree.map((entry) => {
    if (entry.length === 2) return [entry[0], entry[1]]
    return [entry[0], entry[2]]
  })

  if (r === 'superadmin') return groups

  return groups
    .map(([group, items]) => {
      const nextItems = items.filter(([, path]) => canAccessAdminPath(r, path))
      return [group, nextItems]
    })
    .filter(([, items]) => items.length > 0)
}
