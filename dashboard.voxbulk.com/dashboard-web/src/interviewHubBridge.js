import { apiFetch, getAccessToken } from './lib/api.js'

const hub = {
  orders: [],
  tab: 'live',
}

function api(path, options = {}) {
  return apiFetch(path, options)
}

function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function fmtSchedule(start, end) {
  if (!start) return 'Not set'
  const s = new Date(start)
  const e = end ? new Date(end) : null
  const fmt = (dt) =>
    dt.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  if (e && !Number.isNaN(e.getTime())) return `${fmt(s)} → ${fmt(e)}`
  return fmt(s)
}

function intakeSourceLabel(order) {
  const sources = new Set((order.recipients || []).map((r) => r.intake_source).filter(Boolean))
  if (sources.has('email') && (sources.has('cv') || sources.has('csv') || sources.has('merged'))) return 'Upload + email'
  if (sources.has('email')) return 'Email careers@voxbulk.com'
  if (sources.size) return 'File upload'
  return '—'
}

function progressLabel(order) {
  const total = Number(order.recipient_count || 0)
  if (!total) return '—'
  const done = Number(order.report?.completed || order.report?.reached || 0)
  if (order.status === 'running' && done) return `${done} of ${total} called`
  return `${total} candidates`
}

function renderOrderRow(order) {
  const ref = order.reference_id ? `<span class="bdg bb" style="margin-left:6px">${esc(order.reference_id)}</span>` : ''
  const click = order.service_code === 'interview' ? `window.openInterviewResults('${order.id}')` : ''
  return `<div class="proj-row" onclick="${click}">
    <div class="proj-ic ci-b"><i class="ti ti-briefcase"></i></div>
    <div class="proj-info">
      <div class="proj-name">${esc(order.title || 'Interview task')}${ref}</div>
      <div class="proj-meta">${esc(order.status_label || order.status)} · ${esc(fmtSchedule(order.scheduled_start_at, order.scheduled_end_at))} · ${esc(intakeSourceLabel(order))} · ${esc(progressLabel(order))}</div>
    </div>
    <span class="stat-wait">${esc(order.status_label || order.status)}</span>
  </div>`
}

function switchTab(tab) {
  hub.tab = tab
  document.querySelectorAll('#int-tabs .tb').forEach((el) => {
    el.classList.toggle('on', el.getAttribute('data-int-tab') === tab)
  })
  document.getElementById('int-panel-live')?.classList.toggle('on', tab === 'live')
  document.getElementById('int-panel-finished')?.classList.toggle('on', tab === 'finished')
  renderLists()
}

function renderLists() {
  const live = hub.orders.filter((o) => o.is_live)
  const finished = hub.orders.filter((o) => o.is_finished)
  const liveHost = document.getElementById('int-live-orders')
  const finHost = document.getElementById('int-finished-orders')
  if (liveHost) liveHost.innerHTML = live.map(renderOrderRow).join('')
  if (finHost) finHost.innerHTML = finished.map(renderOrderRow).join('')
  const liveEmpty = document.getElementById('int-live-empty')
  const finEmpty = document.getElementById('int-finished-empty')
  if (liveEmpty) liveEmpty.style.display = live.length ? 'none' : ''
  if (finEmpty) finEmpty.style.display = finished.length ? 'none' : ''
}

export async function loadInterviewOrders() {
  if (!getAccessToken()) return
  hub.loading = true
  try {
    hub.orders = (await api('/service-orders?service_code=interview')) || []
    renderLists()
  } catch {
    /* keep static */
  } finally {
    hub.loading = false
  }
}

function bindTabs() {
  document.querySelectorAll('#int-tabs .tb').forEach((tab) => {
    tab.addEventListener('click', () => switchTab(tab.getAttribute('data-int-tab') || 'live'))
  })
}

export function initInterviewHubBridge() {
  window.reloadInterviewHub = loadInterviewOrders
  bindTabs()
  void loadInterviewOrders()
}
