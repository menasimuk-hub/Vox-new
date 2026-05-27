import { apiFetch, getAccessToken } from './lib/api.js'
import { surveyRespondedCount } from './surveyUtils.js'

function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function setText(id, value) {
  const el = document.getElementById(id)
  if (el) el.textContent = value
}

function renderTable(orders) {
  const host = document.getElementById('sur-rep-table-wrap')
  if (!host) return
  const rows = orders.filter((o) => !o.is_archived)
  if (!rows.length) {
    host.innerHTML =
      '<div class="muted" style="font-size:12px;padding:8px 0">No survey campaigns yet. Create one from Surveys.</div>'
    return
  }
  host.innerHTML = rows
    .map((order) => {
      const sent = surveyRespondedCount(order.report)
      const total = Number(order.recipient_count || 0)
      const pct = total > 0 ? Math.round((sent / total) * 100) : 0
      return `<div class="proj-row sur-rep-row" data-survey-order-id="${esc(order.id)}">
        <div class="proj-ic ci-b"><i class="ti ti-clipboard-list"></i></div>
        <div class="proj-info">
          <div class="proj-name">${esc(order.title)}</div>
          <div class="proj-meta">${esc(order.status_label || order.status)} · ${total} contacts · ${pct}% responded</div>
        </div>
        <div style="text-align:right;font-size:12px;font-weight:700;color:var(--grn)">${esc(order.quote_total_gbp || '')}</div>
      </div>`
    })
    .join('')
}

function renderKpis(orders) {
  const active = orders.filter((o) => !o.is_archived)
  const live = active.filter((o) => o.is_live)
  const finished = active.filter((o) => o.is_finished)
  let responses = 0
  let sent = 0
  for (const o of live) {
    responses += surveyRespondedCount(o.report)
    sent += Number(o.recipient_count || 0)
  }
  const rate = sent > 0 ? `${Math.round((responses / sent) * 100)}%` : '0%'
  setText('sur-rep-live', String(live.length))
  setText('sur-rep-live-sub', `${active.filter((o) => o.status === 'running').length} running now`)
  setText('sur-rep-responses', String(responses))
  setText('sur-rep-resp-sub', sent ? `of ${sent} contacts` : '—')
  setText('sur-rep-rate', rate)
  setText('sur-rep-finished', String(finished.length))
  setText('sur-rep-finished-sub', `${active.filter((o) => o.status === 'paused').length} paused`)
}

export async function loadSurveyReports() {
  if (!getAccessToken()) return
  const host = document.getElementById('sur-rep-table-wrap')
  if (host) {
    host.innerHTML = '<div class="muted" style="font-size:12px;padding:8px 0">Loading survey reports…</div>'
  }
  try {
    const rows = await apiFetch('/service-orders?service_code=survey')
    const orders = Array.isArray(rows) ? rows : []
    renderKpis(orders)
    renderTable(orders)
  } catch {
    if (host) {
      host.innerHTML = '<div class="muted" style="font-size:12px;padding:8px 0">Could not load survey reports.</div>'
    }
  }
}

export function initSurveyReportsBridge() {
  window.reloadSurveyReports = loadSurveyReports
  document.getElementById('sur-rep-table-wrap')?.addEventListener('click', (event) => {
    const row = event.target.closest('.sur-rep-row')
    if (!row) return
    const id = row.getAttribute('data-survey-order-id')
    if (id && typeof window.openSurveyDetail === 'function') void window.openSurveyDetail(id)
  })
}
