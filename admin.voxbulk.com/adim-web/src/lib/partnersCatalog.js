/** Marketplace partner providers for Admin → Partners. */

export const PARTNER_PROVIDERS = [
  {
    key: 'zoho',
    label: 'Zoho Marketplace',
    short: 'Zoho',
    initials: 'ZH',
    portalUrl: 'https://marketplace.zoho.com/developer',
    partnerNameHeader: 'zoho',
    commissionDefault: 18,
    extraFields: 'zoho',
  },
  {
    key: 'breezy',
    label: 'Breezy HR',
    short: 'Breezy',
    initials: 'BR',
    portalUrl: 'https://breezy.hr/integrations/build',
    partnerNameHeader: 'breezy',
    commissionDefault: 20,
    extraFields: 'breezy',
  },
  {
    key: 'workable',
    label: 'Workable',
    short: 'Workable',
    initials: 'WK',
    portalUrl: 'https://www.workable.com/partners',
    partnerNameHeader: 'workable',
    commissionDefault: 18,
    extraFields: 'workable',
  },
  {
    key: 'bullhorn',
    label: 'Bullhorn Marketplace',
    short: 'Bullhorn',
    initials: 'BH',
    portalUrl: 'https://marketplace.bullhorn.com/developers',
    partnerNameHeader: 'bullhorn',
    commissionDefault: 22,
    extraFields: 'bullhorn',
  },
  {
    key: 'zapier',
    label: 'Zapier',
    short: 'Zapier',
    initials: 'ZP',
    portalUrl: 'https://developer.zapier.com',
    partnerNameHeader: 'zapier',
    commissionDefault: 18,
    extraFields: 'zapier',
  },
]

export function getPartnerProvider(key) {
  const k = String(key || '').trim().toLowerCase()
  return PARTNER_PROVIDERS.find((p) => p.key === k) || null
}

/** Empty KPI until Partner API ledger is connected. */
export function emptyPartnerKpi() {
  return {
    totals: {
      connected: 0,
      total: PARTNER_PROVIDERS.length,
      jobs: 0,
      completed: 0,
      gross: 0,
      remittance: 0,
      profit: 0,
    },
    rows: PARTNER_PROVIDERS.map((p) => ({
      key: p.key,
      connection: 'none',
      mode: null,
      jobs: 0,
      completed: 0,
      gross: 0,
      commission: p.commissionDefault,
      remittance: 0,
      cost: 0,
      profit: 0,
      lastActivity: null,
    })),
  }
}

export function moneyGbp(n) {
  const v = Number(n) || 0
  return `£${v.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function connectionBadge(connection) {
  switch (connection) {
    case 'connected':
      return { cls: 'partners-badge-green', text: '● Connected' }
    case 'sandbox':
      return { cls: 'partners-badge-amber', text: 'Sandbox only' }
    case 'error':
      return { cls: 'partners-badge-red', text: '● Error' }
    default:
      return { cls: 'partners-badge-grey', text: 'Not configured' }
  }
}

export function modeBadge(mode) {
  if (mode === 'live') return { cls: 'partners-badge-live', text: 'Live' }
  if (mode === 'sandbox') return { cls: 'partners-badge-sandbox', text: 'Sandbox' }
  return { cls: 'partners-badge-grey', text: '—' }
}
