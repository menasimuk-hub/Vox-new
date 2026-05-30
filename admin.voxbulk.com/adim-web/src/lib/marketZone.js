/** Admin market zones — mirrors dashboard billing/market.ts */
export const ZONE_CONFIG = {
  gb: { label: 'GB users', title: 'United Kingdom', flag: '🇬🇧', path: '/organisations/zone/gb' },
  us: { label: 'USA users', title: 'United States', flag: '🇺🇸', path: '/organisations/zone/us' },
  ca: { label: 'Canada users', title: 'Canada', flag: '🇨🇦', path: '/organisations/zone/ca' },
  au: { label: 'Australia users', title: 'Australia', flag: '🇦🇺', path: '/organisations/zone/au' },
}

export function zoneFromParam(raw) {
  const z = String(raw || '').trim().toLowerCase()
  if (z === 'uk') return 'gb'
  return ZONE_CONFIG[z] ? z : null
}

export function subscriptionLabel(status) {
  const s = String(status || '').toLowerCase()
  if (!s) return 'No plan'
  if (s === 'active') return 'Active'
  if (s === 'trialing' || s === 'trial') return 'Trial'
  if (s === 'past_due') return 'Past due'
  if (s === 'cancelled' || s === 'canceled') return 'Cancelled'
  return status
}

export function orgStatusPill(org) {
  if (org?.is_suspended) return { cls: 'p-amber', text: 'Suspended' }
  const sub = String(org?.subscription_status || '').toLowerCase()
  if (sub === 'past_due') return { cls: 'p-amber', text: 'Past due' }
  if (sub === 'cancelled' || sub === 'canceled') return { cls: 'p-red', text: 'Cancelled' }
  if (sub === 'trialing' || sub === 'trial') return { cls: 'p-cyan', text: 'Trial' }
  return { cls: 'p-green', text: 'Active' }
}
