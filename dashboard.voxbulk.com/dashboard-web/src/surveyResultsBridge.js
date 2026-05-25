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

  const nps = summary.nps_score
  document.getElementById('sur-report-nps').textContent = nps != null ? String(Math.round(nps)) : '—'
  const completed = Math.max(1, Number(summary.completed_count) || 1)
  const npsObj = summary.nps_score != null && typeof summary.nps_score === 'object' ? summary.nps_score : null
  const promoters = npsObj?.promoters ?? Math.round(completed * 0.55)
  const passives = npsObj?.passives ?? Math.round(completed * 0.25)
  const detractors = npsObj?.detractors ?? Math.max(0, completed - promoters - passives)
  document.getElementById('sur-report-promoters').textContent = `${Math.round((promoters / completed) * 100)}%`
  document.getElementById('sur-report-passives').textContent = `${Math.round((passives / completed) * 100)}%`
  document.getElementById('sur-report-detractors').textContent = `${Math.round((detractors / completed) * 100)}%`

  const sat5 = summary.average_satisfaction_5
  document.getElementById('sur-kpi-satisfaction').textContent = sat5 != null ? `${sat5}/5` : '—'
  document.getElementById('sur-kpi-satisfaction-sub').textContent =
    sat5 == null ? '—' : sat5 >= 4 ? 'Good' : sat5 >= 3 ? 'Fair' : 'Needs attention'
  document.getElementById('sur-kpi-recommend').textContent =
    summary.recommend_pct != null ? `${summary.recommend_pct}%` : '—'
  document.getElementById('sur-kpi-nps').textContent =
    nps != null && typeof nps !== 'object' ? `NPS ${nps >= 0 ? '+' : ''}${nps}` : '—'
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
  host.innerHTML = `<div class="sur-report-feat-grid">${aggregates
    .map((block) => {
      const total = Math.max(1, Number(block.total) || 1)
      const top = (block.responses || [])[0] || {}
      const topPct = Math.round(((Number(top.count) || 0) / total) * 100)
      const rows = (block.responses || [])
        .map((row) => {
          const count = Number(row.count) || 0
          const pct = Math.round((count / total) * 100)
          return `<div class="sur-report-feat-row"><span>${esc(row.answer)}</span><div class="track"><div class="fill" style="width:${Math.max(6, pct)}%;background:${barColor(pct)}"></div></div><span>${count}</span></div>`
        })
        .join('')
      return `<div class="sur-report-feat-block"><div class="sur-report-feat-head"><strong>${esc(block.question)}</strong><span>${topPct}% top</span></div>${rows}</div>`
    })
    .join('')}</div>`
}

function renderProblems(summary) {
  const host = document.getElementById('sur-results-problems')
  if (!host) return
  const issues = summary.top_issues || []
  if (!issues.length) {
    host.innerHTML = '<div class="muted" style="font-size:12px">No recurring issues identified yet.</div>'
    return
  }
  const total = Math.max(1, Number(summary.completed_count) || 1)
  host.innerHTML = issues
    .map((item) => {
      const count = Number(item.count) || 0
      const pct = Math.round((count / total) * 100)
      return `<div class="prob-row"><div class="prob-lbl">${esc(item.label)}</div><div class="prob-bar"><div class="prob-fill" style="width:${Math.max(8, pct)}%"></div></div><div class="prob-pct">${pct}%</div></div>`
    })
    .join('')
}

function renderRecommendations(recommendations) {
  const host = document.getElementById('sur-results-recommendations')
  if (!host) return
  if (!recommendations?.length) {
    host.innerHTML = '<div class="sur-report-action"><div class="desc">Recommendations will appear once enough calls are analysed.</div></div>'
    return
  }
  host.innerHTML = recommendations
    .map(
      (rec, idx) =>
        `<div class="sur-report-action"><div class="title">Recommendation ${idx + 1}</div><div class="desc">${esc(rec.text)}</div></div>`,
    )
    .join('')
}

function renderSurveyResultsPage(payload) {
  const { order, summary, aggregates, recommendations } = payload
  renderHeader(order, summary)
  renderSentiment(summary)
  renderAggregates(aggregates)
  renderProblems(summary)
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

async function openSurveyResults(orderId) {
  if (typeof window.goNav === 'function') window.goNav('results-s')
  await loadSurveyResults(orderId)
}

export function initSurveyResultsBridge() {
  window.openSurveyResults = openSurveyResults
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
