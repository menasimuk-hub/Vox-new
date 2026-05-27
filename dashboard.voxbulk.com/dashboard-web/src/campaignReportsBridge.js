import { apiFetch, getAccessToken } from './lib/api.js'
import {
  esc,
  isResultsReady,
  pendingMeta,
  renderCampaignTable,
} from './campaignListUi.js'

const state = {
  interview: { tab: 'live', orders: [] },
  survey: { tab: 'live', orders: [] },
}

function filterByTab(orders, tab) {
  if (tab === 'archived') return orders.filter((o) => o.is_archived)
  if (tab === 'finished') return orders.filter((o) => o.is_finished)
  return orders.filter((o) => o.is_live)
}

function renderRow(order, serviceCode) {
  const ready = isResultsReady(order, serviceCode)
  const meta = ready
    ? 'Results ready — click to view'
    : esc(pendingMeta(order, serviceCode))
  const label = ready ? 'View results' : serviceCode === 'interview' ? 'Scheduled' : 'Status'
  return `<tr class="hub-camp-row hub-rep-row" data-order-id="${esc(order.id)}" data-ready="${ready ? '1' : '0'}">
    <td><strong>${esc(order.title || 'Campaign')}</strong></td>
    <td><span class="bdg ${ready ? 'bg' : 'ba'}">${esc(order.status_label || order.status)}</span></td>
    <td class="muted">${meta}</td>
    <td class="hub-camp-actions"><button type="button" class="btn bsm btng" data-rep-view="${esc(order.id)}"><i class="ti ti-eye"></i> ${label}</button></td>
  </tr>`
}

function render(serviceCode) {
  const prefix = serviceCode === 'interview' ? 'int-rep' : 'sur-rep'
  const st = state[serviceCode]
  const host = document.getElementById(`${prefix}-table`)
  if (!host) return
  const filtered = filterByTab(st.orders, st.tab)
  const rows = filtered.map((o) => renderRow(o, serviceCode)).join('')
  host.innerHTML = renderCampaignTable(
    rows,
    'No campaigns in this tab yet.',
  )
}

function switchTab(serviceCode, tab) {
  const prefix = serviceCode === 'interview' ? 'int-rep' : 'sur-rep'
  state[serviceCode].tab = tab
  document.querySelectorAll(`#${prefix}-tabs .tb`).forEach((el) => {
    el.classList.toggle('on', el.getAttribute(`data-${prefix}-tab`) === tab)
  })
  render(serviceCode)
}

async function load(serviceCode) {
  if (!getAccessToken()) return
  const host = document.getElementById(`${serviceCode === 'interview' ? 'int-rep' : 'sur-rep'}-table`)
  if (host) host.innerHTML = '<div class="muted" style="padding:12px 0">Loading…</div>'
  try {
    const code = serviceCode === 'interview' ? 'interview' : 'survey'
    const rows = await apiFetch(`/service-orders?service_code=${code}`)
    state[serviceCode].orders = Array.isArray(rows) ? rows : []
    render(serviceCode)
  } catch {
    if (host) host.innerHTML = '<div class="muted" style="padding:12px 0">Could not load campaigns.</div>'
  }
}

function bind(serviceCode) {
  const prefix = serviceCode === 'interview' ? 'int-rep' : 'sur-rep'
  document.querySelectorAll(`#${prefix}-tabs .tb`).forEach((tab) => {
    tab.addEventListener('click', () => switchTab(serviceCode, tab.getAttribute(`data-${prefix}-tab`) || 'live'))
  })
  document.getElementById(`${prefix}-table`)?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-rep-view]')
    const row = event.target.closest('.hub-rep-row')
    const orderId = btn?.getAttribute('data-rep-view') || row?.getAttribute('data-order-id')
    if (!orderId) return
    if (serviceCode === 'interview' && typeof window.openInterviewResults === 'function') {
      void window.openInterviewResults(orderId)
    } else if (typeof window.openSurveyResults === 'function') {
      void window.openSurveyResults(orderId)
    }
  })
}

export function initCampaignReportsBridge() {
  bind('interview')
  bind('survey')
  window.reloadInterviewCampaignReports = () => load('interview')
  window.reloadSurveyCampaignReports = () => load('survey')
}
