import { apiFetch, downloadAuthenticatedFile, getAccessToken } from './lib/api.js'

const state = { period: 'month', payload: null, loading: false }

function api(path, options = {}) {
  return apiFetch(path, options)
}

function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function setText(id, value) {
  const el = document.getElementById(id)
  if (el) el.textContent = value
}

function renderOverview(payload) {
  const overview = payload?.overview || {}
  const batches = payload?.batches || []
  const anyMock = batches.some((b) => b.is_mock)
  const mockNote = document.getElementById('int-rep-mock-note')
  if (mockNote) mockNote.style.display = anyMock ? '' : 'none'

  setText('int-rep-period-label', payload?.period_label || 'This month')
  setText('int-rep-kpi-batches', String(overview.batch_count ?? '—'))
  setText(
    'int-rep-kpi-batches-sub',
    overview.batch_count ? `${overview.reached ?? 0} reached` : 'No batches in period',
  )
  setText('int-rep-kpi-candidates', String(overview.candidate_count ?? '—'))
  setText(
    'int-rep-kpi-candidates-sub',
    overview.candidate_count ? `${overview.reach_rate_pct ?? 0}% reach rate` : '—',
  )
  setText('int-rep-kpi-advance', String(overview.advance_count ?? '—'))
  setText('int-rep-kpi-cost', overview.total_cost_gbp || '—')
  setText('int-rep-kpi-cost-sub', payload?.period_label || '—')
}

function renderTable(batches) {
  const host = document.getElementById('int-rep-table-wrap')
  if (!host) return
  if (!batches?.length) {
    host.innerHTML =
      '<div class="muted" style="font-size:12px;padding:8px 0">No completed interview batches in this period. Finish a campaign from Interviews to see it here.</div>'
    return
  }
  const rows = batches
    .map((batch) => {
      const ref = batch.reference_id
        ? `<span class="bdg bb" style="margin-right:6px">${esc(batch.reference_id)}</span>`
        : ''
      return `<div class="proj-row int-rep-row" data-order-id="${esc(batch.order_id)}">
        <div class="proj-ic ci-b"><i class="ti ti-briefcase"></i></div>
        <div class="proj-info">
          <div class="proj-name">${ref}${esc(batch.title || 'Interview batch')}</div>
          <div class="proj-meta">${esc(batch.role || 'Interview')} · ${esc(batch.status_label || batch.status)} · ${fmtDate(batch.completed_at || batch.period_at)} · ${batch.candidate_count ?? 0} candidates · avg ${batch.avg_score ?? '—'}</div>
        </div>
        <div style="text-align:right;font-size:12px">
          <div style="font-weight:700;color:var(--grn)">${batch.advance_count ?? 0} advance</div>
          <div class="muted">${esc(batch.quote_total_gbp || '')}</div>
        </div>
      </div>`
    })
    .join('')
  host.innerHTML = rows
}

function bindTableClicks() {
  document.getElementById('int-rep-table-wrap')?.addEventListener('click', (event) => {
    const row = event.target.closest('.int-rep-row')
    if (!row) return
    const orderId = row.getAttribute('data-order-id')
    if (orderId && typeof window.openInterviewResults === 'function') {
      void window.openInterviewResults(orderId)
    }
  })
}

function setPeriod(period, buttonEl) {
  state.period = period
  document.querySelectorAll('#int-rep-drp .drp-opt').forEach((el) => {
    el.classList.toggle('on', el === buttonEl)
  })
  void loadInterviewReports()
}

function bindPeriodButtons() {
  document.querySelectorAll('#int-rep-drp .drp-opt[data-rep-period]').forEach((btn) => {
    btn.addEventListener('click', () => setPeriod(btn.getAttribute('data-rep-period') || 'month', btn))
  })
  document.getElementById('int-rep-export-csv')?.addEventListener('click', () => {
    void exportCsv()
  })
}

function bindTabs() {
  document.querySelectorAll('#rep-tabs .tb').forEach((tab) => {
    tab.addEventListener('click', () => {
      const key = tab.getAttribute('data-rep-tab') || 'interviews'
      document.querySelectorAll('#rep-tabs .tb').forEach((el) => el.classList.toggle('on', el === tab))
      const interviews = document.getElementById('rep-panel-interviews')
      const clinic = document.getElementById('rep-panel-clinic')
      if (interviews) interviews.hidden = key !== 'interviews'
      if (clinic) clinic.hidden = key !== 'clinic'
      if (key === 'interviews') void loadInterviewReports()
    })
  })
}

async function exportCsv() {
  if (!getAccessToken()) return
  try {
    await downloadAuthenticatedFile(
      `/service-orders/interview-reports/export.csv?period=${encodeURIComponent(state.period)}`,
      `interview-batches-${state.period}.csv`,
    )
    window.toast?.('Interview batch CSV downloaded', 'tg')
  } catch (e) {
    window.toast?.(e.message || 'Export failed', 'tr')
  }
}

export async function loadInterviewReports() {
  if (!getAccessToken()) return null
  if (state.loading) return state.payload
  state.loading = true
  const host = document.getElementById('int-rep-table-wrap')
  if (host && !state.payload) {
    host.innerHTML = '<div class="muted" style="font-size:12px;padding:8px 0">Loading interview reports…</div>'
  }
  try {
    const payload = await api(`/service-orders/interview-reports?period=${encodeURIComponent(state.period)}`)
    state.payload = payload
    renderOverview(payload)
    renderTable(payload?.batches || [])
    return payload
  } catch {
    if (host) {
      host.innerHTML = '<div class="muted" style="font-size:12px;padding:8px 0">Could not load interview reports.</div>'
    }
    return null
  } finally {
    state.loading = false
  }
}

export function getInterviewReportsOverview() {
  return state.payload?.overview || null
}

export function initInterviewReportsBridge() {
  bindTabs()
  bindPeriodButtons()
  bindTableClicks()
  window.reloadInterviewReports = loadInterviewReports

  const reportsPage = document.getElementById('pg-reports')
  if (reportsPage && !reportsPage.hidden && reportsPage.classList.contains('on')) {
    void loadInterviewReports()
  }
}
