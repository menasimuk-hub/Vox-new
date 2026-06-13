export function shekel(agorot) {
  const n = Number(agorot || 0)
  return `${(n / 100).toFixed(2)} ₪`
}

export function abuuStatusClass(status) {
  const s = String(status || '').toLowerCase()
  if (['paid', 'preparing', 'delivered', 'paid_manual'].includes(s)) return 'pill ok'
  if (['pending_payment', 'pending_manual', 'assigned'].includes(s)) return 'pill warn'
  if (['cancelled', 'failed'].includes(s)) return 'pill bad'
  return 'pill'
}

export function dateText(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString()
}
