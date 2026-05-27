import { apiFetch, downloadAuthenticatedFile, getAccessToken } from './lib/api.js'

const state = { orderId: null, payload: null }

function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function setVisible(id, show) {
  const el = document.getElementById(id)
  if (el) el.style.display = show ? '' : 'none'
}

function barColor(pct) {
  if (pct >= 80) return 'var(--grn)'
  if (pct >= 65) return 'var(--blu)'
  if (pct >= 50) return 'var(--amb)'
  return 'var(--red)'
}

function fmtPeriod(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
}

function renderHeader(order, summary) {
  document.getElementById('sur-results-breadcrumb').textContent = order.title || 'Survey results'
  document.getElementById('sur-report-title-inline').textContent = order.title || 'Survey'
  document.getElementById('sur-report-company').textContent =
    order.organisation_name || order.goal || 'Your organisation'
  document.getElementById('sur-report-responses').textContent = String(summary.completed_count ?? '—')
  document.getElementById('sur-report-rate').textContent =
    summary.response_rate_pct != null ? `${summary.response_rate_pct}%` : '—'
  document.getElementById('sur-report-period').textContent = fmtPeriod(order.started_at || order.completed_at)

  const npsScore = summary.nps_score
  const npsLabel = summary.nps_label || '—'
  const npsEl = document.getElementById('sur-report-nps')
  if (npsEl) npsEl.textContent = npsScore != null ? String(npsScore) : '—'
  const moodEl = document.getElementById('sur-report-nps-label')
  if (moodEl) {
    moodEl.textContent = npsLabel
    moodEl.className = `sur-nps-mood${npsLabel === 'Good' ? ' is-good' : npsLabel === 'Unhappy' ? ' is-unhappy' : ''}`
  }

  document.getElementById('sur-report-promoters').textContent =
    summary.nps_promoters_pct != null ? `${summary.nps_promoters_pct}%` : '—'
  document.getElementById('sur-report-passives').textContent =
    summary.nps_passives_pct != null ? `${summary.nps_passives_pct}%` : '—'
  document.getElementById('sur-report-detractors').textContent =
    summary.nps_detractors_pct != null ? `${summary.nps_detractors_pct}%` : '—'

  const sat5 = summary.average_satisfaction_5
  document.getElementById('sur-kpi-satisfaction').textContent = sat5 != null ? `${sat5}/5` : '—'
  document.getElementById('sur-kpi-satisfaction-sub').textContent =
    sat5 == null ? '—' : sat5 >= 4 ? 'Good' : sat5 >= 3 ? 'Fair' : 'Needs attention'
  document.getElementById('sur-kpi-recommend').textContent =
    summary.recommend_pct != null ? `${summary.recommend_pct}%` : '—'
  document.getElementById('sur-kpi-nps').textContent =
    npsScore != null ? `${npsLabel} · ${npsScore}/100` : '—'
  document.getElementById('sur-kpi-duration').textContent = summary.average_call_duration_label || '—'
  document.getElementById('sur-kpi-response-rate').textContent =
    summary.response_rate_pct != null ? `${summary.response_rate_pct}% response rate` : '—'
}

function renderSentiment(summary) {
  const host = document.getElementById('sur-report-sentiment')
  if (!host) return
  const counts = summary.sentiment_counts || {}
  const completed = Math.max(1, Number(summary.completed_count) || 1)
  const rows = [
    ['Positive', counts.positive || 0, 'var(--grn)'],
    ['Neutral', counts.neutral || 0, 'var(--blu)'],
    ['Negative', counts.negative || 0, 'var(--red)'],
  ]
  host.innerHTML = rows
    .map(([label, count, color]) => {
      const pct = Math.round((Number(count) / completed) * 100)
      return `<div class="sur-report-sent-row"><div class="top"><span>${label}</span><span>${pct}%</span></div><div class="track"><div class="fill" style="width:${Math.max(4, pct)}%;background:${color}"></div></div></div>`
    })
    .join('')
}

