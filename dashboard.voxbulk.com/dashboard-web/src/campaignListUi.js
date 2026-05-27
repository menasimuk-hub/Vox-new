export function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function fmtScheduleRange(start, end) {
  if (!start) return 'Not scheduled'
  const s = new Date(start)
  const e = end ? new Date(end) : null
  const fmt = (dt) =>
    dt.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  if (e && !Number.isNaN(e.getTime())) return `${fmt(s)} → ${fmt(e)}`
  return fmt(s)
}

export function isResultsReady(order, serviceCode) {
  if (order.is_archived) return false
  if (serviceCode === 'interview') {
    return Boolean(order.is_finished || order.status === 'completed')
  }
  return Boolean(order.is_finished || order.status === 'completed')
}

export function pendingMeta(order, serviceCode) {
  if (isResultsReady(order, serviceCode)) return null
  if (serviceCode === 'interview') {
    return fmtScheduleRange(order.scheduled_start_at, order.scheduled_end_at)
  }
  return order.status_label || order.status || '—'
}

export function renderCampaignTable(rowsHtml, emptyMessage) {
  if (!rowsHtml) {
    return `<div class="empty-state" style="padding:16px 0"><div class="es-sub">${esc(emptyMessage)}</div></div>`
  }
  return `<div class="hub-table-wrap"><table class="res-table hub-camp-table">
    <thead><tr>
      <th>Campaign</th>
      <th>Status</th>
      <th>Schedule / progress</th>
      <th class="hub-camp-actions">Actions</th>
    </tr></thead>
    <tbody>${rowsHtml}</tbody>
  </table></div>`
}
