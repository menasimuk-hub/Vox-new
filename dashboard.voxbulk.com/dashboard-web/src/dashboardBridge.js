import { apiFetch, getAccessToken } from './lib/api.js'

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

export async function initDashboardBridge() {
  if (!getAccessToken()) return

  const now = new Date()
  const dateLabel = now.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
  setText('tb-s-plain', dateLabel)

  try {
    const metrics = await apiFetch('/dashboard/metrics').catch(() => null)
    if (!metrics) return

    const calls = Number(metrics.total_call_logs || 0)
    const wa = Number(metrics.total_whatsapp_logs || 0)
    const queuePending = Number(
      metrics.appointment_status_counts?.pending ||
      metrics.appointment_status_counts?.missed ||
      metrics.appointment_status_counts?.cancelled ||
      0,
    )

    setText('dash-kpi-calls-made', String(calls))
    setText('dash-kpi-wa-sent', `${wa} sent today`)
    setText('dash-kpi-queue', String(queuePending))
    setText('dash-qa-queue', `${queuePending} patients waiting`)

    if (queuePending > 0) {
      setText('qbadge', String(queuePending))
      showEl('qbadge', 'inline-flex')
    } else {
      hideEl('qbadge')
    }
  } catch {
    /* keep zero defaults */
  }
}
