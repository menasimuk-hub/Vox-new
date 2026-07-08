export const LINE_HUE = { voxbulk: 212, customer_feedback: 164, campaign: 30 }

export const TIER_RANK = {
  voxbulk: { payg: 0, starter: 1, pro: 2, business: 3, enterprise: 4 },
  customer_feedback: { starter: 0, growth: 1, pro: 2, business: 3 },
  campaign: { survey: 0, interview: 1, ats: 2, appt: 3 },
}

export const TIER_MAX = { voxbulk: 4, customer_feedback: 3, campaign: 3 }

export const REGION_COLORS = {
  US: { bg: '#E4EDF7', text: '#2F5C8A' },
  GB: { bg: '#F7E4EC', text: '#973A5C' },
  EU: { bg: '#EFE7F9', text: '#5B3F8A' },
  CA: { bg: '#FBE9DE', text: '#A1541F' },
  AU: { bg: '#E3F0E6', text: '#2E6B3E' },
  Global: { bg: '#F1ECDD', text: '#776E5B' },
}

export const GROUP_ORDER = ['voxbulk', 'customer_feedback', 'campaign']

export const FILTER_OPTIONS = [
  { key: 'all', label: 'All' },
  { key: 'voxbulk', label: 'Core platform' },
  { key: 'customer_feedback', label: 'Customer Feedback' },
  { key: 'campaign', label: 'Campaign packs' },
]

export function tierColors(row) {
  const group = row.product_line || 'voxbulk'
  const hue = LINE_HUE[group] ?? 200
  const rank = TIER_RANK[group]?.[row.tier_key] ?? 0
  const max = TIER_MAX[group] ?? 1
  const t = max === 0 ? 0 : rank / max
  return {
    bar: `hsl(${hue}, 42%, ${58 - t * 20}%)`,
    chipBg: `hsl(${hue}, 46%, ${93 - t * 10}%)`,
    chipText: `hsl(${hue}, 40%, ${28 - t * 6}%)`,
  }
}

export function groupIconBg(group) {
  const hue = LINE_HUE[group] ?? 200
  return `hsl(${hue}, 50%, 92%)`
}

export function groupTextColor(group) {
  const hue = LINE_HUE[group] ?? 200
  return `hsl(${hue}, 45%, 36%)`
}

export function formatPriceCell(row) {
  if (row.product_type === 'campaign' || row.price_display == null) {
    return { text: '—', gap: false }
  }
  if (row.is_enterprise) {
    return { text: 'Custom', gap: false }
  }
  const suffix = row.interval === 'yearly' ? '/yr' : '/mo'
  return {
    text: `${row.price_display}${suffix}`,
    gap: Boolean(row.price_gap),
  }
}

export function tierSummaryRows(rows) {
  const byTier = new Map()
  for (const row of rows) {
    const key = row.tier_key || row.code
    if (!byTier.has(key)) byTier.set(key, [])
    byTier.get(key).push(row)
  }
  return [...byTier.entries()].map(([tierKey, tierRows]) => {
    const prices = tierRows.map((r) => r.price_display).filter(Boolean)
    const active = tierRows.filter((r) => r.is_active).length
    return {
      tierKey,
      name: tierRows[0]?.name || tierKey,
      rows: tierRows,
      regionCount: tierRows.length,
      activeCount: active,
      priceRange: prices.length ? prices : ['—'],
      anyGap: tierRows.some((r) => r.price_gap),
    }
  })
}

export function filterRows(rows, { filter, query, gapsOnly }) {
  let out = rows
  if (filter !== 'all') out = out.filter((r) => r.product_line === filter)
  const q = String(query || '').trim().toLowerCase()
  if (q) {
    out = out.filter(
      (r) =>
        String(r.name || '').toLowerCase().includes(q) ||
        String(r.code || '').toLowerCase().includes(q) ||
        String(r.picker_label || '').toLowerCase().includes(q),
    )
  }
  if (gapsOnly) out = out.filter((r) => r.price_gap)
  return out
}

export function computeStats(rows) {
  const subs = rows.filter((r) => r.product_type === 'subscription')
  return {
    total: rows.length,
    active: rows.filter((r) => r.is_active).length,
    stopped: rows.filter((r) => !r.is_active).length,
    gaps: rows.filter((r) => r.price_gap).length,
    activeSubs: subs.filter((r) => r.is_active).length,
  }
}
