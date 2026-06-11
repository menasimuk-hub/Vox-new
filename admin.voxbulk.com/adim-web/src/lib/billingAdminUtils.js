export const money = (pence, currency = 'GBP') => {
  const amount = Number(pence || 0) / 100
  try {
    return new Intl.NumberFormat('en-GB', { style: 'currency', currency: currency || 'GBP' }).format(amount)
  } catch {
    return `£${amount.toFixed(2)}`
  }
}

export const dateText = (value) =>
  value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'

export const dateShort = (value) =>
  value ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'

export function statusPillClass(status) {
  const s = String(status || '').toLowerCase()
  if (['active', 'paid', 'succeeded', 'processed', 'completed', 'approved'].includes(s)) return 'p-green'
  if (['pending', 'under_review', 'issued', 'open', 'collecting', 'trial'].includes(s)) return 'p-amber'
  if (['failed', 'rejected', 'past_due', 'cancelled', 'error'].includes(s)) return 'p-red'
  return 'p-cyan'
}

export function truncate(text, max = 40) {
  const s = String(text || '').trim()
  if (!s) return '—'
  return s.length > max ? `${s.slice(0, max)}…` : s
}
