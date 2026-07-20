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

/** Demo KPI rows until Partner API ledger is live. */
export const DEMO_PARTNER_KPI = {
  totals: {
    connected: 3,
    total: 5,
    jobs: 128,
    completed: 96,
    gross: 864,
    remittance: 691.2,
    profit: 211.2,
  },
  rows: [
    {
      key: 'zoho',
      connection: 'connected',
      mode: 'live',
      jobs: 45,
      completed: 32,
      gross: 288,
      commission: 18,
      remittance: 236.16,
      cost: 160,
      profit: 76.16,
      lastActivity: '2h ago',
    },
    {
      key: 'breezy',
      connection: 'sandbox',
      mode: 'sandbox',
      jobs: 23,
      completed: 18,
      gross: 162,
      commission: 20,
      remittance: 129.6,
      cost: 90,
      profit: 39.6,
      lastActivity: '1d ago',
    },
    {
      key: 'workable',
      connection: 'none',
      mode: null,
      jobs: 0,
      completed: 0,
      gross: 0,
      commission: 18,
      remittance: 0,
      cost: 0,
      profit: 0,
      lastActivity: null,
    },
    {
      key: 'bullhorn',
      connection: 'error',
      mode: 'live',
      jobs: 60,
      completed: 46,
      gross: 414,
      commission: 22,
      remittance: 322.92,
      cost: 230,
      profit: 92.92,
      lastActivity: '15m ago',
    },
    {
      key: 'zapier',
      connection: 'connected',
      mode: 'sandbox',
      jobs: 0,
      completed: 0,
      gross: 0,
      commission: 18,
      remittance: 0,
      cost: 0,
      profit: 0,
      lastActivity: '3d ago',
    },
  ],
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
