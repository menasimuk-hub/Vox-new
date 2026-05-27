import { apiFetch, getAccessToken } from './lib/api.js'
import { confirmDialog } from './modalBridge.js'
import { esc, fmtScheduleRange, renderCampaignTable } from './campaignListUi.js'

const hub = {
  orders: [],
  tab: 'live',
  selectedId: null,
}

function api(path, options = {}) {
  return apiFetch(path, options)
}

function intakeSourceLabel(order) {
  const sources = new Set((order.recipients || []).map((r) => r.intake_source).filter(Boolean))
  if (sources.has('email') && (sources.has('cv') || sources.has('csv') || sources.has('merged'))) return 'Upload + email'
  if (sources.has('email')) return 'Email'
  if (sources.size) return 'File upload'
  return '—'
}

function canEditOrder(order) {
  return Boolean(order?.is_live && !['running', 'paused'].includes(order.status))
}

function canDeleteOrder(order) {
  return Boolean(order?.is_live && !['running', 'paused'].includes(order.status))
}

function renderTableRow(order) {
  const editBtn = canEditOrder(order)
    ? `<button type="button" class="btn bsm btng int-hub-act" data-int-action="edit" data-order-id="${esc(order.id)}" title="Edit"><i class="ti ti-edit"></i></button>`
    : ''
  const deleteBtn = canDeleteOrder(order)
    ? `<button type="button" class="btn bsm btnr int-hub-act" data-int-action="delete" data-order-id="${esc(order.id)}" title="Delete"><i class="ti ti-trash"></i></button>`
    : ''
  const archiveBtn =
    order.is_finished && !order.is_archived
      ? `<button type="button" class="btn bsm int-hub-act" data-int-action="archive" data-order-id="${esc(order.id)}" title="Archive"><i class="ti ti-archive"></i></button>`
      : ''
  return `<tr class="int-hub-row" data-order-id="${esc(order.id)}">
    <td><strong>${esc(order.title || 'Interview task')}</strong>${order.reference_id ? `<span class="bdg bb" style="margin-left:6px">${esc(order.reference_id)}</span>` : ''}</td>
    <td><span class="bdg ba">${esc(order.status_label || order.status)}</span></td>
    <td class="muted">${esc(fmtScheduleRange(order.scheduled_start_at, order.scheduled_end_at))} · ${esc(intakeSourceLabel(order))}</td>
    <td class="hub-camp-actions">${editBtn}${archiveBtn}${deleteBtn}</td>
  </tr>`
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
  const setPanel = (hostId, emptyId, rows, emptyMsg) => {
    const host = document.getElementById(hostId)
    const empty = document.getElementById(emptyId)
    if (host) {
      host.innerHTML = renderCampaignTable(rows.map(renderTableRow).join(''), emptyMsg)
    }
    if (empty) empty.style.display = rows.length ? 'none' : ''
  }
  setPanel('int-live-orders', 'int-live-empty', live, 'No live interviews — use Create new interview in the menu.')
  setPanel('int-finished-orders', 'int-finished-empty', finished, 'No finished interviews yet.')
  setPanel('int-archived-orders', 'int-archived-empty', archived, 'No archived interviews.')
}

async function handleRowAction(orderId, action) {
  if (!orderId) return
  if (action === 'archive') {
    const ok = await confirmDialog({
      title: 'Archive interview?',
      message: 'This removes the campaign from live and finished lists.',
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
    if (typeof window.deleteInterviewOrder === 'function') await window.deleteInterviewOrder(orderId)
    return
  }
  if (action === 'edit') {
    if (typeof window.openInterviewDraft === 'function') await window.openInterviewDraft(orderId)
  }
}

function bindListClicks() {
  ;['int-live-orders', 'int-finished-orders', 'int-archived-orders'].forEach((hostId) => {
    document.getElementById(hostId)?.addEventListener('click', (event) => {
      const actionBtn = event.target.closest('.int-hub-act')
      if (actionBtn) {
        event.stopPropagation()
        void handleRowAction(actionBtn.getAttribute('data-order-id'), actionBtn.getAttribute('data-int-action'))
        return
      }
      const row = event.target.closest('.int-hub-row')
      if (!row) return
      void handleRowAction(row.getAttribute('data-order-id'), 'edit')
    })
  })
}

export function setInterviewHubSelection(orderId) {
  hub.selectedId = orderId || null
}

export async function loadInterviewOrders() {
  if (!getAccessToken()) return
  try {
    hub.orders = (await api('/service-orders?service_code=interview')) || []
    renderLists()
  } catch {
    /* keep */
  }
}

export function initInterviewHubBridge() {
  window.reloadInterviewHub = loadInterviewOrders
  window.setInterviewHubSelection = setInterviewHubSelection
  document.querySelectorAll('#int-tabs .tb').forEach((tab) => {
    tab.addEventListener('click', () => switchTab(tab.getAttribute('data-int-tab') || 'live'))
  })
  bindListClicks()
  void loadInterviewOrders()
}
