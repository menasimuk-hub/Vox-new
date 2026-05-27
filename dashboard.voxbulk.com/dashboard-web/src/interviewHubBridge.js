import { apiFetch, getAccessToken } from './lib/api.js'
import { confirmDialog } from './modalBridge.js'

const hub = {
  orders: [],
  tab: 'live',
  selectedId: null,
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
  const cv = order.cv_collection
  if (cv?.enabled && !cv?.collection_complete) {
    return `${total} candidates · CV email open`
  }
  if (cv?.enabled && cv?.collection_complete) {
    return `${total} candidates · CV email closed`
  }
  return `${total} candidates`
}

function canEditOrder(order) {
  return Boolean(order?.is_live && !['running', 'paused'].includes(order.status))
}

function canViewResults(order) {
  return Boolean(
    order?.is_finished ||
      ['running', 'paused', 'completed', 'cancelled'].includes(String(order?.status || '')),
  )
}

function canDeleteOrder(order) {
  return Boolean(order?.is_live && !['running', 'paused'].includes(order.status))
}

function primaryAction(order) {
  if (canViewResults(order) && !canEditOrder(order)) return 'results'
  if (canEditOrder(order)) return 'edit'
  if (canViewResults(order)) return 'results'
  return 'edit'
}

function renderOrderRow(order) {
  const ref = order.reference_id ? `<span class="bdg bb" style="margin-left:6px">${esc(order.reference_id)}</span>` : ''
  const selected = hub.selectedId === order.id ? ' int-hub-row-selected' : ''
  const editBtn = canEditOrder(order)
    ? `<button type="button" class="btn bsm btng int-hub-act" data-int-action="edit" data-order-id="${esc(order.id)}" title="Edit draft"><i class="ti ti-edit"></i></button>`
    : ''
  const resultsBtn = canViewResults(order)
    ? `<button type="button" class="btn bsm int-hub-act" data-int-action="results" data-order-id="${esc(order.id)}" title="View results"><i class="ti ti-chart-bar"></i></button>`
    : ''
  const deleteBtn = canDeleteOrder(order)
    ? `<button type="button" class="btn bsm btnr int-hub-act" data-int-action="delete" data-order-id="${esc(order.id)}" title="Delete"><i class="ti ti-trash"></i></button>`
    : ''
  const archiveBtn =
    order.is_finished && !order.is_archived
      ? `<button type="button" class="btn bsm int-hub-act" data-int-action="archive" data-order-id="${esc(order.id)}" title="Archive"><i class="ti ti-archive"></i></button>`
      : ''
  return `<div class="proj-row int-hub-row${selected}" data-order-id="${esc(order.id)}" data-int-primary="${primaryAction(order)}">
    <div class="proj-ic ci-b"><i class="ti ti-briefcase"></i></div>
    <div class="proj-info">
      <div class="proj-name">${esc(order.title || 'Interview task')}${ref}</div>
      <div class="proj-meta">${esc(order.status_label || order.status)} · ${esc(fmtSchedule(order.scheduled_start_at, order.scheduled_end_at))} · ${esc(intakeSourceLabel(order))} · ${esc(progressLabel(order))}</div>
    </div>
    <div style="display:flex;align-items:center;gap:6px;flex-shrink:0">
      ${editBtn}${resultsBtn}${archiveBtn}${deleteBtn}
      <span class="stat-wait">${esc(order.status_label || order.status)}</span>
    </div>
  </div>`
}

function switchTab(tab) {
  hub.tab = tab
  document.querySelectorAll('#int-tabs .tb').forEach((el) => {
    el.classList.toggle('on', el.getAttribute('data-int-tab') === tab)
  })
  document.getElementById('int-panel-live')?.classList.toggle('on', tab === 'live')
  document.getElementById('int-panel-finished')?.classList.toggle('on', tab === 'finished')
  document.getElementById('int-panel-archived')?.classList.toggle('on', tab === 'archived')
  renderLists()
}

function renderLists() {
  const live = hub.orders.filter((o) => o.is_live)
  const finished = hub.orders.filter((o) => o.is_finished)
  const archived = hub.orders.filter((o) => o.is_archived)
  const liveHost = document.getElementById('int-live-orders')
  const finHost = document.getElementById('int-finished-orders')
  const archHost = document.getElementById('int-archived-orders')
  if (liveHost) liveHost.innerHTML = live.map(renderOrderRow).join('')
  if (finHost) finHost.innerHTML = finished.map(renderOrderRow).join('')
  if (archHost) archHost.innerHTML = archived.map(renderOrderRow).join('')
  const liveEmpty = document.getElementById('int-live-empty')
  const finEmpty = document.getElementById('int-finished-empty')
  const archEmpty = document.getElementById('int-archived-empty')
  if (liveEmpty) liveEmpty.style.display = live.length ? 'none' : ''
  if (finEmpty) finEmpty.style.display = finished.length ? 'none' : ''
  if (archEmpty) archEmpty.style.display = archived.length ? 'none' : ''
}

async function handleRowAction(orderId, action) {
  if (!orderId) return
  if (action === 'archive') {
    const ok = await confirmDialog({
      title: 'Archive interview?',
      message: 'This removes the campaign from live and finished lists. You can still find it under Archived.',
      okLabel: 'Archive',
    })
    if (!ok) return
    try {
      await api(`/service-orders/${encodeURIComponent(orderId)}/archive`, { method: 'POST' })
      window.toast?.('Interview archived', 'tg')
      await loadInterviewOrders()
      if (typeof window.applyDashboardServices === 'function') window.applyDashboardServices()
    } catch (e) {
      window.toast?.(e.message || 'Archive failed', 'tr')
    }
    return
  }
  if (action === 'delete') {
    if (typeof window.deleteInterviewOrder === 'function') {
      await window.deleteInterviewOrder(orderId)
    }
    return
  }
  if (action === 'results') {
    if (typeof window.openInterviewResults === 'function') {
      await window.openInterviewResults(orderId)
    }
    return
  }
  if (action === 'edit') {
    if (typeof window.openInterviewDraft === 'function') {
      await window.openInterviewDraft(orderId)
    }
  }
}

function bindListClicks() {
  const hosts = ['int-live-orders', 'int-finished-orders', 'int-archived-orders']
  hosts.forEach((hostId) => {
    document.getElementById(hostId)?.addEventListener('click', (event) => {
      const actionBtn = event.target.closest('.int-hub-act')
      if (actionBtn) {
        event.stopPropagation()
        void handleRowAction(
          actionBtn.getAttribute('data-order-id'),
          actionBtn.getAttribute('data-int-action'),
        )
        return
      }
      const row = event.target.closest('.int-hub-row')
      if (!row) return
      const orderId = row.getAttribute('data-order-id')
      const action = row.getAttribute('data-int-primary') || 'edit'
      void handleRowAction(orderId, action)
    })
  })
}

export function setInterviewHubSelection(orderId) {
  hub.selectedId = orderId || null
  renderLists()
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
  window.setInterviewHubSelection = setInterviewHubSelection
  bindTabs()
  bindListClicks()
  void loadInterviewOrders()
}
