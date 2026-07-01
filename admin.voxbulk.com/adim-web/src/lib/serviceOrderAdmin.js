/** Admin navigation + billing helpers for platform service orders. */

export function adminOrderViewPath(order) {
  const id = order?.id
  if (!id) return '/billing/service-orders'
  return `/operations/orders/${encodeURIComponent(id)}`
}

/** Timestamp for list sorting (prefer last activity). */
export function orderListSortTs(order) {
  const raw = order?.updated_at || order?.completed_at || order?.started_at || order?.created_at
  if (!raw) return 0
  const t = new Date(raw).getTime()
  return Number.isNaN(t) ? 0 : t
}

export function orderListSortKey(order) {
  return String(order?.reference_id || order?.campaign_id || order?.title || order?.id || '')
}

/** @param {'completed'|'running'|'paid'|'all'} workflow */
export function filterOrdersByWorkflow(rows, workflow = 'completed') {
  const list = Array.isArray(rows) ? rows : []
  if (workflow === 'all') return list
  return list.filter((o) => {
    const status = String(o.status || '').toLowerCase()
    const payment = String(o.payment_status || '').toLowerCase()
    if (workflow === 'completed') return status === 'completed'
    if (workflow === 'running') return ['running', 'paused', 'scheduled'].includes(status)
    if (workflow === 'paid') return payment === 'approved' && status !== 'draft'
    return true
  })
}

/**
 * @param {'amount_desc'|'amount_asc'|'date_desc'|'date_asc'|'name_asc'|'name_desc'|'order_asc'} sortBy
 */
export function sortServiceOrders(rows, sortBy = 'amount_desc') {
  const sorted = [...(Array.isArray(rows) ? rows : [])]
  sorted.sort((a, b) => {
    if (sortBy === 'amount_desc' || sortBy === 'amount_asc') {
      const diff = (Number(a.quote_total_pence) || 0) - (Number(b.quote_total_pence) || 0)
      if (diff !== 0) return sortBy === 'amount_desc' ? -diff : diff
      const dateDiff = orderListSortTs(a) - orderListSortTs(b)
      if (dateDiff !== 0) return sortBy === 'amount_desc' ? -dateDiff : dateDiff
      return orderListSortKey(a).localeCompare(orderListSortKey(b))
    }
    if (sortBy === 'date_asc') return orderListSortTs(a) - orderListSortTs(b)
    if (sortBy === 'date_desc') return orderListSortTs(b) - orderListSortTs(a)
    if (sortBy === 'name_desc') return String(b.title || '').localeCompare(String(a.title || ''))
    if (sortBy === 'order_asc') return orderListSortKey(a).localeCompare(orderListSortKey(b))
    if (sortBy === 'name_asc') return String(a.title || '').localeCompare(String(b.title || ''))
    return 0
  })
  return sorted
}

export const ORDER_PAYMENT_HELP =
  'Pay status: unpaid = not paid yet · approved = cleared to launch (wallet, DD, allowance, or cash approved) · pending_approval = customer marked cash, awaiting admin · rejected = cash declined. Workflow status (draft/running/completed) is separate from payment.'

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

export function orderDeliveryLabel(order) {
  const cfg = order?.config || {}
  const delivery = String(cfg.delivery || '').toLowerCase()
  if (delivery === 'ai_meeting') return 'Web interview (browser)'
  if (delivery === 'ai_call') return 'Phone AI call'
  const launch = order?.launch_billing || {}
  const channel = String(launch.channel || cfg.survey_channel || cfg.channel || order?.quote_survey_channel || '').toLowerCase()
  if (channel === 'ai_meeting' || channel === 'meeting') return 'Web interview (browser)'
  if (channel === 'whatsapp' || channel === 'wa') return 'WhatsApp'
  if (channel === 'ai_call' || channel === 'phone' || channel === 'call') return 'Phone AI call'
  return channel || '—'
}

/** Interview list/detail label — prefers session stats, falls back to order config. */
export function interviewFormatLabel(order) {
  const cfg = order?.config || {}
  const delivery = String(cfg.delivery || '').toLowerCase()
  const launchChannel = String(order?.launch_billing?.channel || '').toLowerCase()
  const sessions = order?.interview_sessions
  const fmt = String(sessions?.interview_format || '').toLowerCase()
  const sessionLabel = sessions?.interview_format_label

  if (delivery === 'ai_meeting' || launchChannel === 'ai_meeting' || launchChannel === 'meeting') {
    if (fmt === 'mixed') return sessionLabel || 'Phone + web'
    if (fmt === 'phone') return sessionLabel || 'Web interview'
    return sessionLabel || 'Web interview'
  }
  if (sessionLabel) return sessionLabel
  return orderDeliveryLabel(order)
}

/** Match order against free-text search (IDs, refs, names). */
export function orderMatchesSearch(order, query) {
  const q = String(query || '').trim().toLowerCase()
  if (!q) return true
  const haystack = [
    order?.id,
    order?.title,
    order?.org_name,
    order?.owner_email,
    order?.reference_id,
    order?.campaign_id,
    order?.service_code,
    order?.status,
    order?.status_label,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return haystack.includes(q)
}

/**
 * Generic column sort for admin order tables.
 * @param {Record<string, (row: any) => any>} accessors
 */
export function sortRowsByColumn(rows, column, asc, accessors = {}) {
  const get = accessors[column] || ((row) => row?.[column])
  const sorted = [...(Array.isArray(rows) ? rows : [])]
  sorted.sort((a, b) => {
    let va = get(a)
    let vb = get(b)
    if (va == null) va = ''
    if (vb == null) vb = ''
    if (typeof va === 'number' && typeof vb === 'number') {
      const diff = va - vb
      return asc ? diff : -diff
    }
    const na = Number(va)
    const nb = Number(vb)
    if (!Number.isNaN(na) && !Number.isNaN(nb) && String(va).trim() !== '' && String(vb).trim() !== '') {
      const diff = na - nb
      return asc ? diff : -diff
    }
    const cmp = String(va).localeCompare(String(vb), undefined, { numeric: true, sensitivity: 'base' })
    return asc ? cmp : -cmp
  })
  return sorted
}

export function nextColumnSort(currentField, currentAsc, field) {
  if (currentField === field) return { field, asc: !currentAsc }
  return { field, asc: true }
}

export function recipientSessionChannel(row, order) {
  const transport = String(row?.transport || '').toLowerCase()
  const channel = String(row?.call_channel || '').toLowerCase()
  if (transport === 'webrtc') return 'webrtc'
  if (channel === 'meeting') return 'meeting'
  const delivery = String(order?.config?.delivery || '').toLowerCase()
  if (delivery === 'ai_meeting') return 'meeting'
  return channel || 'ai_call'
}

export function orderHasBillableSessions(order) {
  const cfg = order?.config || {}
  const delivery = String(cfg.delivery || '').toLowerCase()
  if (delivery === 'ai_meeting' || delivery === 'ai_call') return true
  const launch = order?.launch_billing || {}
  const channel = String(launch.channel || cfg.survey_channel || cfg.channel || '').toLowerCase()
  if (['ai_call', 'phone', 'call'].includes(channel)) return true
  const recipients = Array.isArray(order?.recipients) ? order.recipients : []
  return recipients.some((r) => ['meeting', 'webrtc'].includes(recipientSessionChannel(r, order)))
}
