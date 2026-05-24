import { apiFetch, downloadAuthenticatedFile, getAccessToken } from './lib/api.js'

const LOG = '[survey-results]'

const state = {
  orderId: null,
  payload: null,
  loading: false,
}

function log(event, detail = {}) {
  console.info(LOG, event, detail)
}

function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function starsHtml(score10) {
  if (score10 == null || Number.isNaN(Number(score10))) {
    return '<span style="color:var(--t3);font-size:11px">—</span>'
  }
  const filled = Math.max(0, Math.min(5, Math.round(Number(score10) / 2)))
  let html = '<div class="stars">'
  for (let i = 0; i < 5; i += 1) {
    html += `<i class="ti ti-star star${i >= filled ? ' e' : ''}"></i>`
  }
  html += '</div>'
  return html
}

function statusBadge(status) {
  const clean = String(status || 'pending').toLowerCase()
  if (clean === 'completed') return '<span class="bdg bg">Completed</span>'
  if (clean === 'opted_out') return '<span class="bdg br">Opted out</span>'
  if (clean === 'no_answer' || clean === 'busy') return '<span class="bdg ba">No answer</span>'
  if (clean === 'failed') return '<span class="bdg br">Failed</span>'
  if (clean === 'calling') return '<span class="bdg bb">Calling</span>'
  if (clean === 'cancelled') return '<span class="bdg ba">Cancelled</span>'
  return `<span class="bdg ba">${esc(clean.replace(/_/g, ' '))}</span>`
}

function satisfactionLabel(score5) {
  if (score5 == null) return '—'
  if (score5 >= 4) return 'Good'
  if (score5 >= 3) return 'Fair'
  return 'Needs attention'
}

function setVisible(id, show) {
  const el = document.getElementById(id)
  if (el) el.style.display = show ? '' : 'none'
}

function renderKpis(summary) {
  const sat5 = summary.average_satisfaction_5
  document.getElementById('sur-kpi-satisfaction').textContent =
    sat5 != null ? `${sat5}/5` : '—'
  document.getElementById('sur-kpi-satisfaction-sub').textContent = satisfactionLabel(sat5)

  document.getElementById('sur-kpi-recommend').textContent =
    summary.recommend_pct != null ? `${summary.recommend_pct}%` : '—'
  document.getElementById('sur-kpi-nps').textContent =
    summary.nps_score != null ? `NPS ${summary.nps_score >= 0 ? '+' : ''}${summary.nps_score}` : '—'

  document.getElementById('sur-kpi-responded').textContent = String(summary.completed_count ?? '—')
  document.getElementById('sur-kpi-response-rate').textContent =
    summary.response_rate_pct != null ? `${summary.response_rate_pct}% rate` : '—'

  document.getElementById('sur-kpi-duration').textContent =
    summary.average_call_duration_label || '—'
}

function renderRespondents(respondents) {
  const tbody = document.getElementById('sur-results-respondents')
  if (!tbody) return
  if (!respondents?.length) {
    tbody.innerHTML =
      '<tr><td colspan="6" style="color:var(--t3);font-size:12px;padding:14px">No recipients on this survey yet.</td></tr>'
    return
  }
  tbody.innerHTML = respondents
    .map(
      (row) => `<tr onclick="window.openSurveyRecipientDetail('${esc(row.id)}')" style="cursor:pointer">
        <td><div style="display:flex;align-items:center;gap:9px"><div class="av ${esc(row.avatar_class)}" style="width:28px;height:28px;font-size:10px">${esc(row.initials)}</div>${esc(row.name)}</div></td>
        <td><i class="ti ti-clock" style="color:var(--t3);font-size:12px"></i> ${esc(row.duration_label)}</td>
        <td>${esc(row.goal)}</td>
        <td>${starsHtml(row.satisfaction_score)}</td>
        <td>${statusBadge(row.status)}</td>
        <td><button class="btn bsm bxsm" type="button" onclick="event.stopPropagation();window.openSurveyRecipientDetail('${esc(row.id)}')"><i class="ti ti-file-text"></i>View</button></td>
      </tr>`,
    )
    .join('')
}