function renderAggregates(aggregates) {
  const host = document.getElementById('sur-results-aggregates')
  const countEl = document.getElementById('sur-report-q-count')
  if (countEl) countEl.textContent = `${aggregates?.length || 0} questions`
  if (!host) return
  if (!aggregates?.length) {
    host.innerHTML = '<div class="muted" style="font-size:12px">No aggregated answers yet — complete a few calls first.</div>'
    return
  }
  host.innerHTML = aggregates
    .map((block) => {
      const total = Math.max(1, Number(block.total) || 1)
      const rows = (block.responses || [])
        .map((row) => {
          const count = Number(row.count) || 0
          const pct = Math.round((count / total) * 100)
          return `<div class="sur-q-row">
            <span class="sur-q-answer">${esc(row.answer)}</span>
            <div class="track"><div class="fill" style="width:${Math.max(4, pct)}%;background:${barColor(pct)}"></div></div>
            <span class="sur-q-pct">${pct}%</span>
            <span class="sur-q-count">(${count})</span>
          </div>`
        })
        .join('')
      return `<div class="sur-q-block">
        <div class="sur-q-title">${esc(block.question)}</div>
        <div class="sur-q-meta">${total} responses</div>
        <div class="sur-q-rows">${rows || '<div class="muted" style="font-size:11px">No answers recorded.</div>'}</div>
      </div>`
    })
    .join('')
}

function renderRecommendations(recommendations) {
  const host = document.getElementById('sur-results-recommendations')
  if (!host) return
  if (!recommendations?.length) {
    host.innerHTML = '<div class="sur-report-action"><div class="desc">Recommendations will appear once enough survey responses are analysed.</div></div>'
    return
  }
  host.innerHTML = recommendations
    .map(
      (rec) =>
        `<div class="sur-report-action"><div class="title">${esc(rec.title || 'Recommendation')}</div><div class="desc">${esc(rec.text || rec.title || '')}</div></div>`,
    )
    .join('')
}

function renderSurveyResultsPage(payload) {
  const { order, summary, aggregates, recommendations } = payload
  renderHeader(order, summary)
  renderSentiment(summary)
  renderAggregates(aggregates)
  renderRecommendations(recommendations)
  setVisible('sur-results-content', true)
  setVisible('sur-results-empty', false)
  setVisible('sur-results-error', false)
}

async function loadSurveyResults(orderId) {
  if (!getAccessToken()) {
    setVisible('sur-results-empty', true)
    return
  }
  state.orderId = orderId
  setVisible('sur-results-loading', true)
  setVisible('sur-results-error', false)
  setVisible('sur-results-content', false)
  setVisible('sur-results-empty', false)
  try {
    const payload = await apiFetch(`/service-orders/${orderId}/survey-results`)
    state.payload = payload
    renderSurveyResultsPage(payload)
  } catch (err) {
    const errEl = document.getElementById('sur-results-error')
    if (errEl) errEl.textContent = err?.message || 'Could not load survey results'
    setVisible('sur-results-error', true)
  } finally {
    setVisible('sur-results-loading', false)
  }
}

function showSurveyResultsDetail(show) {
  window.__surveyResultsDetail = Boolean(show)
  const list = document.getElementById('sur-res-pick-list')
  const detail = document.getElementById('sur-res-pick-detail')
  if (list) list.style.display = show ? 'none' : ''
  if (detail) detail.style.display = show ? '' : 'none'
}

async function openSurveyResults(orderId) {
  if (typeof window.goNav === 'function') window.goNav('results-s')
  showSurveyResultsDetail(true)
  await loadSurveyResults(orderId)
}

export function initSurveyResultsBridge() {
  window.openSurveyResults = openSurveyResults
  window.showSurveyResultsDetail = showSurveyResultsDetail
  document.getElementById('sur-results-export-csv')?.addEventListener('click', async () => {
    if (!state.orderId) return window.toast?.('Open a survey results page first', 'tw')
    try {
      await downloadAuthenticatedFile(
        `/service-orders/${encodeURIComponent(state.orderId)}/survey-results/export.csv`,
        `survey-results-${state.orderId.slice(0, 8)}.csv`,
      )
      window.toast?.('CSV downloaded', 'tg')
    } catch (err) {
      window.toast?.(err?.message || 'Export failed', 'tr')
    }
  })
  document.getElementById('sur-results-export-pdf')?.addEventListener('click', async () => {
    if (!state.orderId) return window.toast?.('Open a survey results page first', 'tw')
    try {
      await downloadAuthenticatedFile(
        `/service-orders/${encodeURIComponent(state.orderId)}/survey-results/export.pdf`,
        `survey-results-${state.orderId.slice(0, 8)}.pdf`,
      )
      window.toast?.('PDF downloaded', 'tg')
    } catch (err) {
      window.toast?.(err?.message || 'Export failed', 'tr')
    }
  })
}
