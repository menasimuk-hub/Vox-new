import { apiFetch, getAccessToken } from './lib/api.js'
import { confirmDialog } from './modalBridge.js'
import { surveyRespondedCount, surveyFailedCount } from './surveyUtils.js'

const hub = {
  orders: [],
  tab: 'live',
  selectedId: null,
  selectedOrder: null,
  loading: false,
  searchQuery: '',
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

function fmtSchedule(iso) {
  if (!iso) return 'Not set'
  const dt = new Date(iso)
  if (Number.isNaN(dt.getTime())) return iso
  return dt.toLocaleString(undefined, {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function toDatetimeLocal(iso) {
  if (!iso) return ''
  const dt = new Date(iso)
  if (Number.isNaN(dt.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`
}

function fromDatetimeLocal(value) {
  if (!value) return null
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return null
  return dt.toISOString()
}

function statusBadgeClass(order) {
  if (order.status === 'running') return 'stat-live'
  if (order.status === 'completed') return 'stat-done'
  if (order.payment_status === 'rejected') return 'stat-fail'
  return 'stat-wait'
}

function renderTrendBars(items, emptyText) {
  if (!items.length) return `<div class="muted" style="font-size:12px;padding:8px 0">${esc(emptyText)}</div>`
  return items
    .map(
      (item) => `<div class="sur-trend-bar">
      <div class="lbl" title="${esc(item.label)}">${esc(item.label)}</div>
      <div class="track"><div class="fill" style="width:${Math.max(0, Math.min(100, item.pct))}%"></div></div>
      <div class="val">${item.pct}%</div>
    </div>`,
    )
    .join('')
}

function renderHubTrend(orders) {
  const host = document.getElementById('sur-trend-chart')
  if (!host) return
  const active = orders.filter((o) => ['running', 'paused', 'scheduled', 'completed'].includes(o.status))
  const items = active.slice(0, 5).map((o) => {
    const sent = surveyRespondedCount(o.report)
    const total = Number(o.recipient_count || 0)
    const pct = total > 0 ? Math.round((sent / total) * 100) : 0
    return { label: o.title, pct }
  })
  host.innerHTML = renderTrendBars(items, 'No response data yet.')
}

function paymentLabel(order) {
  if (order.payment_status === 'rejected') return 'Payment failed'
  if (order.payment_status === 'pending_approval') return 'Pending approval'
  if (['quoted', 'awaiting_payment', 'draft'].includes(order.status) && order.payment_status !== 'approved') {
    return 'Quoted'
  }
  if (order.status === 'scheduled' || (order.payment_status === 'approved' && ['paid', 'scheduled'].includes(order.status))) {
    return 'Scheduled'
  }
  if (order.is_finished || order.status === 'completed') return 'Finished'
  if (order.status === 'running') return 'Live'
  if (order.status === 'paused') return 'Paused'
  return order.status_label || order.status || '—'
}

function matchesSearch(order, query) {
  const q = String(query || '').trim().toLowerCase()
  if (!q) return true
  const company = order.config?.organisation_name || order.config?.clinic_name || ''
  return (
    String(order.title || '').toLowerCase().includes(q) ||
    String(company).toLowerCase().includes(q)
  )
}

function renderOrderRow(order) {
  const na = order.next_action || {}
  const hint = na.hint ? `<div class="proj-meta" style="color:var(--red);margin-top:2px">${esc(na.hint)}</div>` : ''
  const actionChip = na.label
    ? `<span class="bdg ${order.payment_status === 'rejected' ? 'br' : 'ba'}" style="margin-left:8px">${esc(na.label)}</span>`
    : ''
  const payChip = `<span class="bdg ${order.payment_status === 'rejected' ? 'br' : order.is_finished ? 'bg' : 'ba'}" style="margin-left:6px">${esc(paymentLabel(order))}</span>`
  const dispatch =
    order.report && order.status === 'running'
      ? ` · ${surveyRespondedCount(order.report)} sent${order.report.failed ? `, ${order.report.failed} failed` : ''}`
      : ''
  return `<div class="proj-row" data-survey-order-id="${order.id}">
    <div class="proj-ic ci-b"><i class="ti ti-clipboard-list"></i></div>
    <div class="proj-info">
      <div class="proj-name">${esc(order.title)}${payChip}${actionChip}</div>
      <div class="proj-meta">${order.recipient_count} contacts · ${order.quote_total_gbp}${dispatch}</div>
      ${hint}
    </div>
    <span class="${statusBadgeClass(order)}">${esc(order.status_label || order.status)}</span>
  </div>`
}

function computeKpis(orders) {
  const live = orders.filter((o) => o.is_live)
  const finished = orders.filter((o) => o.is_finished)
  const quoted = orders.filter(
    (o) =>
      o.is_live &&
      ['draft', 'quoted', 'awaiting_payment'].includes(o.status) &&
      ['unpaid', 'rejected'].includes(o.payment_status),
  )
  const failed = orders.filter((o) => o.payment_status === 'rejected')
  const scheduledToday = orders.filter((o) => {
    if (!o.scheduled_start_at) return false
    const d = new Date(o.scheduled_start_at)
    const now = new Date()
    return d.toDateString() === now.toDateString()
  })
  return { live, finished, quoted, failed, scheduledToday }
}

function renderKpis(orders) {
  const k = computeKpis(orders)
  const set = (id, val) => {
    const el = document.getElementById(id)
    if (el) el.textContent = String(val)
  }
  set('sur-kpi-live', k.live.length)
  set('sur-kpi-finished', k.finished.length)
  set('sur-kpi-quoted', k.quoted.length)
  set('sur-kpi-failed', k.failed.length)
  const sub = document.getElementById('sur-kpi-failed-sub')
  if (sub) sub.textContent = k.failed.length ? 'Retry payment on detail page' : 'None'
  const schedSub = document.getElementById('sur-kpi-live-sub')
  if (schedSub) schedSub.textContent = `${k.scheduledToday.length} scheduled today`
}

function renderLiveBanner(orders) {
  const banner = document.getElementById('sur-live-banner')
  if (!banner) return
  const running = orders.find((o) => o.status === 'running' || o.status === 'paused')
  if (!running) {
    banner.style.display = 'none'
    return
  }
  banner.style.display = 'flex'
  const title = document.getElementById('sur-live-banner-title')
  const sub = document.getElementById('sur-live-banner-sub')
  if (title) title.textContent = running.title
  if (sub) {
    const sent = surveyRespondedCount(running.report)
    const total = running.recipient_count || 0
    sub.textContent = `${sent} of ${total} responded · ${running.status === 'paused' ? 'Paused' : 'Live now'}`
  }
  banner.dataset.orderId = running.id
}

function renderLists(orders) {
  const filtered = orders.filter((o) => matchesSearch(o, hub.searchQuery))
  const live = filtered.filter((o) => o.is_live)
  const finished = filtered.filter((o) => o.is_finished)
  const liveHost = document.getElementById('sur-live-orders')
  const finHost = document.getElementById('sur-finished-orders')
  const liveEmpty = document.getElementById('sur-live-empty')
  const finEmpty = document.getElementById('sur-finished-empty')
  if (liveHost) liveHost.innerHTML = live.map(renderOrderRow).join('')
  if (finHost) finHost.innerHTML = finished.map(renderOrderRow).join('')
  if (liveEmpty) liveEmpty.style.display = live.length ? 'none' : 'block'
  if (finEmpty) finEmpty.style.display = finished.length ? 'none' : 'block'
  renderKpis(orders)
  renderLiveBanner(orders)
  renderHubTrend(orders)
}

function switchTab(tab) {
  hub.tab = tab
  document.querySelectorAll('#sur-tabs .tb').forEach((el) => {
    el.classList.toggle('on', el.dataset.surTab === tab)
  })
  document.getElementById('sur-panel-live')?.classList.toggle('on', tab === 'live')
  document.getElementById('sur-panel-finished')?.classList.toggle('on', tab === 'finished')
}

async function loadSurveyOrders() {
  if (!getAccessToken()) return
  hub.loading = true
  try {
    const rows = await api('/service-orders?service_code=survey')
    hub.orders = Array.isArray(rows) ? rows : []
    renderLists(hub.orders)
  } catch {
    /* keep previous */
  } finally {
    hub.loading = false
  }
}

function bindTabs() {
  document.querySelectorAll('#sur-tabs .tb').forEach((tab) => {
    tab.addEventListener('click', () => switchTab(tab.dataset.surTab || 'live'))
  })
}

function bindListClicks() {
  document.getElementById('sur-live-orders')?.addEventListener('click', onListClick)
  document.getElementById('sur-finished-orders')?.addEventListener('click', onListClick)
}

function onListClick(event) {
  const row = event.target.closest?.('[data-survey-order-id]')
  if (!row) return
  void openSurveyDetail(row.dataset.surveyOrderId)
}

function showDetailPanel(show) {
  document.getElementById('sur-detail-loading').style.display = show === 'loading' ? 'flex' : 'none'
  document.getElementById('sur-detail-error').style.display = show === 'error' ? 'flex' : 'none'
  document.getElementById('sur-detail-content').style.display = show === 'content' ? 'block' : 'none'
}

function setBtnVisible(id, visible) {
  const el = document.getElementById(id)
  if (el) el.style.display = visible ? '' : 'none'
}

function toggleInlineEdit(show) {
  const panel = document.getElementById('sur-detail-inline-edit')
  if (panel) panel.style.display = show ? 'block' : 'none'
}

function renderDetailBilling(order) {
  const host = document.getElementById('sur-detail-billing')
  if (!host) return
  const method = order.payment_method || 'Not selected'
  const status =
    order.payment_status === 'rejected'
      ? 'Failed — retry payment'
      : order.payment_status === 'pending_approval'
        ? 'Pending admin approval'
        : order.payment_status === 'approved'
          ? 'Paid'
          : 'Unpaid'
  host.innerHTML = `
    <div><strong>Amount:</strong> ${esc(order.quote_total_gbp || '£0.00')}</div>
    <div><strong>Method:</strong> ${esc(method)}</div>
    <div><strong>Status:</strong> ${esc(status)}</div>
    ${order.payment_note ? `<div><strong>Note:</strong> ${esc(order.payment_note)}</div>` : ''}
    ${order.admin_decision_note ? `<div><strong>Admin:</strong> ${esc(order.admin_decision_note)}</div>` : ''}
  `
}

function renderDetailTrend(order) {
  const host = document.getElementById('sur-detail-trend')
  if (!host) return
  const sent = surveyRespondedCount(order.report)
  const failed = surveyFailedCount(order.report)
  const pending = Math.max(0, Number(order.recipient_count || 0) - sent - failed)
  const total = sent + failed + pending || 1
  host.innerHTML = renderTrendBars(
    [
      { label: 'Responded', pct: Math.round((sent / total) * 100) },
      { label: 'Failed', pct: Math.round((failed / total) * 100) },
      { label: 'Pending', pct: Math.round((pending / total) * 100) },
    ],
    'No calls yet.',
  )
}

function renderDetail(order) {
  hub.selectedId = order.id
  hub.selectedOrder = order
  showDetailPanel('content')
  toggleInlineEdit(false)
  document.getElementById('sur-detail-bc').textContent = order.title || 'Survey detail'
  document.getElementById('sur-detail-title').textContent = order.title || 'Survey'
  const badge = document.getElementById('sur-detail-status-badge')
  if (badge) {
    badge.textContent = order.status_label || order.status
    badge.className = statusBadgeClass(order)
  }
  document.getElementById('sur-detail-contacts').textContent = String(order.recipient_count || 0)
  document.getElementById('sur-detail-quote').textContent = order.quote_total_gbp || '£0.00'
  document.getElementById('sur-detail-prompt').textContent = order.config?.script_approved ? 'Approved' : 'Not approved'
  document.getElementById('sur-detail-payment').textContent =
    order.payment_status === 'rejected'
      ? 'Failed'
      : order.payment_status === 'pending_approval'
        ? 'Pending approval'
        : order.payment_status === 'approved'
          ? 'Paid'
          : 'Unpaid'
  document.getElementById('sur-detail-start').textContent = fmtSchedule(order.scheduled_start_at)
  document.getElementById('sur-detail-end').textContent = fmtSchedule(order.scheduled_end_at)
  const notes = [
    order.payment_note ? `Payment note: ${order.payment_note}` : '',
    order.admin_decision_note ? `Admin: ${order.admin_decision_note}` : '',
    order.created_at ? `Created: ${fmtSchedule(order.created_at)}` : '',
    order.started_at ? `Started: ${fmtSchedule(order.started_at)}` : '',
    order.completed_at ? `Completed: ${fmtSchedule(order.completed_at)}` : '',
  ].filter(Boolean)
  document.getElementById('sur-detail-notes').innerHTML = notes.length
    ? notes.map((n) => `<div>${esc(n)}</div>`).join('')
    : 'No notes yet.'

  const na = order.next_action || {}
  const nextEl = document.getElementById('sur-detail-next-action')
  if (nextEl) {
    if (na.label) {
      nextEl.style.display = 'flex'
      nextEl.className = `sur-next-action${order.payment_status === 'rejected' ? ' is-error' : ''}`
      nextEl.innerHTML = `<i class="ti ti-arrow-right"></i><div><strong>Next: ${esc(na.label)}</strong><div>${esc(na.hint || '')}</div></div>`
    } else {
      nextEl.style.display = 'none'
    }
  }

  renderDetailBilling(order)
  renderDetailTrend(order)

  const titleInput = document.getElementById('sur-edit-title')
  const startInput = document.getElementById('sur-edit-start')
  const endInput = document.getElementById('sur-edit-end')
  if (titleInput) titleInput.value = order.title || ''
  if (startInput) startInput.value = toDatetimeLocal(order.scheduled_start_at)
  if (endInput) endInput.value = toDatetimeLocal(order.scheduled_end_at)

  const action = na.action || ''
  setBtnVisible('sur-detail-pay', ['pay'].includes(action))
  setBtnVisible('sur-detail-start', action === 'start')
  setBtnVisible('sur-detail-edit', order.is_live)
  setBtnVisible('sur-detail-duplicate', true)
  setBtnVisible('sur-detail-results', order.is_finished || order.status === 'running' || order.status === 'completed')
  setBtnVisible('sur-detail-pause', action === 'pause')
  setBtnVisible('sur-detail-resume', action === 'resume')
  setBtnVisible(
    'sur-detail-stop',
    ['pause', 'resume', 'start', 'wait'].includes(action) &&
      ['running', 'paused', 'scheduled', 'paid'].includes(order.status),
  )
  setBtnVisible('sur-detail-delete', order.is_live && !['running', 'paused'].includes(order.status))
}

export async function openSurveyDetail(orderId) {
  if (!orderId) return
  if (typeof window.goNav === 'function') window.goNav('survey-detail')
  showDetailPanel('loading')
  try {
    const order = await api(`/service-orders/${encodeURIComponent(orderId)}`)
    renderDetail(order)
  } catch (e) {
    showDetailPanel('error')
    const errEl = document.getElementById('sur-detail-error')
    if (errEl) errEl.textContent = e.message || 'Could not load survey'
  }
}

async function detailAction(method, path, body) {
  const id = hub.selectedId
  if (!id) return
  const opts = { method }
  if (body) opts.body = JSON.stringify(body)
  const order = await api(`/service-orders/${encodeURIComponent(id)}${path}`, opts)
  renderDetail(order)
  await loadSurveyOrders()
  return order
}

function bindDetailActions() {
  document.getElementById('sur-detail-pay')?.addEventListener('click', async () => {
    const id = hub.selectedId
    if (!id) return
    try {
      const order = await api(`/service-orders/${encodeURIComponent(id)}`)
      if (typeof window.payExistingSurveyOrder === 'function') {
        await window.payExistingSurveyOrder(order)
        await openSurveyDetail(id)
        await loadSurveyOrders()
      }
    } catch (e) {
      window.toast?.(e.message || 'Payment failed', 'tr')
    }
  })
  document.getElementById('sur-detail-edit')?.addEventListener('click', () => {
    toggleInlineEdit(true)
    document.getElementById('sur-detail-inline-edit')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  })
  document.getElementById('sur-edit-cancel')?.addEventListener('click', () => toggleInlineEdit(false))
  document.getElementById('sur-edit-save')?.addEventListener('click', () => {
    const id = hub.selectedId
    if (!id) return
    const payload = {
      title: document.getElementById('sur-edit-title')?.value?.trim(),
      scheduled_start_at: fromDatetimeLocal(document.getElementById('sur-edit-start')?.value),
      scheduled_end_at: fromDatetimeLocal(document.getElementById('sur-edit-end')?.value),
    }
    void api(`/service-orders/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(payload) })
      .then((order) => {
        renderDetail(order)
        toggleInlineEdit(false)
        window.toast?.('Survey updated', 'tg')
        void loadSurveyOrders()
      })
      .catch((e) => window.toast?.(e.message || 'Could not save', 'tr'))
  })
  document.getElementById('sur-detail-duplicate')?.addEventListener('click', () => {
    if (typeof window.duplicateSurveyOrder === 'function') window.duplicateSurveyOrder(hub.selectedId)
    if (typeof window.goNav === 'function') window.goNav('surveys')
  })
  document.getElementById('sur-detail-results')?.addEventListener('click', () => {
    if (typeof window.openSurveyResults === 'function') window.openSurveyResults(hub.selectedId)
  })
  document.getElementById('sur-detail-start')?.addEventListener('click', () => {
    void detailAction('POST', '/start')
      .then(() => window.toast?.('Survey started — AI calls will begin in your schedule window', 'tg'))
      .catch((e) => window.toast?.(e.message, 'tr'))
  })
  document.getElementById('sur-detail-pause')?.addEventListener('click', () => {
    void detailAction('POST', '/pause').catch((e) => window.toast?.(e.message, 'tr'))
  })
  document.getElementById('sur-detail-resume')?.addEventListener('click', () => {
    void detailAction('POST', '/resume').catch((e) => window.toast?.(e.message, 'tr'))
  })
  document.getElementById('sur-detail-stop')?.addEventListener('click', async () => {
    const ok = await confirmDialog({
      title: 'Stop survey?',
      message: 'Outbound calls will halt. Contacts already on a call may finish naturally.',
      okLabel: 'Stop survey',
      danger: true,
    })
    if (!ok) return
    void detailAction('POST', '/stop', { reason: 'Stopped from dashboard' }).catch((e) => window.toast?.(e.message, 'tr'))
  })
  document.getElementById('sur-detail-delete')?.addEventListener('click', async () => {
    const ok = await confirmDialog({
      title: 'Delete survey?',
      message: 'This cannot be undone.',
      okLabel: 'Delete',
      danger: true,
    })
    if (!ok) return
    const id = hub.selectedId
    void api(`/service-orders/${encodeURIComponent(id)}`, { method: 'DELETE' })
      .then(() => {
        window.toast?.('Survey deleted', 'tg')
        if (typeof window.goNav === 'function') window.goNav('surveys')
        void loadSurveyOrders()
      })
      .catch((e) => window.toast?.(e.message || 'Delete failed', 'tr'))
  })
  document.getElementById('sur-live-stop-btn')?.addEventListener('click', () => {
    const id = document.getElementById('sur-live-banner')?.dataset?.orderId
    if (!id) return
    void openSurveyDetail(id)
    document.getElementById('sur-detail-stop')?.click()
  })
}

export function initSurveyHubBridge() {
  window.openSurveyDetail = openSurveyDetail
  window.reloadSurveyHub = loadSurveyOrders
  window.onSurveyPageNav = (pageId) => {
    const show = ['surveys', 'survey-detail', 'results-s'].includes(pageId)
    const wrap = document.getElementById('global-search-wrap')
    if (wrap) wrap.style.display = show ? 'flex' : 'none'
  }
  document.getElementById('global-search')?.addEventListener('input', (e) => {
    hub.searchQuery = e.target.value || ''
    renderLists(hub.orders)
  })
  bindTabs()
  bindListClicks()
  bindDetailActions()
  switchTab('live')
  void loadSurveyOrders()
}