function renderProblems(summary, completedCount) {
  const host = document.getElementById('sur-results-problems')
  if (!host) return
  const issues = summary.top_issues || []
  if (!issues.length) {
    host.innerHTML =
      '<div style="font-size:12px;color:var(--t3);padding:6px 0">No recurring issues identified yet.</div>'
    return
  }
  const total = Math.max(1, Number(completedCount) || 1)
  host.innerHTML = issues
    .map((item) => {
      const count = Number(item.count) || 0
      const pct = Math.round((count / total) * 100)
      const width = Math.max(8, Math.min(100, pct))
      return `<div class="prob-row"><div class="prob-lbl">${esc(item.label)}</div><div class="prob-bar"><div class="prob-fill" style="width:${width}%"></div></div><div class="prob-pct">${pct}%</div></div>`
    })
    .join('')
}

function renderAggregates(aggregates) {
  const host = document.getElementById('sur-results-aggregates')
  if (!host) return
  if (!aggregates?.length) {
    host.innerHTML =
      '<div style="font-size:12px;color:var(--t3);padding:6px 0">No aggregated answers yet — complete a few calls first.</div>'
    return
  }
  host.innerHTML = aggregates
    .map((block) => {
      const total = Math.max(1, Number(block.total) || 1)
      const rows = (block.responses || [])
        .map((row) => {
          const count = Number(row.count) || 0
          const pct = Math.round((count / total) * 100)
          return `<div class="sur-agg-row">
            <div class="lbl">${esc(row.answer)}</div>
            <div class="track"><div class="fill" style="width:${Math.max(6, pct)}%"></div></div>
            <div class="val">${count}</div>
          </div>`
        })
        .join('')
      return `<div class="sur-agg-block">
        <div class="sur-agg-q">${esc(block.question)} <span style="color:var(--t3);font-weight:500">(${total} responses)</span></div>
        ${rows}
      </div>`
    })
    .join('')
}

function renderRecommendations(recommendations) {
  const host = document.getElementById('sur-results-recommendations')
  if (!host) return
  if (!recommendations?.length) {
    host.innerHTML =
      '<div style="color:var(--t3)">Recommendations will appear once enough calls are analysed.</div>'
    return
  }
  host.innerHTML = recommendations
    .map(
      (rec) =>
        `<div style="margin-bottom:8px;display:flex;gap:8px"><i class="ti ti-arrow-right" style="color:var(--grn);margin-top:2px;flex-shrink:0"></i>${esc(rec.text)}</div>`,
    )
    .join('')
}

function renderTranscriptLines(transcript) {
  if (!transcript) {
    return '<div style="font-size:12px;color:var(--t3)">Transcript not available yet — it may still be syncing from Telnyx.</div>'
  }
  return transcript
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const idx = line.indexOf(':')
      if (idx > 0) {
        const speaker = line.slice(0, idx).trim()
        const text = line.slice(idx + 1).trim()
        const cls = speaker.toLowerCase().includes('agent') ? 'trans-ai' : 'trans-ai'
        return `<div class="trans-line"><span class="${cls}">${esc(speaker)}:</span> <span class="trans-pt">${esc(text)}</span></div>`
      }
      return `<div class="trans-line"><span class="trans-pt">${esc(line)}</span></div>`
    })
    .join('')
}

function renderAnswers(answers) {
  if (!answers?.length) return ''
  const rows = answers
    .map(
      (item) =>
        `<div style="margin-bottom:8px"><div style="font-size:11px;color:var(--t3);margin-bottom:2px">${esc(item.question || 'Question')}</div><div style="font-size:12px;color:var(--t1)">${esc(item.answer || '—')}</div></div>`,
    )
    .join('')
  return `<div class="card" style="margin:0;padding:10px 12px"><div class="ch" style="margin-bottom:8px"><i class="ti ti-list-check grn"></i>Extracted answers</div>${rows}</div>`
}

