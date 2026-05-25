import { showLaunchSummaryModal, showSurveyPaymentModal } from './modalBridge.js'
import { surveyRespondedCount } from './surveyUtils.js'
import {
  apiFetch,
  apiUploadFile,
  apiUploadFiles,
  authErrorMessage,
  downloadAuthenticatedFile,
  getAccessToken,
  handleUnauthorizedApiError,
} from './lib/api.js'
import { buildWaFlowFromPayload, createWaPreviewRenderer } from './waSurveyPreview.js'
import {
  getClientContextForApi,
  materialiseScriptPayload,
  setProfileCache,
  setSampleRecipientFirstName,
  syncWaPreviewHeader,
} from './clientContext.js'

const state = {
  surveyOrderId: null,
  interviewOrderId: null,
  surveyFile: null,
  interviewFile: null,
  ordersLoaded: false,
  surveyScriptApproved: false,
  interviewScriptApproved: false,
  surveyScriptPayload: null,
  interviewScriptPayload: null,
  surveyGenerating: false,
  interviewGenerating: false,
  paymentOptions: null,
}

const surveyLaunch = {
  packages: [],
  packagesLoaded: false,
  contactCount: 0,
  contactCountKnown: false,
  selectedPackageId: null,
  packageManual: false,
  quote: null,
  quoting: false,
  quoteError: '',
  paying: false,
  surveyAgents: [],
  agentsLoaded: false,
  selectedAgentId: null,
  agentManual: false,
}

const interviewLaunch = {
  contactCount: 0,
  contactCountKnown: false,
  preview: [],
  quote: null,
  quoting: false,
  quoteError: '',
  interviewAgents: [],
  agentsLoaded: false,
  selectedAgentId: null,
  draftOrderId: null,
  recipients: [],
  intakeSummary: null,
  intakeLoading: false,
  quoteStatusNote: '',
}

const LOG_SURVEY = '[survey]'

const GC_ORDER_FLOW_KEY = 'voxbulk_gc_order_redirect_flow_id'

const waPreview = {
  step: 0,
  flow: null,
  finished: false,
}

let waRenderer = null

async function api(path, options = {}) {
  return apiFetch(path, options)
}

