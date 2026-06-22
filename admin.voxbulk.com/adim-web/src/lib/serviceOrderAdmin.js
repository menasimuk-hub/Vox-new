/** Admin navigation + billing helpers for platform service orders. */

export function adminOrderViewPath(order) {
  const id = order?.id
  if (!id) return '/billing/service-orders'
  return `/operations/orders/${encodeURIComponent(id)}`
}

export function formatDurationSeconds(secs) {
  const n = Number(secs)
  if (!Number.isFinite(n) || n <= 0) return '—'
  const mins = Math.floor(n / 60)
  const rem = Math.floor(n % 60)
  if (mins <= 0) return `${rem}s`
  return `${mins}m ${String(rem).padStart(2, '0')}s`
}

export function billableMinutesFromSeconds(secs) {
  const n = Number(secs)
  if (!Number.isFinite(n) || n <= 0) return 0
  return Math.max(1, Math.ceil(n / 60))
}

export function orderEstimatedDurationMin(order) {
  const launch = order?.launch_billing || {}
  const cfg = order?.config || {}
  const fromQuote = (order?.quote_breakdown || []).find((line) => line?.kind === 'per_minute')
  const raw =
    launch.duration_minutes ??
    cfg.duration_minutes ??
    cfg.estimated_duration_min ??
    cfg.expected_duration_minutes ??
    fromQuote?.duration_minutes ??
    null
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : null
}

export function orderCallUsageSummary(order) {
  const recipients = Array.isArray(order?.recipients) ? order.recipients : []
  let totalSeconds = 0
  let connected = 0
  let billableMinutes = 0
  for (const row of recipients) {
    const secs = Number(row?.duration_seconds)
    if (!Number.isFinite(secs) || secs <= 0) continue
    totalSeconds += secs
    connected += 1
    billableMinutes += billableMinutesFromSeconds(secs)
  }
  return { totalSeconds, connected, billableMinutes }
}
