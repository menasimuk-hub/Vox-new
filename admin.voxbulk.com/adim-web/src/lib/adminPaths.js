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
  return '/dashboard/mrr'
}

export function canAccessAdminPath(role, pathname) {
  const r = normalizeAdminRole(role)
  if (r === 'superadmin') return true

  const p = String(pathname || '/')

  const isUnder = (prefix) => p === prefix || p.startsWith(`${prefix}/`)

  if (isUnder('/integrations') || isUnder('/services-api') || p.includes('/social-login')) return false

  // Platform admins (distinct from Organisation → clinic users listed per tenant).
  if (p === '/admin/users' || p.startsWith('/admin/users/')) {
    return r === 'superadmin'
  }

  // Marketing is restricted to SMTP + templates (still uses integration-style APIs only under /admin/email).
  if (r === 'marketing') {
    return isUnder('/settings/email') || isUnder('/support')
  }

  if (r === 'technical') {
    return isUnder('/support') || isUnder('/ai/agents') || p === '/ai/agent-demo'
  }

  if (r === 'support') {
    return isUnder('/support')
  }

  if (r === 'accountant') {
    return (
      isUnder('/dashboard') ||
      isUnder('/billing') ||
      isUnder('/organisations') ||
      isUnder('/onboarding') ||
      isUnder('/operations') ||
      isUnder('/support') ||
      isUnder('/ai') ||
      isUnder('/compliance') ||
      isUnder('/analytics') ||
      isUnder('/team') ||
      isUnder('/marketing') ||
      isUnder('/settings/global') ||
      isUnder('/settings/flags') ||
      isUnder('/settings/api-keys')
    )
  }

  return false
}

export function filterSidebarNav(adminRole, navTree) {
  const r = normalizeAdminRole(adminRole)
  if (r === 'superadmin') return navTree

  return navTree
    .map(([group, Icon, items]) => {
      const nextItems = items.filter(([, path]) => canAccessAdminPath(r, path))
      return [group, Icon, nextItems]
    })
    .filter(([, , items]) => items.length > 0)
}
