import { apiFetch, getAccessToken } from './lib/api.js'
import { getEnabledServices } from './servicesBridge.js'

function setText(id, value) {
  const el = document.getElementById(id)
  if (el) el.textContent = value
}

function hideEl(id) {
  const el = document.getElementById(id)
  if (el) el.style.display = 'none'
}

function showEl(id, display = '') {
  const el = document.getElementById(id)
  if (el) el.style.display = display || ''
}

function applyServiceSections(enabled) {
  const show = (id, on) => {
    const el = document.getElementById(id)
    if (el) el.style.display = on ? '' : 'none'
  }
  show('dash-section-recovery', Boolean(enabled.recovery))
  show('dash-section-interview', Boolean(enabled.interview))
  show('dash-section-survey', Boolean(enabled.survey))
  show('dash-chart-recovery', Boolean(enabled.recovery))
}

function applyHomeSummary(summary, enabled) {
  if (!summary) return
  const int = summary.interview || {}
  const sur = summary.survey || {}
  const rec = summary.recovery || {}

  setText('dash-int-live', String(int.live ?? 0))
  setText('dash-int-live-sub', `${int.running ?? 0} running now`)
  setText('dash-int-running', String(int.running ?? 0))
  setText('dash-int-finished', String(int.finished ?? 0))
  setText('dash-int-candidates', String(int.candidates ?? 0))

  setText('dash-sur-live', String(sur.live ?? 0))
  setText('dash-sur-live-sub', `${sur.running ?? 0} running · ${sur.paused ?? 0} paused`)
  setText('dash-sur-responses', String(sur.responses ?? 0))
  setText('dash-sur-resp-sub', sur.sent ? `of ${sur.sent} reached` : '—')
  setText('dash-sur-rate', `${sur.completion_rate ?? 0}%`)
  setText('dash-sur-paused', String(sur.paused ?? 0))

  if (enabled.recovery) {
    const queuePending = Number(rec.queue_pending || 0)
    setText('dash-kpi-calls-made', String(rec.total_calls ?? 0))
    setText('dash-kpi-wa-sent', `${rec.whatsapp_sent ?? 0} sent`)
    setText('dash-kpi-queue', String(queuePending))
    setText('dash-qa-queue', `${queuePending} waiting`)
    if (queuePending > 0) {
      setText('qbadge', String(queuePending))
      showEl('qbadge', 'inline-flex')
    } else {
      hideEl('qbadge')
    }
  }
}

export async function applyDashboardServices() {
  const enabled = getEnabledServices()
  applyServiceSections(enabled)
  if (!getAccessToken()) return
  try {
    const summary = await apiFetch('/dashboard/home-summary')
    const merged = summary?.enabled_services || enabled
    applyServiceSections(merged)
    applyHomeSummary(summary, merged)
  } catch {
    applyServiceSections(enabled)
  }
}

export async function initDashboardBridge() {
  if (!getAccessToken()) return

  const now = new Date()
  const dateLabel = now.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
  setText('tb-s-plain', dateLabel)

  window.applyDashboardServices = applyDashboardServices
  await applyDashboardServices()
}
