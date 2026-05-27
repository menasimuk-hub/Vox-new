import { apiFetch, getAccessToken } from './lib/api.js'
import {
  esc,
  isResultsReady,
  pendingMeta,
  renderCampaignTable,
} from './campaignListUi.js'

const pickers = {
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
    ? 'Results ready'
    : esc(pendingMeta(order, serviceCode))
  return `<tr class="hub-camp-row" data-order-id="${esc(order.id)}">
    <td><strong>${esc(order.title || 'Campaign')}</strong></td>
    <td><span class="bdg ${ready ? 'bg' : 'ba'}">${esc(order.status_label || order.status)}</span></td>
    <td class="muted">${meta}</td>
    <td class="hub-camp-actions"><button type="button" class="btn bsm btng hub-view-res" data-order-id="${esc(order.id)}"><i class="ti ti-eye"></i> View</button></td>
  </tr>`
}

function renderPicker(serviceCode) {
  const prefix = serviceCode === 'interview' ? 'int-res-pick' : 'sur-res-pick'
  const state = pickers[serviceCode]
  const filtered = filterByTab(state.orders, state.tab)
  const host = document.getElementById(`${prefix}-table`)
  if (!host) return
  const rows = filtered.map((o) => renderRow(o, serviceCode)).join('')
  host.innerHTML = renderCampaignTable(rows, 'No campaigns in this tab.')
}

function switchTab(serviceCode, tab) {
  const prefix = serviceCode === 'interview' ? 'int-res-pick' : 'sur-res-pick'
  pickers[serviceCode].tab = tab
  document.querySelectorAll(`#${prefix}-tabs .tb`).forEach((el) => {
    el.classList.toggle('on', el.getAttribute(`data-${prefix}-tab`) === tab)
  })
  renderPicker(serviceCode)
}

async function loadOrders(serviceCode) {
  if (!getAccessToken()) return
  try {
    const code = serviceCode === 'interview' ? 'interview' : 'survey'
    const rows = await apiFetch(`/service-orders?service_code=${code}`)
    pickers[serviceCode].orders = Array.isArray(rows) ? rows : []
    renderPicker(serviceCode)
  } catch {
    /* keep */
  }
}

function bindPicker(serviceCode) {
  const prefix = serviceCode === 'interview' ? 'int-res-pick' : 'sur-res-pick'
  document.querySelectorAll(`#${prefix}-tabs .tb`).forEach((tab) => {
    tab.addEventListener('click', () => switchTab(serviceCode, tab.getAttribute(`data-${prefix}-tab`) || 'live'))
  })
  document.getElementById(`${prefix}-table`)?.addEventListener('click', (event) => {
    const btn = event.target.closest('.hub-view-res')
    const row = event.target.closest('.hub-camp-row')
    const orderId = btn?.getAttribute('data-order-id') || row?.getAttribute('data-order-id')
    if (!orderId) return
    if (serviceCode === 'interview' && typeof window.openInterviewResults === 'function') {
      void window.openInterviewResults(orderId)
    } else if (typeof window.openSurveyResults === 'function') {
      void window.openSurveyResults(orderId)
    }
  })
  document.getElementById(`${prefix}-back`)?.addEventListener('click', () => {
    if (serviceCode === 'interview' && typeof window.showInterviewResultsDetail === 'function') {
      window.showInterviewResultsDetail(false)
    } else if (typeof window.showSurveyResultsDetail === 'function') {
      window.showSurveyResultsDetail(false)
    }
    if (typeof window.goNav === 'function') window.goNav(serviceCode === 'interview' ? 'results-i' : 'results-s')
  })
}

export function showInterviewResultsPicker() {
  window.__intResultsDetail = false
  if (typeof window.showInterviewResultsDetail === 'function') window.showInterviewResultsDetail(false)
  void loadOrders('interview')
}

export function showSurveyResultsPicker() {
  window.__surveyResultsDetail = false
  if (typeof window.showSurveyResultsDetail === 'function') window.showSurveyResultsDetail(false)
  void loadOrders('survey')
}

export function initResultsPickerBridge() {
  bindPicker('interview')
  bindPicker('survey')
  window.reloadInterviewResultsPicker = () => loadOrders('interview')
  window.reloadSurveyResultsPicker = () => loadOrders('survey')
  window.showInterviewResultsPicker = showInterviewResultsPicker
  window.showSurveyResultsPicker = showSurveyResultsPicker
}