function fmtGbp(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(2)}`
}

function logSurvey(event, detail = {}) {
  console.info(LOG_SURVEY, event, detail)
}

function autoPickSurveyPackage(count, packages) {
  const list = (packages || []).filter((p) => p.is_active !== false)
  if (!list.length) return null
  const n = Math.max(Number(count || 0), 0)
  const fitting = list.filter((p) => Number(p.bundle_size || 0) >= n)
  if (fitting.length) {
    return fitting.reduce((best, pkg) =>
      Number(pkg.bundle_size || 0) < Number(best.bundle_size || 0) ? pkg : best,
    )
  }
  return list.reduce((best, pkg) =>
    Number(pkg.bundle_size || 0) > Number(best.bundle_size || 0) ? pkg : best,
  )
}

function packageLabel(pkg) {
  const size = Number(pkg.bundle_size || 0)
  return `${pkg.label || 'Package'} — ${size} contacts @ ${fmtGbp(pkg.bundle_price_pence)}`
}

async function loadSurveyLaunchPackages() {
  if (surveyLaunch.packagesLoaded && surveyLaunch.packages.length) return surveyLaunch.packages
  try {
    const data = await api('/service-orders/survey-packages')
    surveyLaunch.packages = data?.packages?.ai_call || []
    surveyLaunch.packagesLoaded = true
    logSurvey('packages_loaded', { count: surveyLaunch.packages.length })
    return surveyLaunch.packages
  } catch (e) {
    logSurvey('packages_failed', { message: e.message })
    throw e
  }
}

async function loadSurveyAgents() {
  if (surveyLaunch.agentsLoaded && surveyLaunch.surveyAgents.length) return surveyLaunch.surveyAgents
  try {
    const data = await api('/service-orders/survey-agents')
    surveyLaunch.surveyAgents = data?.agents || []
    surveyLaunch.agentsLoaded = true
    if (!surveyLaunch.selectedAgentId && surveyLaunch.surveyAgents.length) {
      const preferred =
        surveyLaunch.surveyAgents.find((a) => a.is_default_for_org) ||
        surveyLaunch.surveyAgents.find((a) => a.is_platform_default) ||
        surveyLaunch.surveyAgents[0]
      surveyLaunch.selectedAgentId = preferred?.id || null
    }
    renderSurveyAgentSelect()
    logSurvey('agents_loaded', { count: surveyLaunch.surveyAgents.length })
    return surveyLaunch.surveyAgents
  } catch (e) {
    logSurvey('agents_failed', { message: e.message })
    const select = document.getElementById('sur-agent-select')
    if (select) {
      select.innerHTML = '<option value="">No agents available</option>'
    }
    return []
  }
}

function renderSurveyAgentSelect() {
  const select = document.getElementById('sur-agent-select')
  if (!select) return
  const agents = surveyLaunch.surveyAgents
  if (!agents.length) {
    select.innerHTML = '<option value="">No survey agents configured</option>'
    return
  }
  select.innerHTML = agents
    .map((agent) => {
      const label = agent.voice_type_label
        ? `${agent.voice_label} (${agent.voice_type_label})`
        : agent.voice_label
      const suffix = agent.is_default_for_org ? ' · your default' : agent.is_platform_default ? ' · default' : ''
      return `<option value="${agent.id}"${String(agent.id) === String(surveyLaunch.selectedAgentId) ? ' selected' : ''}>${label}${suffix}</option>`
    })
    .join('')
}

function selectedSurveyAgent() {
  return surveyLaunch.surveyAgents.find((a) => String(a.id) === String(surveyLaunch.selectedAgentId)) || null
}

async function loadInterviewAgents() {
  if (interviewLaunch.agentsLoaded && interviewLaunch.interviewAgents.length) return interviewLaunch.interviewAgents
  try {
    const data = await api('/service-orders/interview-agents')
    interviewLaunch.interviewAgents = data?.agents || []
    interviewLaunch.agentsLoaded = true
    if (!interviewLaunch.selectedAgentId && interviewLaunch.interviewAgents.length) {
      const preferred =
        interviewLaunch.interviewAgents.find((a) => a.is_default_for_org) ||
        interviewLaunch.interviewAgents.find((a) => a.is_platform_default) ||
        interviewLaunch.interviewAgents[0]
      interviewLaunch.selectedAgentId = preferred?.id || null
    }
    renderInterviewAgentSelect()
    return interviewLaunch.interviewAgents
  } catch {
    const select = document.getElementById('int-agent-select')
    if (select) select.innerHTML = '<option value="">No agents available</option>'
    return []
  }
}

function renderInterviewAgentSelect() {
  const select = document.getElementById('int-agent-select')
  if (!select) return
  const agents = interviewLaunch.interviewAgents
  if (!agents.length) {
    select.innerHTML = '<option value="">No interview agents configured</option>'
    return
  }
  select.innerHTML = agents
    .map((agent) => {
      const label = agent.voice_type_label
        ? `${agent.voice_label} (${agent.voice_type_label})`
        : agent.voice_label
      const suffix = agent.is_default_for_org ? ' · your default' : agent.is_platform_default ? ' · default' : ''
      return `<option value="${agent.id}"${String(agent.id) === String(interviewLaunch.selectedAgentId) ? ' selected' : ''}>${label}${suffix}</option>`
    })
    .join('')
}

function selectedInterviewAgent() {
  return interviewLaunch.interviewAgents.find((a) => String(a.id) === String(interviewLaunch.selectedAgentId)) || null
}

function escHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function updateInterviewUploadUi(fileCount, label) {
  const zone = document.getElementById('int-upload-zone')
  const statusEl = document.getElementById('int-upload-status')
  if (statusEl && label) {
    statusEl.textContent = label
    statusEl.style.display = 'block'
  } else if (statusEl && !fileCount) {
    statusEl.textContent = ''
    statusEl.style.display = 'none'
  }
  if (zone) zone.classList.toggle('has-file', Boolean(fileCount))
}

function renderInterviewQuoteUi() {
  const panel = document.getElementById('int-launch-pricing')
  const countEl = document.getElementById('int-contact-count')
  const previewWrap = document.getElementById('int-preview-table-wrap')
  const breakdownEl = document.getElementById('int-quote-breakdown')
  const totalEl = document.getElementById('int-quote-total')
  const statusEl = document.getElementById('int-quote-status')
  if (!panel) return

  if (!state.interviewFile) {
    panel.hidden = true
    return
  }

  panel.hidden = false
  if (countEl) {
    countEl.textContent = interviewLaunch.contactCountKnown
      ? `${interviewLaunch.contactCount} candidates uploaded`
      : 'Contact count confirmed at checkout'
  }

  if (previewWrap) {
    const rows = interviewLaunch.preview || []
    previewWrap.innerHTML = rows.length
      ? `<table class="res-table" style="font-size:11px;margin:0"><thead><tr><th>Name</th><th>Phone</th><th>Email</th></tr></thead><tbody>${rows
          .map(
            (r) =>
              `<tr><td>${escHtml(r.name || '—')}</td><td>${escHtml(r.phone || '—')}</td><td>${escHtml(r.email || '—')}</td></tr>`,
          )
          .join('')}</tbody></table>`
      : ''
  }

  if (interviewLaunch.quoting) {
    if (statusEl) statusEl.textContent = 'Calculating quote…'
    return
  }

  if (interviewLaunch.quoteError) {
    if (breakdownEl) breakdownEl.innerHTML = ''
    if (totalEl) totalEl.innerHTML = ''
    if (statusEl) statusEl.textContent = interviewLaunch.quoteError
    return
  }

  const quote = interviewLaunch.quote
  if (!quote) {
    if (breakdownEl) breakdownEl.innerHTML = ''
    if (totalEl) totalEl.innerHTML = ''
    if (statusEl) statusEl.textContent = 'Upload a contact list to see flat-rate pricing'
    return
  }

  const perPerson = (quote.lines || []).find((l) => l.kind === 'per_person' || l.rule_type === 'per_person')
  if (breakdownEl) {
    breakdownEl.innerHTML = (quote.lines || [])
      .map(
        (line) =>
          `<div class="sur-quote-line"><span>${escHtml(line.label || line.detail || 'Line item')}</span><strong>${fmtGbp(line.amount_pence)}</strong></div>`,
      )
      .join('')
  }
  if (totalEl) {
    totalEl.innerHTML = `<span>Total due now</span><span>${quote.total_gbp || fmtGbp(quote.total_pence)}</span>`
  }
  if (statusEl) {
    statusEl.textContent = interviewLaunch.quoteStatusNote
      || (perPerson
        ? `Flat rate · ${fmtGbp(perPerson.unit_price_pence || 0)} per candidate`
        : 'Flat-rate interview pricing')
  }
}

async function refreshInterviewPreviewQuote() {
  if (!state.interviewFile) return
  interviewLaunch.quoting = true
  interviewLaunch.quoteError = ''
  renderInterviewQuoteUi()
  try {
    const data = await apiUploadFile('/service-orders/recipients/preview', state.interviewFile, 'file', {
      service_code: 'interview',
      delivery: 'ai_call',
    })
    interviewLaunch.contactCount = Number(data?.recipient_count || 0)
    interviewLaunch.contactCountKnown = true
    interviewLaunch.preview = data?.preview || []
    interviewLaunch.quote = data?.quote || null
  } catch (e) {
    interviewLaunch.quote = null
    interviewLaunch.quoteError = e.message || 'Could not preview upload'
    interviewLaunch.preview = []
  } finally {
    interviewLaunch.quoting = false
    renderInterviewQuoteUi()
  }
}

async function refreshInterviewQuoteFromDraft() {
  const readyCount = interviewIntakeReadyCount()
  const total = (interviewLaunch.recipients || []).length
  if (!total) {
    interviewLaunch.quote = null
    renderInterviewQuoteUi()
    return
  }
  interviewLaunch.quoting = true
  interviewLaunch.quoteError = ''
  renderInterviewQuoteUi()
  try {
    const quote = await api('/service-orders/quote', {
      method: 'POST',
      body: JSON.stringify({
        service_code: 'interview',
        recipient_count: readyCount || total,
        options: { delivery: 'ai_call' },
      }),
    })
    interviewLaunch.quote = quote
    if (readyCount < total) {
      interviewLaunch.quoteError = ''
      interviewLaunch.quoteStatusNote = `${total - readyCount} candidate(s) missing phone — not included in quote until fixed`
    } else {
      interviewLaunch.quoteStatusNote = ''
    }
  } catch (e) {
    interviewLaunch.quote = null
    interviewLaunch.quoteError = e.message || 'Could not calculate quote'
  } finally {
    interviewLaunch.quoting = false
    renderInterviewQuoteUi()
  }
}

let interviewFileSelectToken = 0

async function onInterviewFileSelected(fileList) {
  await uploadInterviewFiles(fileList)
}

async function uploadInterviewFiles(fileList) {
  const files = Array.from(fileList || []).filter(Boolean)
  if (!files.length) return
  interviewLaunch.intakeLoading = true
  const statusEl = document.getElementById('int-upload-status')
  if (statusEl) {
    statusEl.style.display = 'block'
    statusEl.textContent = `Processing ${files.length} file(s)…`
  }
  try {
    const orderId = await ensureInterviewDraftOrder()
    if (!orderId) throw new Error('Could not start interview draft')
    const data = await apiUploadFiles(`/service-orders/${orderId}/recipients/intake-files`, files, 'files')
    interviewLaunch.recipients = data?.recipients || []
    interviewLaunch.intakeSummary = data?.summary || null
    state.interviewFile = files[0] || null
    renderInterviewCandidateList()
    const count = interviewLaunch.recipients.length
    const parsed = data?.parsed_count || 0
    const contactRows = data?.contact_rows || 0
    const rejected = (data?.rejected_files || []).length
    const statusText = `${count} candidates in list${parsed ? ` · ${parsed} CV(s) parsed` : ''}${contactRows ? ` · ${contactRows} spreadsheet row(s)` : ''}${rejected ? ` · ${rejected} file(s) skipped` : ''}`
    if (statusEl) statusEl.textContent = statusText
    updateInterviewUploadUi(count, statusText)
    if (count === 0) {
      window.toast?.('No candidates added — use Excel, CSV, PDF, DOCX, or ZIP', 'tr')
    } else {
      window.toast?.(`${count} candidates in list — add any missing phones`, 'tg')
    }
  } catch (e) {
    if (statusEl) statusEl.textContent = e.message || 'Upload failed'
    window.toast?.(e.message || 'Could not process upload', 'tr')
  } finally {
    interviewLaunch.intakeLoading = false
  }
}

function renderInterviewKpis(orders, credits) {
  const creditsEl = document.getElementById('int-kpi-credits')
  const creditsSub = document.getElementById('int-kpi-credits-sub')
  const completedEl = document.getElementById('int-kpi-completed')
  const completedSub = document.getElementById('int-kpi-completed-sub')
  const balance = Number(credits?.interview_credits || 0)
  if (creditsEl) creditsEl.textContent = String(balance)
  if (creditsSub) creditsSub.textContent = balance === 1 ? 'promo credit' : 'promo credits'

  const now = new Date()
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
  const completed = (orders || []).filter((o) => {
    if (o.status !== 'completed') return false
    const raw = o.completed_at || o.updated_at || o.created_at
    if (!raw) return false
    const dt = new Date(raw)
    return !Number.isNaN(dt.getTime()) && dt >= monthStart
  })
  const recipients = completed.reduce((sum, o) => sum + Number(o.recipient_count || 0), 0)
  const reached = completed.reduce((sum, o) => sum + Number(o.report?.completed || o.report?.reached || 0), 0)
  const pct = recipients > 0 ? Math.round((reached / recipients) * 100) : 0

  if (completedEl) completedEl.textContent = String(completed.length)
  if (completedSub) {
    completedSub.textContent =
      completed.length && recipients
        ? `${reached} of ${recipients} reached (${pct}%)`
        : completed.length
          ? `${recipients} candidates`
          : 'No completed campaigns this month'
  }
}

async function openInterviewResults(orderId) {
  state.interviewOrderId = orderId
  if (typeof window.goNav === 'function') window.goNav('results-i')

  const bc = document.getElementById('int-results-bc-title')
  const banner = document.getElementById('int-results-phase-banner')
  const bannerText = document.getElementById('int-results-phase-banner-text')
  const mockNote = document.getElementById('int-results-mock-note')

  try {
    const order = await api(`/service-orders/${encodeURIComponent(orderId)}`)
    const title = order.title || 'Interview campaign'
    if (bc) bc.textContent = title
    if (banner) banner.style.display = 'flex'
    if (bannerText) {
      bannerText.textContent = `${title} — sample data shown until live call results are available (Phase 2).`
    }
    if (mockNote) mockNote.style.display = 'none'
  } catch {
    if (bc) bc.textContent = 'Interview campaign'
    if (banner) banner.style.display = 'flex'
    if (mockNote) mockNote.style.display = ''
  }
}

function cvQualityBadge(quality) {
  const q = String(quality || 'missing')
  if (q === 'good') return '<span class="bdg bg">CV good</span>'
  if (q === 'low_quality') return '<span class="bdg ba">CV low</span>'
  if (q === 'corrupt') return '<span class="bdg br">CV error</span>'
  return '<span class="bdg bb">No CV</span>'
}

function renderInterviewCandidateList() {
  const panel = document.getElementById('int-candidate-panel')
  const summaryEl = document.getElementById('int-intake-summary')
  const tableWrap = document.getElementById('int-candidate-table-wrap')
  const recipients = interviewLaunch.recipients || []
  if (!panel || !tableWrap) return

  if (!recipients.length) {
    panel.hidden = true
    return
  }

  panel.hidden = false
  const summary = interviewLaunch.intakeSummary || {}
  if (summaryEl) {
    summaryEl.textContent = `${summary.total || recipients.length} candidates · ${summary.ready || 0} ready · ${summary.missing_phone || 0} need phone · ${summary.cv_good || 0} good CVs`
  }

  tableWrap.innerHTML = `<table class="res-table int-candidate-table" style="font-size:11.5px">
    <thead><tr><th>Name</th><th>Phone</th><th>Email</th><th>CV</th><th>Issues</th><th></th></tr></thead>
    <tbody>${recipients
      .map((r) => {
        const phoneCell = r.phone
          ? `<button type="button" class="int-cell-btn" data-int-edit="${r.id}" data-field="phone">${escHtml(r.phone)}</button>`
          : `<button type="button" class="int-cell-btn is-missing" data-int-edit="${r.id}" data-field="phone">Add phone</button>`
        const emailCell = r.email
          ? `<button type="button" class="int-cell-btn" data-int-edit="${r.id}" data-field="email">${escHtml(r.email)}</button>`
          : `<button type="button" class="int-cell-btn is-missing" data-int-edit="${r.id}" data-field="email">Add email</button>`
        const issues = (r.intake_errors || []).map((e) => escHtml(e)).join('<br/>') || '—'
        return `<tr>
          <td>${escHtml(r.name || '—')}</td>
          <td>${phoneCell}</td>
          <td>${emailCell}</td>
          <td>${cvQualityBadge(r.cv_quality)}${r.cv_filename ? `<div class="muted" style="font-size:10px;margin-top:2px">${escHtml(r.cv_filename)}</div>` : ''}</td>
          <td style="font-size:10.5px;color:var(--amb)">${issues}</td>
          <td><button type="button" class="btn bsm btnr int-del-btn" data-int-del="${r.id}" title="Remove"><i class="ti ti-trash"></i></button></td>
        </tr>`
      })
      .join('')}</tbody></table>`

  tableWrap.querySelectorAll('[data-int-edit]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-int-edit')
      const field = btn.getAttribute('data-field')
      void editInterviewRecipientField(id, field)
    })
  })
  tableWrap.querySelectorAll('[data-int-del]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      const id = btn.getAttribute('data-int-del')
      void deleteInterviewRecipient(id)
    })
  })

  interviewLaunch.contactCount = recipients.length
  interviewLaunch.contactCountKnown = true
  void refreshInterviewQuoteFromDraft()
}

async function ensureInterviewDraftOrder() {
  if (interviewLaunch.draftOrderId) return interviewLaunch.draftOrderId
  const role = (document.getElementById('int-role')?.value || '').trim()
  const criteria = (document.getElementById('int-criteria')?.value || '').trim()
  const title = role || 'Interview draft'
  const data = await api('/service-orders/interview/draft', {
    method: 'POST',
    body: JSON.stringify({ title, role, criteria }),
  })
  interviewLaunch.draftOrderId = data?.order?.id || null
  state.interviewOrderId = interviewLaunch.draftOrderId
  interviewLaunch.recipients = data?.recipients || []
  interviewLaunch.intakeSummary = data?.summary || null
  renderInterviewCandidateList()
  return interviewLaunch.draftOrderId
}

async function editInterviewRecipientField(recipientId, field) {
  const orderId = interviewLaunch.draftOrderId
  if (!orderId || !recipientId) return
  const recipient = (interviewLaunch.recipients || []).find((r) => String(r.id) === String(recipientId))
  const label = field === 'phone' ? 'Phone number' : 'Email'
  const current = field === 'phone' ? recipient?.phone || '' : recipient?.email || ''
  const value = window.prompt(`${label} for ${recipient?.name || 'candidate'}:`, current)
  if (value === null) return
  try {
    const data = await api(`/service-orders/${orderId}/recipients/${recipientId}`, {
      method: 'PATCH',
      body: JSON.stringify({ [field]: value.trim() }),
    })
    interviewLaunch.recipients = data?.recipients || []
    interviewLaunch.intakeSummary = data?.summary || null
    renderInterviewCandidateList()
  } catch (e) {
    window.toast?.(e.message || 'Could not update candidate', 'tr')
  }
}

async function deleteInterviewRecipient(recipientId) {
  const orderId = interviewLaunch.draftOrderId
  if (!orderId || !recipientId) return
  if (!window.confirm('Remove this candidate from the list?')) return
  try {
    const data = await api(`/service-orders/${orderId}/recipients/${recipientId}`, { method: 'DELETE' })
    interviewLaunch.recipients = data?.recipients || []
    interviewLaunch.intakeSummary = data?.summary || null
    renderInterviewCandidateList()
    window.toast?.('Candidate removed', 'tw')
  } catch (e) {
    window.toast?.(e.message || 'Could not remove candidate', 'tr')
  }
}

function interviewIntakeReadyCount() {
  return (interviewLaunch.recipients || []).filter((r) => r.intake_ready).length
}

function bindInterviewLaunchUi() {
  document.getElementById('int-agent-select')?.addEventListener('change', (e) => {
    interviewLaunch.selectedAgentId = e.target.value || null
  })

  if (typeof window.updateIntWindow === 'function') window.updateIntWindow()
}

async function countContactsInFile(file) {
  if (!file) return 0
  const lower = file.name.toLowerCase()
  if (!lower.endsWith('.csv')) return null
  try {
    const chunk = await file.slice(0, 512 * 1024).text()
    const lines = chunk.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
    if (lines.length < 2) return 0
    let count = 0
    for (let i = 1; i < lines.length; i += 1) {
      const cols = lines[i].split(',').map((c) => c.trim().replace(/^"|"$/g, ''))
      if (cols.some(Boolean)) count += 1
    }
    return count
  } catch {
    return null
  }
}

function renderSurveyPackageSelect() {
  const select = document.getElementById('sur-package-select')
  if (!select) return
  const pkgs = surveyLaunch.packages
  select.innerHTML = pkgs
    .map(
      (pkg) =>
        `<option value="${pkg.id}"${String(pkg.id) === String(surveyLaunch.selectedPackageId) ? ' selected' : ''}>${packageLabel(pkg)}</option>`,
    )
    .join('')
}

function renderSurveyQuoteUi() {
  const panel = document.getElementById('sur-launch-pricing')
  const countEl = document.getElementById('sur-contact-count')
  const breakdownEl = document.getElementById('sur-quote-breakdown')
  const totalEl = document.getElementById('sur-quote-total')
  const statusEl = document.getElementById('sur-quote-status')
  const payBtn = document.getElementById('sur-pay-schedule')
  if (!panel) return

  if (!state.surveyFile) {
    panel.hidden = true
    if (payBtn) payBtn.disabled = !!surveyLaunch.paying
    return
  }

  panel.hidden = false
  if (countEl) {
    countEl.textContent = surveyLaunch.contactCountKnown
      ? `${surveyLaunch.contactCount} contacts uploaded`
      : 'Excel upload — exact contact count confirmed at checkout'
  }

  if (surveyLaunch.quoting) {
    if (statusEl) statusEl.textContent = 'Calculating quote…'
    if (payBtn) payBtn.disabled = !!surveyLaunch.paying
    return
  }

  if (surveyLaunch.quoteError) {
    if (breakdownEl) breakdownEl.innerHTML = ''
    if (totalEl) totalEl.innerHTML = ''
    if (statusEl) statusEl.textContent = surveyLaunch.quoteError
    if (payBtn) payBtn.disabled = !!surveyLaunch.paying
    return
  }

  const quote = surveyLaunch.quote
  if (!quote) {
    if (breakdownEl) breakdownEl.innerHTML = ''
    if (totalEl) totalEl.innerHTML = ''
    if (statusEl) statusEl.textContent = surveyLaunch.contactCountKnown
      ? 'Select a package to see pricing'
      : 'Upload CSV for live pricing, or continue to checkout'
    if (payBtn) payBtn.disabled = !!surveyLaunch.paying
    return
  }

  const bundleLine = (quote.lines || []).find((l) => l.kind === 'bundle')
  const setupLine = (quote.lines || []).find((l) => l.kind === 'setup')
  const overageLine = (quote.lines || []).find((l) => l.kind === 'overage')
  const covered = bundleLine?.contacts_included || bundleLine?.bundle_size || 0

  if (breakdownEl) {
    breakdownEl.innerHTML = [
      `<div class="sur-quote-line"><span>Uploaded contacts</span><strong>${quote.recipient_count}</strong></div>`,
      bundleLine
        ? `<div class="sur-quote-line"><span>${bundleLine.label} (covers ${covered})</span><strong>${fmtGbp(bundleLine.amount_pence)}</strong></div>`
        : '',
      overageLine
        ? `<div class="sur-quote-line isExtra"><span>${overageLine.extra_contacts || ''} extra contacts</span><strong>${fmtGbp(overageLine.amount_pence)}</strong></div>`
        : '',
      setupLine
        ? `<div class="sur-quote-line"><span>${setupLine.label || 'Setup fee'}</span><strong>${fmtGbp(setupLine.amount_pence)}</strong></div>`
        : '',
    ]
      .filter(Boolean)
      .join('')
  }

  if (totalEl) {
    totalEl.innerHTML = `<span>Total due now</span><span>${quote.total_gbp || fmtGbp(quote.total_pence)}</span>`
  }

  if (statusEl) {
    statusEl.textContent = surveyLaunch.packageManual
      ? 'Manual package selected'
      : 'Best-fit package auto-selected'
  }

  if (payBtn) payBtn.disabled = !!surveyLaunch.paying
}

async function ingestRecipientFile(file, serviceCode) {
  if (!file) {
    if (serviceCode === 'survey') setSampleRecipientFirstName('')
    return
  }
  const firstName = await parseFirstNameFromRecipientFile(file)
  if (serviceCode === 'survey') setSampleRecipientFirstName(firstName)
}

function updateSurveyUploadUi(file, { contactCount = null, contactCountKnown = false } = {}) {
  const zone = document.getElementById('sur-upload-zone')
  const label = document.getElementById('sur-upload-filename')
  if (label) {
    if (file) {
      const countText =
        contactCountKnown && contactCount != null ? ` · ${contactCount} contacts` : ''
      label.textContent = `Selected: ${file.name}${countText}`
      label.style.display = 'block'
    } else {
      label.textContent = ''
      label.style.display = 'none'
    }
  }
  if (zone) {
    zone.classList.toggle('has-file', Boolean(file))
    if (file) zone.classList.remove('error')
  }
}

async function refreshSurveyQuote() {
  if (!state.surveyFile) return
  await loadSurveyLaunchPackages()
  renderSurveyPackageSelect()

  if (!surveyLaunch.selectedPackageId && surveyLaunch.packages.length) {
    const picked = autoPickSurveyPackage(surveyLaunch.contactCount, surveyLaunch.packages)
    surveyLaunch.selectedPackageId = picked?.id || surveyLaunch.packages[0]?.id || null
    surveyLaunch.packageManual = false
    renderSurveyPackageSelect()
  }

  if (!surveyLaunch.selectedPackageId) {
    surveyLaunch.quote = null
    surveyLaunch.quoteError = 'No AI call packages available'
    renderSurveyQuoteUi()
    return
  }

  if (!surveyLaunch.contactCountKnown) {
    surveyLaunch.quote = null
    surveyLaunch.quoteError = ''
    renderSurveyQuoteUi()
    return
  }

  surveyLaunch.quoting = true
  surveyLaunch.quoteError = ''
  renderSurveyQuoteUi()
  logSurvey('quote_start', {
    contacts: surveyLaunch.contactCount,
    package_id: surveyLaunch.selectedPackageId,
  })

  try {
    const quote = await api('/service-orders/quote', {
      method: 'POST',
      body: JSON.stringify({
        service_code: 'survey',
        recipient_count: surveyLaunch.contactCount,
        options: {
          survey_channel: 'ai_call',
          package_id: surveyLaunch.selectedPackageId,
        },
      }),
    })
    surveyLaunch.quote = quote
    logSurvey('quote_ok', { total_pence: quote.total_pence, package_id: quote.selected_package_id })
  } catch (e) {
    surveyLaunch.quote = null
    surveyLaunch.quoteError = e.message || 'Could not calculate quote'
    logSurvey('quote_failed', { message: surveyLaunch.quoteError })
  } finally {
    surveyLaunch.quoting = false
    renderSurveyQuoteUi()
  }
}

let surveyHandlersAbort = null
let surveyFileSelectToken = 0
let lastSurveyFileKey = ''

function surveyFileKey(file) {
  if (!file) return ''
  return `${file.name}:${file.size}:${file.lastModified}`
}

async function onSurveyFileSelected(file) {
  const fileKey = surveyFileKey(file)
  if (file && fileKey === lastSurveyFileKey && state.surveyFile === file) return

  const token = ++surveyFileSelectToken
  state.surveyFile = file || null
  surveyLaunch.quote = null
  surveyLaunch.quoteError = ''
  updateSurveyUploadUi(file)
  if (!file) {
    lastSurveyFileKey = ''
    surveyLaunch.contactCount = 0
    surveyLaunch.contactCountKnown = false
    renderSurveyQuoteUi()
    return
  }

  lastSurveyFileKey = fileKey

  try {
    await ingestRecipientFile(file, 'survey')
    if (token !== surveyFileSelectToken) return

    const count = await countContactsInFile(file)
    if (token !== surveyFileSelectToken) return

    if (count === null) {
      surveyLaunch.contactCountKnown = false
      surveyLaunch.contactCount = 0
      logSurvey('contacts_unknown', { filename: file.name })
    } else {
      surveyLaunch.contactCountKnown = true
      surveyLaunch.contactCount = count
      logSurvey('contacts_counted', { count })
    }

    updateSurveyUploadUi(file, {
      contactCount: surveyLaunch.contactCount,
      contactCountKnown: surveyLaunch.contactCountKnown,
    })

    if (!surveyLaunch.packageManual) {
      await loadSurveyLaunchPackages()
      if (token !== surveyFileSelectToken) return
      const picked = autoPickSurveyPackage(surveyLaunch.contactCount, surveyLaunch.packages)
      surveyLaunch.selectedPackageId = picked?.id || null
    }

    await refreshSurveyQuote()
  } catch (e) {
    if (token !== surveyFileSelectToken) return
    console.error('[survey] file_select_failed', e)
    notifyUser(e?.message || 'Could not read contact file', 'tr')
    renderSurveyQuoteUi()
  }
}

function bindSurveyControl(id, event, handler, signal) {
  const el = document.getElementById(id)
  if (!el) return
  el.addEventListener(event, handler, { signal })
}

function bindSurveyPageHandlers() {
  surveyHandlersAbort?.abort()
  surveyHandlersAbort = new AbortController()
  const { signal } = surveyHandlersAbort

  bindSurveyControl(
    'sur-pay-schedule',
    'click',
    (event) => {
      event.preventDefault()
      void runSurveyLaunchFlow()
    },
    signal,
  )
  bindSurveyControl(
    'sur-ai-generate',
    'click',
    (event) => {
      event.preventDefault()
      void generateServiceScript('survey')
    },
    signal,
  )
  bindSurveyControl(
    'sur-ai-regen',
    'click',
    (event) => {
      event.preventDefault()
      void generateServiceScript('survey')
    },
    signal,
  )
  bindSurveyControl(
    'sur-ai-approve',
    'click',
    (event) => {
      event.preventDefault()
      approveServiceScript('survey')
    },
    signal,
  )
  bindSurveyControl(
    'sur-template-dl',
    'click',
    (event) => {
      event.preventDefault()
      event.stopPropagation()
      void downloadAuthenticatedFile('/service-orders/template.csv', 'voxbulk-contacts-template.csv').catch(
        (err) => notifyUser(err.message || 'Could not download template', 'tr'),
      )
    },
    signal,
  )
  bindSurveyControl(
    'sur-file-input',
    'change',
    (event) => {
      void onSurveyFileSelected(event.target.files?.[0] || null)
      event.target.value = ''
    },
    signal,
  )
  bindSurveyControl(
    'sur-package-select',
    'change',
    (event) => {
      surveyLaunch.selectedPackageId = event.target.value || null
      surveyLaunch.packageManual = true
      logSurvey('package_manual', { package_id: surveyLaunch.selectedPackageId })
      void refreshSurveyQuote()
    },
    signal,
  )
  bindSurveyControl(
    'sur-agent-select',
    'change',
    (event) => {
      surveyLaunch.selectedAgentId = event.target.value || null
      surveyLaunch.agentManual = true
      logSurvey('agent_selected', { agent_id: surveyLaunch.selectedAgentId })
    },
    signal,
  )
}

function bindSurveyLaunchUi() {
  bindSurveyPageHandlers()
}

async function ensureAuthenticatedSession() {
  const token = getAccessToken()
  if (!token) {
    const err = new Error('Your session expired. Please sign in again.')
    err.status = 401
    throw err
  }
  await apiFetch('/auth/me', { redirectOn401: false })
}

function reportSurveyFlowError(err, fallbackMessage) {
  const message = authErrorMessage(err) || fallbackMessage
  notifyUser(message, 'tr')
  handleUnauthorizedApiError(err)
}

async function schedulePaidSurveyOrder(order) {
  try {
    const scheduled = await api(`/service-orders/${order.id}/schedule`, { method: 'POST' })
    logSurvey('scheduled', { order_id: order.id, status: scheduled.status })
    return scheduled
  } catch (e) {
    logSurvey('schedule_failed', { order_id: order.id, message: e.message })
    return order
  }
}

async function runSurveyLaunchFlow() {
  logSurvey('pay_button_clicked')
  try {
    if (surveyLaunch.paying) return

    clearSurveyValidationUi()
    const errors = collectSurveyLaunchValidationErrors()

    if (errors.length > 0) {
      showSurveyValidationErrors(errors)
      return
    }

    let agent = selectedSurveyAgent()
    try {
      await ensureAuthenticatedSession()
      await loadSurveyLaunchPackages()
      await loadSurveyAgents()
      agent = selectedSurveyAgent()
      if (!surveyLaunch.selectedPackageId && surveyLaunch.packages.length) {
        const picked = autoPickSurveyPackage(surveyLaunch.contactCount, surveyLaunch.packages)
        surveyLaunch.selectedPackageId = picked?.id || surveyLaunch.packages[0]?.id || null
        renderSurveyPackageSelect()
        await refreshSurveyQuote()
      }
      if (!surveyLaunch.selectedPackageId) {
        showSurveyValidationErrors(['Please select an AI call package.'])
        return
      }
      if (!agent && surveyLaunch.surveyAgents.length) {
        const msg = 'Please select an AI voice agent.'
        showSurveyValidationErrors([msg])
        markSurveyFieldError('sur-agent-select', 'sur-hint-agent', msg)
        return
      }

      const sched = schedulePayload('sur')
      if (!sched.scheduled_start_at) {
        showSurveyValidationErrors(['Please check your schedule dates and times.'])
        return
      }

      const quoteText = surveyLaunch.quote
        ? surveyLaunch.quote.total_gbp || fmtGbp(surveyLaunch.quote.total_pence)
        : 'Quoted at checkout'
      if (!confirmSurveyLaunchSummary({ agent, sched, quoteText })) return
    } catch (e) {
      reportSurveyFlowError(e, 'Could not prepare survey checkout')
      return
    }

    surveyLaunch.paying = true
    renderSurveyQuoteUi()
    logSurvey('launch_start')

    const title = (document.getElementById('sur-goal')?.value || 'Survey campaign').trim().slice(0, 120)
    const branding = getClientContextForApi()
    agent = selectedSurveyAgent()
    const agentLabel = agent?.name || agent?.voice_label || ''
    const config = {
      goal: document.getElementById('sur-goal')?.value || '',
      survey_channel: 'ai_call',
      package_id: surveyLaunch.selectedPackageId,
      channels: ['call'],
      contact_method: 'AI phone call',
      script_mode: scriptModeFromButtons('survey'),
      approved_script: state.surveyScriptPayload?.script_text || '',
      script_questions: state.surveyScriptPayload?.questions || [],
      system_prompt: state.surveyScriptPayload?.system_prompt || '',
      script_approved: state.surveyScriptApproved,
      organisation_name: branding.organisation_name,
      survey_organiser_name: agentLabel || branding.survey_organiser_name,
      clinic_name: branding.organisation_name,
    }
    if (agent) {
      config.agent_id = agent.id
      config.agent_voice_label = agent.voice_label
    }

    try {
      let order = await api('/service-orders', {
        method: 'POST',
        body: JSON.stringify({ service_code: 'survey', title, config }),
      })
      order = await uploadRecipients(order.id, state.surveyFile)
      await api(`/service-orders/${order.id}`, {
        method: 'PATCH',
        body: JSON.stringify(schedulePayload('sur')),
      })
      order = await api(`/service-orders/${order.id}/quote`, { method: 'POST' })

      logSurvey('order_quoted', {
        order_id: order.id,
        total: order.quote_total_gbp,
        contacts: order.recipient_count,
      })

      await offerSurveyPayment(order)
    } catch (e) {
      reportSurveyFlowError(e, 'Could not create survey order')
      logSurvey('launch_failed', { message: e.message, status: e.status })
    } finally {
      surveyLaunch.paying = false
      renderSurveyQuoteUi()
    }
  } catch (err) {
    console.error('[survey] launch_unhandled', err)
    reportSurveyFlowError(err, 'Pay and schedule failed — please try again')
    surveyLaunch.paying = false
    renderSurveyQuoteUi()
  }
}

let lastUserNotice = { message: '', type: '', at: 0 }

function notifyUser(message, type = 'tg') {
  const msg = String(message || '').trim()
  if (!msg) return
  const now = Date.now()
  if (lastUserNotice.message === msg && lastUserNotice.type === type && now - lastUserNotice.at < 2500) return
  lastUserNotice = { message: msg, type, at: now }
  if (typeof window.toast === 'function') window.toast(msg, type)
  else if (typeof toast === 'function') toast(msg, type)
  else window.alert(msg)
}

function clearSurveyValidationUi() {
  const banner = document.getElementById('sur-validation-errors')
  if (banner) banner.style.display = 'none'
  ;[
    'sur-ai-script',
    'sur-ai-approve',
    'sur-start-date',
    'sur-start-time',
    'sur-end-date',
    'sur-end-time',
    'sur-agent-select',
    'sur-upload-zone',
  ].forEach((id) => document.getElementById(id)?.classList.remove('error'))
  ;[
    'sur-hint-script',
    'sur-hint-approve',
    'sur-hint-start-date',
    'sur-hint-start-time',
    'sur-hint-end-date',
    'sur-hint-end-time',
    'sur-hint-upload',
    'sur-hint-agent',
  ].forEach((id) => setSurveyFieldHint(id, ''))
}

function setSurveyFieldHint(hintId, message) {
  const el = document.getElementById(hintId)
  if (!el) return
  el.textContent = message || ''
  el.classList.toggle('error-hint', Boolean(message))
}

function markSurveyFieldError(fieldId, hintId, message) {
  document.getElementById(fieldId)?.classList.add('error')
  if (hintId) setSurveyFieldHint(hintId, message)
}

function formatScheduleLabel(isoValue) {
  if (!isoValue) return 'Not set'
  const dt = new Date(isoValue)
  if (Number.isNaN(dt.getTime())) return isoValue
  return dt.toLocaleString(undefined, {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function confirmSurveyLaunchSummary({ agent, sched, quoteText }) {
  const contactLine = surveyLaunch.contactCountKnown
    ? `${surveyLaunch.contactCount} contacts`
    : state.surveyFile?.name || 'Uploaded file'
  return showLaunchSummaryModal({
    lines: [
      'Please confirm your survey launch:',
      '',
      'Prompt: Approved',
      `Contacts: ${contactLine}`,
      `Start: ${formatScheduleLabel(sched.scheduled_start_at)}`,
      `End: ${formatScheduleLabel(sched.scheduled_end_at)}`,
      `Voice agent: ${agent?.name || agent?.voice_label || 'Default'}`,
      `Total: ${quoteText}`,
      '',
      'You will choose how to pay on the next step.',
    ],
  })
}

function collectSurveyLaunchValidationErrors() {
  const errors = []
  const scriptEl = document.getElementById('sur-ai-script')
  const approveBtn = document.getElementById('sur-ai-approve')
  const startDateEl = document.getElementById('sur-start-date')
  const startTimeEl = document.getElementById('sur-start-time')
  const endDateEl = document.getElementById('sur-end-date')
  const endTimeEl = document.getElementById('sur-end-time')

  if (startDateEl?.value && !endDateEl?.value) {
    endDateEl.value = startDateEl.value
  }

  if (!state.surveyScriptApproved) {
    const msg = 'Please approve the prompt before continuing.'
    errors.push(msg)
    scriptEl?.classList.add('error')
    approveBtn?.classList.add('error')
    setSurveyFieldHint('sur-hint-script', msg)
    setSurveyFieldHint('sur-hint-approve', msg)
    showAiPanel('sur', true)
  }

  if (!startDateEl?.value?.trim()) {
    const msg = 'Please select a date.'
    errors.push(msg)
    markSurveyFieldError('sur-start-date', 'sur-hint-start-date', msg)
  }
  if (!startTimeEl?.value?.trim()) {
    const msg = 'Please select a time.'
    errors.push(msg)
    markSurveyFieldError('sur-start-time', 'sur-hint-start-time', msg)
  }
  if (!endDateEl?.value?.trim()) {
    const msg = 'Please select an end date.'
    errors.push(msg)
    markSurveyFieldError('sur-end-date', 'sur-hint-end-date', msg)
  }
  if (!endTimeEl?.value?.trim()) {
    const msg = 'Please select an end time.'
    errors.push(msg)
    markSurveyFieldError('sur-end-time', 'sur-hint-end-time', msg)
  }
  if (!state.surveyFile) {
    const msg = 'Please upload a contact list.'
    errors.push(msg)
    document.getElementById('sur-upload-zone')?.classList.add('error')
    setSurveyFieldHint('sur-hint-upload', msg)
  }

  return errors
}

function showSurveyValidationErrors(errors) {
  const unique = [...new Set(errors.filter(Boolean))]
  const banner = document.getElementById('sur-validation-errors')
  if (!banner) {
    notifyUser(unique.length === 1 ? unique[0] : unique.join('\n'), 'tr')
    return
  }

  let html = '<i class="ti ti-alert-circle"></i>'
  if (unique.length === 1) {
    html += `<span>${escHtml(unique[0])}</span>`
  } else {
    html += `<div><div style="font-weight:700;margin-bottom:6px">Please fix the following:</div><ul class="validation-list">${unique.map((e) => `<li>${escHtml(e)}</li>`).join('')}</ul></div>`
  }
  banner.innerHTML = html
  banner.style.display = 'flex'
  banner.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

async function offerSurveyPayment(order) {
  try {
    await loadPaymentOptions()
  } catch {
    if (!state.paymentOptions) {
      state.paymentOptions = { cash_available: true, gocardless_available: false }
    }
  }

  let promoAvailable = false
  let promoCredits = 0
  try {
    const credits = await api('/service-orders/credits')
    promoCredits = Number(credits?.survey_credits || 0)
    promoAvailable = promoCredits >= Number(order.recipient_count || 0) && order.recipient_count > 0
  } catch {
    /* ignore */
  }

  const gc = Boolean(state.paymentOptions?.gocardless_available)
  const cash = state.paymentOptions?.cash_available !== false
  const breakdown = (order.quote_breakdown || []).map((l) => l.detail || l.label).filter(Boolean)
  const amountLabel = order.quote_total_gbp || fmtGbp(order.quote_total_pence)

  const choice = await showSurveyPaymentModal({
    title: 'Pay for survey',
    amountLabel,
    breakdown,
    note: cash
      ? 'Cash payments need admin approval before calls can start. GoCardless is instant when configured.'
      : 'Choose your payment method below.',
    gocardlessAvailable: gc,
    cashAvailable: cash,
    promoAvailable,
    promoLabel: promoAvailable ? `Use ${promoCredits} promo credits` : '',
  })

  if (choice === 'promo' && promoAvailable) {
    await submitSurveyPromoCreditPayment(order.id)
    return
  }
  if (choice === 'gocardless' && gc) {
    await startGocardlessOrderPayment(order.id)
    return
  }
  if (choice === 'cash' && cash) {
    await submitSurveyCashPayment(order.id)
  }
}

async function submitSurveyPromoCreditPayment(orderId) {
  try {
    const paid = await api(`/service-orders/${orderId}/pay-promo-credits`, { method: 'POST' })
    const scheduled = await schedulePaidSurveyOrder(paid)
    window.toast?.(
      scheduled.status === 'scheduled' ? 'Paid — survey scheduled' : 'Paid — survey ready',
      'tg',
    )
    await loadOrdersIntoUi()
    resetSurveyLaunchForm()
  } catch (e) {
    window.toast?.(e.message || 'Could not use promo credits', 'tr')
  }
}

async function submitSurveyCashPayment(orderId) {
  try {
    const paid = await api(`/service-orders/${orderId}/pay-cash`, {
      method: 'POST',
      body: JSON.stringify({ note: 'Cash payment submitted from dashboard' }),
    })
    logSurvey('cash_payment_submitted', { order_id: orderId, payment_status: paid.payment_status })
    if (paid.payment_status === 'approved') {
      const scheduled = await schedulePaidSurveyOrder(paid)
      window.toast?.(
        scheduled.status === 'scheduled' ? 'Payment approved — survey scheduled' : 'Payment approved — survey ready',
        'tg',
      )
    } else {
      window.toast?.('Payment submitted — waiting for admin approval', 'tg')
    }
    await loadOrdersIntoUi()
    resetSurveyLaunchForm()
  } catch (e) {
    logSurvey('cash_payment_failed', { order_id: orderId, error: e.message })
    window.toast?.(e.message || 'Payment submit failed', 'tr')
  }
}

function resetSurveyLaunchForm() {
  state.surveyFile = null
  state.surveyScriptApproved = false
  state.surveyScriptPayload = null
  surveyLaunch.contactCount = 0
  surveyLaunch.contactCountKnown = false
  surveyLaunch.selectedPackageId = null
  surveyLaunch.packageManual = false
  surveyLaunch.quote = null
  surveyLaunch.quoteError = ''
  const fileInput = document.getElementById('sur-file-input')
  if (fileInput) fileInput.value = ''
  lastSurveyFileKey = ''
  document.getElementById('sur-goal') && (document.getElementById('sur-goal').value = '')
  document.getElementById('sur-ai-script') && (document.getElementById('sur-ai-script').value = '')
  showAiPanel('sur', false)
  setAiStatus('sur', false)
  renderSurveyQuoteUi()
}

function deliveryFromInterviewForm() {
  return 'ai_call'
}

function scriptModeFromButtons(serviceCode) {
  if (serviceCode === 'survey') return state.surveyScriptApproved ? 'fixed' : 'fixed'
  return state.interviewScriptApproved ? 'fixed' : 'fixed'
}

function surveyUsesWhatsApp() {
  return /whatsapp/i.test(selectValue(document.getElementById('sur-contact-method')))
}

function surveyChannels() {
  const method = selectValue(document.getElementById('sur-contact-method'))
  if (/both/i.test(method)) return ['whatsapp', 'call']
  if (/whatsapp/i.test(method)) return ['whatsapp']
  return ['call']
}

function resolveSurveyPayload() {
  const scriptText = (document.getElementById('sur-ai-script')?.value || '').trim()
  const base = state.surveyScriptPayload || {}
  return materialiseScriptPayload(
    {
      ...base,
      script_text: scriptText || base.script_text || '',
      questions: base.questions || [],
      whatsapp_flow: base.whatsapp_flow,
      intro: base.intro,
      closing: base.closing,
    },
    { forPreview: true },
  )
}

function getWaRenderer() {
  const host = document.getElementById('sur-wa-chat')
  if (!host) return null
  if (!waRenderer) {
    waRenderer = createWaPreviewRenderer(host, { onProgress: updateWaProgress })
  }
  return waRenderer
}

function syncSurveyWhatsAppUi() {
  const btn = document.getElementById('sur-wa-preview-btn')
  if (!btn) return
  const show = surveyUsesWhatsApp()
  btn.style.display = show ? 'inline-flex' : 'none'
}

function updateWaProgress() {
  const flow = waPreview.flow
  const total = flow?.questions?.length || 0
  const stepInd = document.getElementById('sur-wa-step-ind')
  const prog = document.getElementById('sur-wa-progress')
  if (!stepInd || !prog) return

  if (waPreview.finished || waPreview.step > total) {
    prog.style.width = '100%'
    stepInd.textContent = 'Completed ✓'
    return
  }
  if (waPreview.step === 0) {
    prog.style.width = '0%'
    stepInd.textContent = total ? `0 of ${total} answered` : 'Tap Start to begin'
    return
  }

  const answered = Math.min(waPreview.step - 1, total)
  prog.style.width = total ? `${Math.round((answered / total) * 100)}%` : '0%'
  stepInd.textContent = `${answered} of ${total} answered`
}

function clearWaPreviewUi() {
  const chat = document.getElementById('sur-wa-chat')
  if (chat) chat.innerHTML = ''
}

function showWaStep() {
  const flow = waPreview.flow
  const renderer = getWaRenderer()
  if (!flow || !renderer) return
  const qCount = flow.questions?.length || 0

  if (waPreview.step === 0) {
    renderer.appendBotMessage({ text: flow.intro, reply_type: 'intro' }, {
      intro: true,
      onPick: () => advanceWaPreview('Start survey →'),
    })
    updateWaProgress()
    return
  }

  if (waPreview.step > 0 && waPreview.step <= qCount) {
    const q = flow.questions[waPreview.step - 1]
    renderer.appendBotMessage(q, {
      onPick: (answer) => advanceWaPreview(answer),
    })
    updateWaProgress()
    return
  }

  if (!waPreview.finished) {
    waPreview.finished = true
    renderer.appendBotMessage({ text: flow.closing, reply_type: 'closing' }, { closing: true })
    updateWaProgress()
  }
}

function advanceWaPreview(answer) {
  if (waPreview.finished) return
  getWaRenderer()?.appendUserBubble(answer)
  waPreview.step += 1
  setTimeout(showWaStep, 400)
}

function resetSurveyWaPreview() {
  waPreview.step = 0
  waPreview.finished = false
  waPreview.flow = buildWaFlowFromPayload(resolveSurveyPayload())
  waRenderer = null
  clearWaPreviewUi()
  showWaStep()
}

function openSurveyWaPreview() {
  if (!surveyUsesWhatsApp()) {
    window.toast?.('Select WhatsApp or Both as the contact method', 'tr')
    return
  }
  const payload = resolveSurveyPayload()
  if (!payload.script_text && !payload.whatsapp_flow?.questions?.length && !payload.questions?.length) {
    window.toast?.('Generate your AI survey script first', 'tr')
    return
  }
  state.surveyScriptPayload = payload
  syncWaPreviewHeader()
  document.getElementById('sur-wa-preview-overlay')?.classList.add('show')
  resetSurveyWaPreview()
}

function closeSurveyWaPreview() {
  document.getElementById('sur-wa-preview-overlay')?.classList.remove('show')
}

function selectValue(selectEl) {
  if (!selectEl) return ''
  const opt = selectEl.options?.[selectEl.selectedIndex]
  return (opt?.textContent || opt?.value || '').trim()
}

function setAiStatus(prefix, approved) {
  const badge = document.getElementById(`${prefix}-ai-status`)
  if (!badge) return
  if (approved) {
    badge.textContent = 'Approved'
    badge.className = 'bdg bg'
  } else {
    badge.textContent = 'Draft'
    badge.className = 'bdg ba'
  }
}

function showAiPanel(prefix, show = true) {
  const panel = document.getElementById(`${prefix}-ai-panel`)
  if (panel) panel.style.display = show ? 'block' : 'none'
}

function markScriptDraft(prefix, serviceCode) {
  const text = (document.getElementById(`${prefix}-ai-script`)?.value || '').trim()
  if (serviceCode === 'survey') {
    state.surveyScriptApproved = false
    if (state.surveyScriptPayload) {
      state.surveyScriptPayload = { ...state.surveyScriptPayload, script_text: text }
    }
  } else {
    state.interviewScriptApproved = false
    if (state.interviewScriptPayload) {
      state.interviewScriptPayload = { ...state.interviewScriptPayload, script_text: text }
    }
  }
  setAiStatus(prefix, false)
}

function readApprovedScript(prefix, serviceCode) {
  const text = (document.getElementById(`${prefix}-ai-script`)?.value || '').trim()
  if (!text) return null
  const base = serviceCode === 'survey' ? state.surveyScriptPayload : state.interviewScriptPayload
  return {
    ...(base || {}),
    script_text: text,
    system_prompt: base?.system_prompt || text,
  }
}

async function generateServiceScript(serviceCode) {
  const isSurvey = serviceCode === 'survey'
  const prefix = isSurvey ? 'sur' : 'int'
  const generatingKey = isSurvey ? 'surveyGenerating' : 'interviewGenerating'

  if (state[generatingKey]) return

  const goalEl = document.getElementById('sur-goal')
  const roleEl = document.getElementById('int-role')
  const criteriaEl = document.getElementById('int-criteria')

  if (isSurvey && !(goalEl?.value || '').trim()) {
    window.toast?.('Describe what you want to learn before generating', 'tr')
    goalEl?.focus()
    return
  }
  if (isSurvey) {
    setProfileCache({
      company_name: document.getElementById('prof-company-name')?.value?.trim() || '',
      organiser_name: document.getElementById('prof-organiser-name')?.value?.trim() || '',
    })
    if (!document.getElementById('prof-company-name')?.value?.trim()) {
      window.toast?.('Add your Company name in Profile settings first', 'tr')
      return
    }
    await loadSurveyAgents()
    const agent = selectedSurveyAgent()
    if (!agent) {
      window.toast?.('Select an AI voice agent before generating the script', 'tr')
      document.getElementById('sur-agent-select')?.focus()
      return
    }
  }
  if (!isSurvey && !(roleEl?.value || '').trim()) {
    window.toast?.('Enter the role / position before generating', 'tr')
    roleEl?.focus()
    return
  }
  if (!isSurvey) {
    await loadInterviewAgents()
  }

  const generateBtn = document.getElementById(`${prefix}-ai-generate`)
  const regenBtn = document.getElementById(`${prefix}-ai-regen`)
  state[generatingKey] = true
  if (generateBtn) {
    generateBtn.disabled = true
    generateBtn.innerHTML = '<i class="ti ti-loader"></i>Generating…'
  }
  if (regenBtn) regenBtn.disabled = true
  window.toast?.('AI is writing your script — this may take a few seconds', 'tg')

  const clientCtx = getClientContextForApi()
  
  // For survey scripts, use the selected agent's name from admin profile
  let agentName = ''
  let agentId = ''
  if (isSurvey) {
    const agent = selectedSurveyAgent()
    if (agent) {
      agentId = agent.id
      agentName = agent.name || agent.voice_label || ''
    }
  } else {
    const agent = selectedInterviewAgent()
    if (agent) {
      agentId = agent.id
      agentName = agent.name || agent.voice_label || ''
    }
  }

  const payload = isSurvey
    ? {
        service_code: 'survey',
        goal: goalEl?.value || '',
        contact_method: 'AI phone call',
        max_call_length: selectValue(document.getElementById('sur-max-length')),
        agent_id: agentId,
        client_context: {
          organisation_name: clientCtx.organisation_name,
          assistant_name: agentName || clientCtx.assistant_name,
          terminology_label: clientCtx.terminology_label,
          agent_id: agentId,
          survey_organiser_name: agentName,
          contact_name: agentName,
        },
      }
    : {
        service_code: 'interview',
        role: roleEl?.value || '',
        criteria: criteriaEl?.value || '',
        delivery: deliveryFromInterviewForm(),
        agent_id: agentId,
        client_context: {
          ...clientCtx,
          agent_id: agentId,
          assistant_name: agentName || clientCtx.assistant_name,
        },
      }

  try {
    const res = await api('/dashboard/service-scripts/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    const materialised = materialiseScriptPayload(res, { forPreview: false })
    const scriptBox = document.getElementById(`${prefix}-ai-script`)
    if (scriptBox) scriptBox.value = materialised.script_text || ''
    showAiPanel(prefix, true)
    markScriptDraft(prefix, serviceCode)
    if (isSurvey) {
      state.surveyScriptApproved = false
      state.surveyScriptPayload = materialised
    } else state.interviewScriptPayload = materialised
    syncSurveyWhatsAppUi()
    window.toast?.('Script ready — read it below and click Approve when happy', 'tg')
    scriptBox?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  } catch (e) {
    window.toast?.(e.message || 'Could not generate script — check DeepSeek is configured', 'tr')
  } finally {
    state[generatingKey] = false
    if (generateBtn) {
      generateBtn.disabled = false
      generateBtn.innerHTML = isSurvey
        ? '<i class="ti ti-sparkles"></i>AI write survey script'
        : '<i class="ti ti-sparkles"></i>Generate AI questions'
    }
    if (regenBtn) regenBtn.disabled = false
  }
}

function approveServiceScript(serviceCode) {
  const isSurvey = serviceCode === 'survey'
  const prefix = isSurvey ? 'sur' : 'int'
  const text = (document.getElementById(`${prefix}-ai-script`)?.value || '').trim()
  if (!text) {
    window.toast?.('Generate a script first, or paste your own', 'tr')
    return
  }
  const approved = readApprovedScript(prefix, serviceCode)
  if (isSurvey) {
    state.surveyScriptApproved = true
    state.surveyScriptPayload = approved
  } else {
    state.interviewScriptApproved = true
    state.interviewScriptPayload = approved
  }
  setAiStatus(prefix, true)
  clearSurveyValidationUi()
  notifyUser('Script approved — you can pay and schedule when ready', 'tg')
}

function bindScriptEditors() {
  ;['sur', 'int'].forEach((prefix) => {
    const box = document.getElementById(`${prefix}-ai-script`)
    box?.addEventListener('input', () => {
      const serviceCode = prefix === 'sur' ? 'survey' : 'interview'
      if (serviceCode === 'survey' && state.surveyScriptApproved) markScriptDraft(prefix, serviceCode)
      if (serviceCode === 'interview' && state.interviewScriptApproved) markScriptDraft(prefix, serviceCode)
    })
  })
}

function schedulePayload(prefix) {
  const sd = document.getElementById(`${prefix}-start-date`)
  const st = document.getElementById(`${prefix}-start-time`)
  const ed = document.getElementById(`${prefix}-end-date`)
  const et = document.getElementById(`${prefix}-end-time`)
  if (!sd?.value || !ed?.value) return {}
  const start = `${sd.value}T${st?.value || '09:00'}:00`
  const end = `${ed.value}T${et?.value || '17:00'}:00`
  const now = new Date()
  const startDt = new Date(start)
  const runMode = startDt > now ? 'scheduled' : 'manual'
  return { run_mode: runMode, scheduled_start_at: start, scheduled_end_at: end }
}

function statusBadge(status, paymentStatus) {
  if (paymentStatus === 'pending_approval') return '<span class="stat-wait">Awaiting payment</span>'
  if (status === 'scheduled') return '<span class="stat-wait">Scheduled</span>'
  if (status === 'draft') return '<span class="stat-wait">Draft</span>'
  if (status === 'quoted') return '<span class="stat-wait">Quoted</span>'
  if (status === 'awaiting_payment') return '<span class="stat-wait">Awaiting payment</span>'
  if (status === 'running') return '<span class="stat-live"><span style="width:6px;height:6px;border-radius:50%;background:var(--grn);display:inline-block;animation:lpulse 1.2s infinite"></span>Live</span>'
  if (status === 'paid') return '<span class="stat-wait">Paid — ready</span>'
  if (status === 'completed') return '<span class="stat-done">Completed</span>'
  return `<span class="stat-wait">${status}</span>`
}

function renderOrderRow(order) {
  const icon = order.service_code === 'interview' ? 'ti-briefcase' : 'ti-clipboard-list'
  const dispatch =
    order.report && order.status === 'running'
      ? ` · ${surveyRespondedCount(order.report)} sent${order.report.failed ? `, ${order.report.failed} failed` : ''}${order.report.skipped ? `, ${order.report.skipped} skipped` : ''}`
      : ''
  const meta = `${order.recipient_count} contacts · ${order.quote_total_gbp}${order.payment_status === 'pending_approval' ? ' · payment pending' : ''}${dispatch}`
  const clickHandler =
    order.service_code === 'interview'
      ? `window.openInterviewResults('${order.id}')`
      : `window.openSurveyResults('${order.id}')`
  return `<div class="proj-row" onclick="${clickHandler}">
    <div class="proj-ic ci-b"><i class="ti ${icon}"></i></div>
    <div class="proj-info">
      <div class="proj-name">${order.title}</div>
      <div class="proj-meta">${meta}</div>
    </div>
    ${statusBadge(order.status, order.payment_status)}
  </div>`
}

async function loadOrdersIntoUi() {
  if (!getAccessToken()) return
  try {
    if (typeof window.reloadSurveyHub === 'function') {
      await window.reloadSurveyHub()
    }
    const [interviews, credits] = await Promise.all([
      api('/service-orders?service_code=interview'),
      api('/service-orders/credits').catch(() => ({})),
    ])
    renderInterviewKpis(interviews, credits)
    const intHost = document.getElementById('int-live-orders')
    if (intHost) {
      const intRows = (interviews || []).slice(0, 8).map(renderOrderRow).join('')
      intHost.innerHTML = intRows
      const intEmpty = document.getElementById('int-projects-empty')
      if (intEmpty) intEmpty.style.display = intRows ? 'none' : ''
    }
    state.ordersLoaded = true
  } catch {
    /* keep static preview */
  }
}

async function payExistingSurveyOrder(order) {
  await offerSurveyPayment(order)
}

async function duplicateSurveyOrder(orderId) {
  if (!orderId) return
  try {
    const order = await api(`/service-orders/${encodeURIComponent(orderId)}`)
    const goalEl = document.getElementById('sur-goal')
    if (goalEl) goalEl.value = order.config?.goal || order.title || ''
    if (order.config?.approved_script) {
      state.surveyScriptPayload = {
        script_text: order.config.approved_script,
        questions: order.config.script_questions || [],
        system_prompt: order.config.system_prompt || '',
      }
      state.surveyScriptApproved = Boolean(order.config.script_approved)
      const scriptEl = document.getElementById('sur-ai-script')
      if (scriptEl) scriptEl.value = order.config.approved_script
      showAiPanel('sur', true)
      setAiStatus('sur', state.surveyScriptApproved)
    }
    window.toast?.('Survey copied into new campaign form — upload contacts and pay to launch.', 'tg')
  } catch (e) {
    window.toast?.(e.message || 'Could not duplicate survey', 'tr')
  }
}

function bindUploads() {
  const intInput = document.getElementById('int-file-input')
  const intTpl = document.getElementById('int-template-dl')

  if (intTpl) {
    intTpl.addEventListener('click', async (e) => {
      e.preventDefault()
      e.stopPropagation()
      try {
        await downloadAuthenticatedFile('/service-orders/template.csv', 'voxbulk-contacts-template.csv')
      } catch (err) {
        window.toast?.(err.message || 'Could not download template', 'tr')
      }
    })
  }
  if (intInput) {
    intInput.addEventListener('change', async () => {
      await onInterviewFileSelected(intInput.files)
      intInput.value = ''
    })
  }
}

async function parseFirstNameFromRecipientFile(file) {
  if (!file) return ''
  const lower = file.name.toLowerCase()
  if (!lower.endsWith('.csv')) return ''
  try {
    const chunk = await file.slice(0, 8192).text()
    const lines = chunk.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
    if (lines.length < 2) return ''
    const splitRow = (line) => line.split(',').map((c) => c.trim().replace(/^"|"$/g, ''))
    const headers = splitRow(lines[0]).map((h) => h.toLowerCase())
    const row = splitRow(lines[1])
    const nameIdx = headers.findIndex((h) => /^(name|first_name|firstname|full name|contact name|contact)$/.test(h))
    const raw = nameIdx >= 0 ? row[nameIdx] : row[0]
    return String(raw || '').trim().split(/\s+/)[0] || ''
  } catch {
    return ''
  }
}

async function loadPaymentOptions() {
  try {
    state.paymentOptions = await api('/billing/payment-options')
  } catch {
    state.paymentOptions = { cash_available: true, gocardless_available: false }
  }
}

function orderBillingQueryParam(name) {
  try {
    return new URLSearchParams(window.location.search).get(name)
  } catch {
    return null
  }
}

function clearOrderBillingQuery() {
  try {
    const url = new URL(window.location.href)
    url.searchParams.delete('order_billing')
    window.history.replaceState({}, '', url.pathname + url.search + url.hash)
  } catch {
    /* ignore */
  }
}

async function completeGocardlessOrderReturn() {
  const billing = orderBillingQueryParam('order_billing')
  if (billing === 'cancelled') {
    sessionStorage.removeItem(GC_ORDER_FLOW_KEY)
    clearOrderBillingQuery()
    window.toast?.('GoCardless payment cancelled.', 'tw')
    return
  }
  if (billing !== 'success') return

  const redirectFlowId = sessionStorage.getItem(GC_ORDER_FLOW_KEY)
  sessionStorage.removeItem(GC_ORDER_FLOW_KEY)
  clearOrderBillingQuery()
  if (!redirectFlowId) {
    window.toast?.('Payment completed — refresh if your order did not update.', 'tw')
    return
  }

  try {
    const result = await api('/service-orders/gocardless/complete', {
      method: 'POST',
      body: JSON.stringify({ redirect_flow_id: redirectFlowId }),
    })
    const order = result?.order
    if (order?.payment_status === 'approved') {
      if (order.service_code === 'survey') {
        const scheduled = await schedulePaidSurveyOrder(order)
        window.toast?.(
          scheduled.status === 'scheduled'
            ? 'GoCardless payment approved — survey scheduled'
            : 'GoCardless payment approved — survey ready',
          'tg',
        )
        resetSurveyLaunchForm()
      } else {
        await api(`/service-orders/${order.id}/start`, { method: 'POST' })
        window.toast?.('GoCardless payment approved — campaign started', 'tg')
      }
    } else {
      window.toast?.('GoCardless payment completed', 'tg')
    }
    await loadOrdersIntoUi()
  } catch (e) {
    window.toast?.(e.message || 'Could not complete GoCardless payment', 'tr')
  }
}

async function startGocardlessOrderPayment(orderId) {
  const result = await api(`/service-orders/${orderId}/gocardless/start`, { method: 'POST' })
  const redirectFlowId = result?.redirect_flow_id
  const authorizationUrl = result?.authorization_url
  if (!redirectFlowId || !authorizationUrl) {
    throw new Error('GoCardless did not return a checkout URL')
  }
  sessionStorage.setItem(GC_ORDER_FLOW_KEY, redirectFlowId)
  window.location.assign(authorizationUrl)
}

async function submitPromoCreditPayment(orderId) {
  try {
    const paid = await api(`/service-orders/${orderId}/pay-promo-credits`, { method: 'POST' })
    await api(`/service-orders/${paid.id}/start`, { method: 'POST' })
    window.toast?.('Paid with promo credits — campaign started', 'tg')
    await loadOrdersIntoUi()
  } catch (e) {
    window.toast?.(e.message || 'Could not use promo credits', 'tr')
  }
}

async function offerOrderPayment(order, quoteText) {
  let promoAvailable = false
  let promoCredits = 0
  try {
    const credits = await api('/service-orders/credits')
    promoCredits =
      order.service_code === 'survey'
        ? Number(credits?.survey_credits || 0)
        : Number(credits?.interview_credits || 0)
    promoAvailable = promoCredits >= Number(order.recipient_count || 0) && order.recipient_count > 0
  } catch {
    // fall through to normal payment options
  }

  const gc = Boolean(state.paymentOptions?.gocardless_available)
  const cash = state.paymentOptions?.cash_available !== false
  const breakdown = String(quoteText || '')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)

  const choice = await showSurveyPaymentModal({
    title: order.service_code === 'survey' ? 'Pay for survey' : 'Pay for campaign',
    amountLabel: order.quote_total_gbp || fmtGbp(order.quote_total_pence),
    breakdown,
    note: cash ? 'Cash payments need admin approval.' : '',
    gocardlessAvailable: gc,
    cashAvailable: cash,
    promoAvailable,
    promoLabel: promoAvailable ? `Use ${promoCredits} promo credits` : '',
  })

  if (choice === 'promo' && promoAvailable) {
    await submitPromoCreditPayment(order.id)
    return
  }
  if (choice === 'gocardless' && gc) {
    await startGocardlessOrderPayment(order.id)
    return
  }
  if (choice === 'cash' && cash) {
    await submitCashOrderPayment(order.id)
  }
}

async function submitCashOrderPayment(orderId) {
  try {
    const paid = await api(`/service-orders/${orderId}/pay-cash`, {
      method: 'POST',
      body: JSON.stringify({ note: 'Cash payment submitted from dashboard' }),
    })
    window.toast?.('Payment submitted — waiting for admin approval', 'tg')
    if (paid.payment_status === 'approved') {
      await api(`/service-orders/${paid.id}/start`, { method: 'POST' })
      window.toast?.('Campaign started', 'tg')
    }
    await loadOrdersIntoUi()
  } catch (e) {
    window.toast?.(e.message || 'Payment submit failed', 'tr')
  }
}

async function uploadRecipients(orderId, file) {
  return apiUploadFile(`/service-orders/${orderId}/recipients/upload`, file, 'file')
}

async function tryStartPaidOrder(serviceCode) {
  if (serviceCode === 'survey') return false
  try {
    const orders = await api(`/service-orders?service_code=${encodeURIComponent(serviceCode)}`)
    const paid = (orders || []).find(
      (o) => o.payment_status === 'approved' && (o.status === 'paid' || o.status === 'scheduled'),
    )
    if (!paid) return false
    await api(`/service-orders/${paid.id}/start`, { method: 'POST' })
    window.toast?.('Campaign started — AI phone interviews will run in your calling window', 'tg')
    await loadOrdersIntoUi()
    return true
  } catch {
    return false
  }
}

async function runOrderFlow(serviceCode) {
  if (serviceCode === 'survey') {
    await runSurveyLaunchFlow()
    return
  }

  const isSurvey = false
  if (await tryStartPaidOrder(serviceCode)) return
  const prefix = isSurvey ? 'sur' : 'int'
  const hasDraftList = (interviewLaunch.recipients || []).length > 0
  const file = isSurvey ? state.surveyFile : state.interviewFile
  if (!isSurvey && !hasDraftList && !file) {
    window.toast?.('Upload a candidate list or CV files first', 'tr')
    return
  }
  if (!isSurvey && hasDraftList) {
    const ready = interviewIntakeReadyCount()
    const total = interviewLaunch.recipients.length
    if (ready === 0) {
      window.toast?.('Add phone numbers for at least one candidate before launching', 'tr')
      return
    }
    if (ready < total) {
      window.toast?.(`${total - ready} candidate(s) still missing phone — add or delete them first`, 'tr')
      return
    }
  } else if (!isSurvey && !file) {
    window.toast?.('Upload a CSV or Excel contact list first', 'tr')
    return
  }

  const sched = schedulePayload(prefix)
  if (!sched.scheduled_start_at) {
    window.toast?.('Please set a start and end date first', 'tr')
    return
  }

  const title = isSurvey
    ? (document.getElementById('sur-goal')?.value || 'Survey campaign').trim().slice(0, 120)
    : (document.getElementById('int-role')?.value || 'Interview campaign').trim().slice(0, 120)

  const branding = getClientContextForApi()
  const config = isSurvey
    ? {
        goal: document.getElementById('sur-goal')?.value || '',
        channels: surveyChannels(),
        contact_method: selectValue(document.getElementById('sur-contact-method')),
        script_mode: scriptModeFromButtons('survey'),
        approved_script: state.surveyScriptPayload?.script_text || '',
        script_questions: state.surveyScriptPayload?.questions || [],
        system_prompt: state.surveyScriptPayload?.system_prompt || '',
        whatsapp_flow: state.surveyScriptPayload?.whatsapp_flow || null,
        script_approved: state.surveyScriptApproved,
        organisation_name: branding.organisation_name,
        survey_organiser_name: branding.survey_organiser_name,
        clinic_name: branding.organisation_name,
      }
    : {
        role: document.getElementById('int-role')?.value || '',
        delivery: deliveryFromInterviewForm(),
        criteria: document.getElementById('int-criteria')?.value || '',
        script_mode: scriptModeFromButtons('interview'),
        approved_script: state.interviewScriptPayload?.script_text || '',
        script_questions: state.interviewScriptPayload?.questions || [],
        system_prompt: state.interviewScriptPayload?.system_prompt || '',
        script_approved: state.interviewScriptApproved,
      }

  const scriptOk = isSurvey ? state.surveyScriptApproved : state.interviewScriptApproved
  if (!scriptOk) {
    window.toast?.('Generate your AI script, read it, then click Approve before launching', 'tr')
    showAiPanel(prefix, true)
    document.getElementById(`${prefix}-ai-script`)?.focus()
    return
  }

  try {
    let order
    if (!isSurvey && interviewLaunch.draftOrderId) {
      order = await api(`/service-orders/${interviewLaunch.draftOrderId}`, {
        method: 'PATCH',
        body: JSON.stringify({ title, config, ...sched }),
      })
      order = await api(`/service-orders/${order.id}/quote`, { method: 'POST' })
    } else {
      order = await api('/service-orders', {
        method: 'POST',
        body: JSON.stringify({ service_code: serviceCode, title, config }),
      })
      order = await uploadRecipients(order.id, file)
      await api(`/service-orders/${order.id}`, {
        method: 'PATCH',
        body: JSON.stringify(sched),
      })
      order = await api(`/service-orders/${order.id}/quote`, { method: 'POST' })
    }

    const quoteText = (order.quote_breakdown || [])
      .map((l) => l.detail || l.label)
      .join('\n')

    await offerOrderPayment(order, quoteText)
  } catch (e) {
    window.toast?.(e.message || 'Could not create order', 'tr')
  }
}

function wireHelpChat() {
  if (typeof window.sendMsg !== 'function') return
  const original = window.sendMsg
  window.sendMsg = async function patchedSendMsg() {
    const inp = document.getElementById('cw-input')
    const txt = (inp?.value || '').trim()
    if (!txt) return
    document.getElementById('quick-replies')?.style && (document.getElementById('quick-replies').style.display = 'none')
    window.appendMsg?.(txt, 'user', 'Just now')
    inp.value = ''
    window.showTyping?.()
    try {
      const res = await api('/dashboard/help/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: txt,
          history: (window.chatHistory || []).slice(-8),
        }),
      })
      window.removeTyping?.()
      window.appendMsg?.(res.reply || 'How can I help with VOXBULK?', 'support', 'Just now')
    } catch {
      window.removeTyping?.()
      original.call(window)
    }
  }
}

function wireAiButtons() {
  document.getElementById('int-ai-generate')?.addEventListener('click', () => generateServiceScript('interview'))
  document.getElementById('int-ai-regen')?.addEventListener('click', () => generateServiceScript('interview'))
  document.getElementById('int-ai-approve')?.addEventListener('click', () => approveServiceScript('interview'))
}

export function initServiceOrdersBridge() {
  window.payAndScheduleSurvey = (event) => {
    event?.preventDefault?.()
    void runSurveyLaunchFlow()
  }
  window.launchSurCampaign = () => runSurveyLaunchFlow()
  window.openInterviewResults = openInterviewResults
  window.launchIntCampaign = async () => {
    await runOrderFlow('interview')
    const banner = document.getElementById('int-live-banner')
    if (banner) banner.style.display = 'none'
  }
  window.openSurveyWaPreview = openSurveyWaPreview
  window.closeSurveyWaPreview = closeSurveyWaPreview
  window.resetSurveyWaPreview = resetSurveyWaPreview
  window.payExistingSurveyOrder = payExistingSurveyOrder
  window.duplicateSurveyOrder = duplicateSurveyOrder
  document.getElementById('sur-wa-preview-overlay')?.addEventListener('click', (e) => {
    if (e.target?.id === 'sur-wa-preview-overlay') closeSurveyWaPreview()
  })
  bindUploads()
  bindScriptEditors()
  bindSurveyLaunchUi()
  bindInterviewLaunchUi()
  wireHelpChat()
  wireAiButtons()
  syncWaPreviewHeader()
  loadPaymentOptions()
  completeGocardlessOrderReturn()
  loadOrdersIntoUi()
  void loadSurveyLaunchPackages().catch(() => {})
  void loadSurveyAgents().catch(() => {})
  void loadInterviewAgents().catch(() => {})
  renderSurveyQuoteUi()
  renderInterviewQuoteUi()
}

if (typeof window !== 'undefined') {
  window.payAndScheduleSurvey = (event) => {
    event?.preventDefault?.()
    void runSurveyLaunchFlow()
  }
}