function renderSurveyResultsPage(payload) {
  const { order, summary, respondents, recommendations, aggregates } = payload
  document.getElementById('sur-results-breadcrumb').textContent = order.title || 'Survey results'
  renderKpis(summary)
  renderAggregates(aggregates)
  renderRespondents(respondents)
  renderProblems(summary, summary.completed_count)
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
  state.loading = true
  setVisible('sur-results-loading', true)
  setVisible('sur-results-error', false)
  setVisible('sur-results-content', false)
  setVisible('sur-results-empty', false)
  log('load_started', { orderId })

  try {
    const payload = await apiFetch(`/service-orders/${orderId}/survey-results`)
    state.payload = payload
    renderSurveyResultsPage(payload)
    log('load_saved', {
      orderId,
      completed: payload.summary?.completed_count,
      analyzed: payload.summary?.analyzed_count,
    })
  } catch (err) {
    const msg = err?.message || 'Could not load survey results'
    const errEl = document.getElementById('sur-results-error')
    if (errEl) errEl.textContent = msg
    setVisible('sur-results-error', true)
    setVisible('sur-results-content', false)
    log('load_failed', { orderId, error: msg })
  } finally {
    state.loading = false
    setVisible('sur-results-loading', false)
  }
}

async function openSurveyResults(orderId) {
  if (typeof window.goNav === 'function') window.goNav('results-s')
  document.getElementById('srec-panel').style.display = 'none'
  await loadSurveyResults(orderId)
}

async function openSurveyRecipientDetail(recipientId) {
  if (!state.orderId) return
  log('recipient_open_started', { orderId: state.orderId, recipientId })
  try {
    const payload = await apiFetch(
      `/service-orders/${state.orderId}/recipients/${recipientId}/survey-detail`,
    )
    const row = payload.recipient || {}
    document.getElementById('srec-name').textContent = row.name || '—'
    document.getElementById('srec-dur').textContent = row.duration_label || '—'
    document.getElementById('srec-goal').textContent = state.payload?.order?.goal || 'Survey'
    document.getElementById('srec-sentiment').textContent = row.sentiment_label || '—'
    document.getElementById('srec-av').textContent = row.initials || '—'
    document.getElementById('srec-av').className = `av ${row.avatar_class || 'av-g'}`
    document.getElementById('srec-summary').textContent = row.short_summary || ''
    document.getElementById('srec-transcript').innerHTML = renderTranscriptLines(row.transcript)
    document.getElementById('srec-answers').innerHTML = renderAnswers(row.extracted_answers)
    document.getElementById('srec-panel').style.display = 'block'
    document.getElementById('srec-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    log('recipient_open_saved', { recipientId, hasTranscript: Boolean(row.transcript) })
  } catch (err) {
    window.toast?.(err?.message || 'Could not load transcript', 'tr')
    log('recipient_open_failed', { recipientId, error: err?.message })
  }
}

function bindSurveyResultsNav() {
  document.querySelector('.ni[onclick*="results-s"]')?.addEventListener('click', () => {
    if (!state.orderId) {
      setVisible('sur-results-empty', true)
      setVisible('sur-results-content', false)
      setVisible('sur-results-loading', false)
      setVisible('sur-results-error', false)
    }
  })
}

export function initSurveyResultsBridge() {
  window.openSurveyResults = openSurveyResults
  window.openSurveyRecipientDetail = openSurveyRecipientDetail
  window.showSurveyRec = (name, dur) => {
    log('legacy_showSurveyRec_ignored', { name, dur })
  }
  document.getElementById('sur-results-export-csv')?.addEventListener('click', async () => {
    if (!state.orderId) {
      window.toast?.('Open a survey results page first', 'tw')
      return
    }
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
    if (!state.orderId) {
      window.toast?.('Open a survey results page first', 'tw')
      return
    }
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
  bindSurveyResultsNav()
  log('bridge_ready')
}
