import { confirmDialog, showLaunchSummaryModal, showSurveyPaymentModal } from './modalBridge.js'
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
  preparedOrder: null,
  preparedQuoteText: '',
  saving: false,
  cvClosedEarly: false,
}

const INTERVIEW_DRAFT_LS_KEY = 'voxbulk_interview_draft_id'

const interviewResultsUi = {
  rows: [],
  sortKey: 'score',
  sortAsc: false,
  selected: new Set(),
  menuDocBound: false,
  toolbarBound: false,
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
  const phase = getInterviewCvCollectionPhase()
  if (phase.blocksLaunch) {
    interviewLaunch.quote = null
    interviewLaunch.quoteError = ''
    interviewLaunch.quoteStatusNote = phase.state === 'open'
      ? `Pricing available after CV email collection ends (${phase.endLabel})`
      : 'Pricing available after Step 1 email collection finishes'
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
    void saveInterviewDraft({ silent: true })
  } catch (e) {
    if (statusEl) statusEl.textContent = e.message || 'Upload failed'
    window.toast?.(e.message || 'Could not process upload', 'tr')
  } finally {
    interviewLaunch.intakeLoading = false
  }
}

function renderInterviewKpis(orders, credits, reportOverview) {
  const creditsEl = document.getElementById('int-kpi-credits')
  const creditsSub = document.getElementById('int-kpi-credits-sub')
  const completedEl = document.getElementById('int-kpi-completed')
  const completedSub = document.getElementById('int-kpi-completed-sub')
  const balance = Number(credits?.interview_credits || 0)
  if (creditsEl) creditsEl.textContent = String(balance)
  if (creditsSub) creditsSub.textContent = balance === 1 ? 'promo credit' : 'promo credits'

  if (reportOverview) {
    const batches = Number(reportOverview.batch_count || 0)
    const candidates = Number(reportOverview.candidate_count || 0)
    const reached = Number(reportOverview.reached || 0)
    const pct = candidates > 0 ? Number(reportOverview.reach_rate_pct || 0) : 0
    if (completedEl) completedEl.textContent = String(batches)
    if (completedSub) {
      completedSub.textContent =
        batches && candidates
          ? `${reached} of ${candidates} reached (${pct}%)`
          : batches
            ? `${candidates} candidates`
            : 'No completed campaigns this month'
    }
    return
  }

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
  interviewResultsUi.orderId = orderId
  if (typeof window.goNav === 'function') window.goNav('results-i')

  const bc = document.getElementById('int-results-bc-title')
  const banner = document.getElementById('int-results-phase-banner')
  const bannerText = document.getElementById('int-results-phase-banner-text')
  const mockNote = document.getElementById('int-results-mock-note')

  try {
    const [order, results] = await Promise.all([
      api(`/service-orders/${encodeURIComponent(orderId)}`),
      api(`/service-orders/${encodeURIComponent(orderId)}/interview-results`),
    ])
    const title = order.title || results.title || 'Interview campaign'
    if (bc) bc.textContent = title
    if (banner) banner.style.display = 'flex'
    if (bannerText) {
      bannerText.textContent = results.scheduling_mock
        ? `${title} — connect Calendly in System settings, select top candidates, then Send scheduling links.`
        : results.is_mock
          ? `${title} — calls in progress; scores update when interviews complete.`
          : `${title} — live interview results.`
    }
    if (mockNote) mockNote.style.display = results.is_mock ? '' : 'none'
    renderInterviewResultsPage(results)
  } catch {
    if (bc) bc.textContent = 'Interview campaign'
    if (banner) banner.style.display = 'flex'
    if (mockNote) mockNote.style.display = ''
  }
}

function recommendationBadge(rec) {
  const r = String(rec || 'Hold')
  if (r === 'Advance') return '<span class="bdg bg">Advance</span>'
  if (r === 'Decline') return '<span class="bdg br">Decline</span>'
  return '<span class="bdg ba">Hold</span>'
}

function sentimentBadge(sent) {
  const s = String(sent || 'Neutral')
  if (/enthus/i.test(s)) return '<span class="bdg bp">Enthusiastic</span>'
  if (/hesit/i.test(s)) return '<span class="bdg br">Hesitant</span>'
  return '<span class="bdg bb">Neutral</span>'
}

function scoreStars(score) {
  const n = Math.max(0, Math.min(5, Math.round(Number(score || 0) / 20)))
  return `<div class="stars">${[1, 2, 3, 4, 5]
    .map((i) => `<i class="ti ti-star star${i <= n ? '' : ' e'}"></i>`)
    .join('')}</div>`
}

function sortInterviewCandidates(rows, key, asc) {
  const recRank = { Advance: 3, Hold: 2, Decline: 1 }
  const sentRank = { Enthusiastic: 3, Neutral: 2, Hesitant: 1 }
  return [...rows].sort((a, b) => {
    let av
    let bv
    switch (key) {
      case 'name':
        av = a.name || ''
        bv = b.name || ''
        break
      case 'duration':
        av = Number(a.duration_seconds || 0)
        bv = Number(b.duration_seconds || 0)
        break
      case 'recommendation':
        av = recRank[a.recommendation] || 0
        bv = recRank[b.recommendation] || 0
        break
      case 'sentiment':
        av = sentRank[a.sentiment] || 0
        bv = sentRank[b.sentiment] || 0
        break
      case 'score':
      default:
        av = Number(a.score || 0)
        bv = Number(b.score || 0)
    }
    if (typeof av === 'string') {
      const cmp = av.localeCompare(bv)
      return asc ? cmp : -cmp
    }
    return asc ? av - bv : bv - av
  })
}

function sortIndicator(key) {
  if (interviewResultsUi.sortKey !== key) return ''
  return `<span class="sort-ind">${interviewResultsUi.sortAsc ? '↑' : '↓'}</span>`
}

function candidateInitials(name) {
  return (name || '?')
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0])
    .join('')
    .toUpperCase()
}

function closeAllInterviewRowMenus() {
  document.querySelectorAll('.int-row-menu.open').forEach((el) => el.classList.remove('open'))
}

function bindInterviewResultsMenuDismiss() {
  if (interviewResultsUi.menuDocBound) return
  interviewResultsUi.menuDocBound = true
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.int-res-actions')) closeAllInterviewRowMenus()
  })
}

function updateInterviewResultsBulkUi() {
  const bulkBtn = document.getElementById('int-res-bulk-send')
  const selectAll = document.getElementById('int-res-select-all')
  const count = interviewResultsUi.selected.size
  if (bulkBtn) bulkBtn.disabled = count === 0
  if (selectAll) {
    const total = interviewResultsUi.rows.length
    selectAll.checked = total > 0 && count === total
    selectAll.indeterminate = count > 0 && count < total
  }
}

function renderInterviewResultsTableBody() {
  const tableHost = document.getElementById('int-results-table-host')
  if (!tableHost) return
  const sorted = sortInterviewCandidates(interviewResultsUi.rows, interviewResultsUi.sortKey, interviewResultsUi.sortAsc)
  if (!sorted.length) {
    tableHost.innerHTML = '<div class="muted" style="font-size:12px;padding:12px 4px">No candidates yet.</div>'
    return
  }

  tableHost.innerHTML = `<table class="res-table int-res-table">
    <thead><tr>
      <th class="int-res-check" aria-label="Select"></th>
      <th class="int-res-sort" data-sort="name">Candidate${sortIndicator('name')}</th>
      <th class="int-res-sort" data-sort="duration">Duration${sortIndicator('duration')}</th>
      <th>Task</th>
      <th class="int-res-sort" data-sort="score">Score${sortIndicator('score')}</th>
      <th class="int-res-sort" data-sort="recommendation">Recommendation${sortIndicator('recommendation')}</th>
      <th class="int-res-sort" data-sort="sentiment">Sentiment${sortIndicator('sentiment')}</th>
      <th></th>
      <th class="int-res-actions" aria-label="Actions"></th>
    </tr></thead>
    <tbody>${sorted
      .map((c) => {
        const id = String(c.id || '')
        const checked = interviewResultsUi.selected.has(id)
        const wa = c.whatsapp_mock || ''
        const email = c.email_mailto || (c.email ? `mailto:${encodeURIComponent(c.email)}` : '')
        const cal = c.scheduling_url_mock || ''
        const waDisabled = wa ? '' : ' disabled'
        const emailDisabled = email ? '' : ' disabled'
        const calDisabled = cal ? '' : ' disabled'
        return `<tr data-int-res-row="${escHtml(id)}" class="${checked ? 'int-res-row-selected' : ''}">
          <td class="int-res-check"><input type="checkbox" class="int-res-pick" data-id="${escHtml(id)}"${checked ? ' checked' : ''} aria-label="Select ${escHtml(c.name || 'candidate')}"/></td>
          <td><div style="display:flex;align-items:center;gap:9px"><div class="av av-g" style="width:28px;height:28px;font-size:10px">${escHtml(candidateInitials(c.name))}</div>${escHtml(c.name || '—')}</div></td>
          <td><i class="ti ti-clock" style="color:var(--t3);font-size:12px"></i> ${escHtml(c.duration_label || '—')}</td>
          <td>${escHtml(c.task || 'Interview screening')}</td>
          <td>${scoreStars(c.score)}</td>
          <td>${recommendationBadge(c.recommendation)}</td>
          <td>${sentimentBadge(c.sentiment)}</td>
          <td><button class="btn bsm bxsm int-res-play" type="button"><i class="ti ti-player-play"></i>Play</button></td>
          <td class="int-res-actions">
            <button type="button" class="int-row-menu-btn" data-menu-toggle="${escHtml(id)}" aria-label="Scheduling links"><i class="ti ti-dots-vertical"></i></button>
            <div class="int-row-menu" data-menu="${escHtml(id)}">
              <a class="wa${waDisabled}" href="${escHtml(wa || '#')}" target="_blank" rel="noopener" title="WhatsApp"${wa ? '' : ' tabindex="-1"'}><i class="ti ti-brand-whatsapp"></i></a>
              <a class="int-menu-link${emailDisabled}" href="${escHtml(email || '#')}" title="Email"${email ? '' : ' tabindex="-1"'}><i class="ti ti-mail"></i></a>
              <a class="int-menu-link${calDisabled}" href="${escHtml(cal || '#')}" target="_blank" rel="noopener" title="Scheduling link"${cal ? '' : ' tabindex="-1"'}><i class="ti ti-calendar"></i></a>
            </div>
          </td>
        </tr>`
      })
      .join('')}</tbody></table>`

  tableHost.querySelectorAll('.int-res-sort').forEach((th) => {
    th.addEventListener('click', () => {
      const key = th.getAttribute('data-sort')
      if (!key) return
      if (interviewResultsUi.sortKey === key) interviewResultsUi.sortAsc = !interviewResultsUi.sortAsc
      else {
        interviewResultsUi.sortKey = key
        interviewResultsUi.sortAsc = key === 'name'
      }
      renderInterviewResultsTableBody()
    })
  })

  tableHost.querySelectorAll('.int-res-pick').forEach((box) => {
    box.addEventListener('click', (e) => e.stopPropagation())
    box.addEventListener('change', (e) => {
      const id = e.target.getAttribute('data-id')
      if (!id) return
      if (e.target.checked) interviewResultsUi.selected.add(id)
      else interviewResultsUi.selected.delete(id)
      e.target.closest('tr')?.classList.toggle('int-res-row-selected', e.target.checked)
      updateInterviewResultsBulkUi()
    })
  })

  tableHost.querySelectorAll('[data-menu-toggle]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      const id = btn.getAttribute('data-menu-toggle')
      const menu = tableHost.querySelector(`[data-menu="${CSS.escape(id)}"]`)
      const wasOpen = menu?.classList.contains('open')
      closeAllInterviewRowMenus()
      if (menu && !wasOpen) menu.classList.add('open')
    })
  })

  tableHost.querySelectorAll('.int-row-menu a').forEach((link) => {
    link.addEventListener('click', (e) => e.stopPropagation())
  })

  tableHost.querySelectorAll('[data-int-res-row]').forEach((row) => {
    const id = row.getAttribute('data-int-res-row')
    const c = interviewResultsUi.rows.find((r) => String(r.id) === String(id))
    if (!c) return
    row.addEventListener('click', (e) => {
      if (e.target.closest('.int-res-check, .int-res-actions, .int-res-play, .int-row-menu')) return
      if (typeof window.showRec === 'function') {
        window.showRec(c.name || '', c.duration_label || '', c.task || '', c.sentiment || '')
      }
    })
    row.querySelector('.int-res-play')?.addEventListener('click', (e) => {
      e.stopPropagation()
      if (typeof window.showRec === 'function') {
        window.showRec(c.name || '', c.duration_label || '', c.task || '', c.sentiment || '')
      }
    })
  })
}

async function persistInterviewShortlist(orderId) {
  const ids = [...interviewResultsUi.selected]
  if (!orderId || !ids.length) return
  try {
    await api(`/service-orders/${encodeURIComponent(orderId)}/interview-shortlist`, {
      method: 'PATCH',
      body: JSON.stringify({ recipient_ids: ids }),
    })
  } catch (e) {
    console.warn('[interview] shortlist save failed', e)
  }
}

async function sendBulkInterviewScheduling() {
  const orderId = interviewResultsUi.orderId
  const selected = interviewResultsUi.rows.filter((r) => interviewResultsUi.selected.has(String(r.id)))
  if (!selected.length) {
    window.toast?.('Select at least one candidate', 'tr')
    return
  }
  const ok = await confirmDialog({
    title: 'Send scheduling links',
    message: `Send Calendly scheduling links by email to ${selected.length} selected candidate(s)?`,
    okLabel: 'Send',
    cancelLabel: 'Cancel',
  })
  if (!ok) return

  try {
    await persistInterviewShortlist(orderId)
    const res = await api(`/service-orders/${encodeURIComponent(orderId)}/interview-scheduling/send`, {
      method: 'POST',
      body: JSON.stringify({ recipient_ids: selected.map((c) => c.id) }),
    })
    const sent = res?.sent ?? 0
    const errs = (res?.errors || []).length
    window.toast?.(`Scheduling sent to ${sent} candidate(s)${errs ? ` · ${errs} issue(s)` : ''}`, sent ? 'tg' : 'tr')
    if (orderId) await openInterviewResults(orderId)
  } catch (e) {
    window.toast?.(e?.message || 'Could not send scheduling links — connect Calendly in System settings', 'tr')
  }
  closeAllInterviewRowMenus()
}

function wireInterviewResultsToolbar() {
  bindInterviewResultsMenuDismiss()
  const toolbar = document.getElementById('int-res-toolbar')
  if (toolbar) toolbar.hidden = interviewResultsUi.rows.length === 0

  if (!interviewResultsUi.toolbarBound) {
    interviewResultsUi.toolbarBound = true
    document.getElementById('int-res-select-all')?.addEventListener('change', (e) => {
      interviewResultsUi.selected.clear()
      if (e.target.checked) {
        interviewResultsUi.rows.forEach((r) => interviewResultsUi.selected.add(String(r.id)))
      }
      renderInterviewResultsTableBody()
      updateInterviewResultsBulkUi()
    })
    document.getElementById('int-res-bulk-send')?.addEventListener('click', () => void sendBulkInterviewScheduling())
  }
}

function renderInterviewResultsPage(results) {
  const kpis = results?.kpis || {}
  document.getElementById('int-res-kpi-called') && (document.getElementById('int-res-kpi-called').textContent = String(kpis.called ?? '—'))
  document.getElementById('int-res-kpi-reached') && (document.getElementById('int-res-kpi-reached').textContent = String(kpis.reached ?? '—'))
  const reachPct = document.getElementById('int-res-kpi-reach-pct')
  if (reachPct) reachPct.textContent = kpis.reach_rate_pct != null ? `${kpis.reach_rate_pct}%` : ''
  document.getElementById('int-res-kpi-advance') && (document.getElementById('int-res-kpi-advance').textContent = String(kpis.recommended_advance ?? '—'))
  document.getElementById('int-res-kpi-duration') && (document.getElementById('int-res-kpi-duration').textContent = kpis.avg_duration_label || '—')

  const staticTable = document.getElementById('int-results-table-static')
  interviewResultsUi.rows = results?.candidates || []
  interviewResultsUi.selected.clear()
  const saved = results?.top_10_recipient_ids || []
  saved.forEach((id) => interviewResultsUi.selected.add(String(id)))
  interviewResultsUi.rows.forEach((r) => {
    if (r.shortlist_selected) interviewResultsUi.selected.add(String(r.id))
  })
  if (staticTable) staticTable.style.display = interviewResultsUi.rows.length ? 'none' : ''

  wireInterviewResultsToolbar()
  renderInterviewResultsTableBody()
  updateInterviewResultsBulkUi()
}

function cvQualityBadge(quality) {
  const q = String(quality || 'missing')
  if (q === 'good') return '<span class="bdg bg">CV good</span>'
  if (q === 'low_quality') return '<span class="bdg ba">CV low</span>'
  if (q === 'corrupt') return '<span class="bdg br">CV error</span>'
  return '<span class="bdg bb">No CV</span>'
}

function updateInterviewReferenceCard(order) {
  const wrap = document.getElementById('int-ref-card-wrap')
  const codeEl = document.getElementById('int-ref-id')
  const ref = String(order?.reference_id || '').trim()
  const hasDraft = Boolean(order?.id || interviewLaunch.draftOrderId)
  if (!wrap || !codeEl) return
  if (!hasDraft) {
    wrap.hidden = true
    return
  }
  codeEl.textContent = ref || 'Save draft to generate…'
  wrap.hidden = false
  if (typeof window.updateIntCvEmailWindow === 'function') window.updateIntCvEmailWindow()
}

function bindInterviewReferenceCopy() {
  document.getElementById('int-ref-copy')?.addEventListener('click', async () => {
    const ref = document.getElementById('int-ref-id')?.textContent?.trim()
    if (!ref || ref.includes('…')) return
    try {
      await navigator.clipboard.writeText(ref)
      window.toast?.('Reference copied', 'tg')
    } catch {
      window.toast?.('Could not copy — select the code and copy manually', 'tr')
    }
  })
}

async function downloadInterviewRecipientCv(recipientId) {
  const orderId = interviewLaunch.draftOrderId || state.interviewOrderId
  if (!orderId || !recipientId) return
  const recipient = (interviewLaunch.recipients || []).find((r) => r.id === recipientId)
  const filename = recipient?.cv_filename || `cv-${recipientId}.txt`
  try {
    await downloadAuthenticatedFile(
      `/service-orders/${encodeURIComponent(orderId)}/recipients/${encodeURIComponent(recipientId)}/cv`,
      filename,
    )
  } catch (e) {
    window.toast?.(e.message || 'Could not download CV', 'tr')
  }
}

function resetInterviewFormForNewTask() {
  clearInterviewFormFields()
  interviewLaunch.draftOrderId = null
  updateInterviewFormChrome(null)
}

function clearInterviewFormFields() {
  ;['int-role', 'int-criteria', 'int-ai-script'].forEach((id) => {
    const el = document.getElementById(id)
    if (el) el.value = ''
  })
  ;['int-start-date', 'int-start-time', 'int-end-date', 'int-end-time'].forEach((id) => {
    const el = document.getElementById(id)
    if (el) el.value = ''
  })
  state.interviewFile = null
  state.interviewOrderId = null
  state.interviewScriptPayload = null
  state.interviewScriptApproved = false
  interviewLaunch.recipients = []
  interviewLaunch.intakeSummary = null
  interviewLaunch.quote = null
  interviewLaunch.quoteError = ''
  interviewLaunch.preparedOrder = null
  interviewLaunch.preparedQuoteText = ''
  interviewLaunch.contactCount = 0
  interviewLaunch.contactCountKnown = false
  const panel = document.getElementById('int-candidate-panel')
  if (panel) panel.hidden = true
  const uploadStatus = document.getElementById('int-upload-status')
  if (uploadStatus) {
    uploadStatus.style.display = 'none'
    uploadStatus.textContent = ''
  }
  const saveStatus = document.getElementById('int-save-status')
  if (saveStatus) {
    saveStatus.style.display = 'none'
    saveStatus.textContent = ''
  }
  showAiPanel('int', false)
  setAiStatus('int', false)
  renderInterviewQuoteUi()
  if (typeof window.updateIntWindow === 'function') window.updateIntWindow()
  setInterviewFormLocked(false)
  setCvEmailEnabled(false)
  ;['int-cv-start-date', 'int-cv-start-time', 'int-cv-end-date', 'int-cv-end-time'].forEach((id) => {
    const el = document.getElementById(id)
    if (el) el.value = id.includes('time') ? (id.includes('start') ? '09:00' : '17:00') : ''
  })
}

function updateInterviewFormChrome(order) {
  const titleEl = document.getElementById('int-form-title')
  const deleteBtn = document.getElementById('int-delete-draft-btn')
  if (!order?.id) {
    if (titleEl) titleEl.textContent = 'New interview campaign'
    if (deleteBtn) deleteBtn.hidden = true
    if (typeof window.setInterviewHubSelection === 'function') window.setInterviewHubSelection(null)
    return
  }
  const editable = order.is_live && !['running', 'paused'].includes(order.status)
  if (titleEl) {
    titleEl.textContent = editable
      ? order.status === 'draft'
        ? 'Edit interview draft'
        : 'Edit interview task'
      : order.title || 'Interview task'
  }
  if (deleteBtn) deleteBtn.hidden = !editable
  if (typeof window.setInterviewHubSelection === 'function') window.setInterviewHubSelection(order.id)
}

function setInterviewFormLocked(locked) {
  const note = document.getElementById('int-form-lock-note')
  const zone = document.getElementById('int-upload-zone')
  const fileInput = document.getElementById('int-file-input')
  if (note) note.style.display = locked ? '' : 'none'
  if (zone) zone.style.opacity = locked ? '0.55' : ''
  if (zone) zone.style.pointerEvents = locked ? 'none' : ''
  if (fileInput) fileInput.disabled = Boolean(locked)
}

async function openInterviewDraft(orderId, { silent = false, scroll = true } = {}) {
  if (!orderId || !getAccessToken()) return false
  try {
    const order = await api(`/service-orders/${encodeURIComponent(orderId)}`)
    if (order.service_code !== 'interview') throw new Error('Not an interview task')

    if (order.is_finished || ['running', 'paused'].includes(order.status)) {
      await openInterviewResults(orderId)
      return true
    }

    if (typeof window.goNav === 'function') window.goNav('interviews')

    clearInterviewFormFields()
    interviewLaunch.draftOrderId = order.id
    state.interviewOrderId = order.id
    localStorage.setItem(INTERVIEW_DRAFT_LS_KEY, order.id)

    const recipData = await api(`/service-orders/${encodeURIComponent(orderId)}/recipients`)
    interviewLaunch.recipients = recipData?.recipients || order.recipients || []
    interviewLaunch.intakeSummary = recipData?.summary || null

    applyInterviewOrderToForm(order)
    renderInterviewCandidateList()
    updateInterviewFormChrome(order)

    const paidLocked = order.payment_status === 'approved'
    setInterviewFormLocked(paidLocked)

    const statusEl = document.getElementById('int-save-status')
    if (statusEl) {
      statusEl.style.display = 'block'
      const n = interviewLaunch.recipients.length
      statusEl.textContent = n
        ? `Editing saved task — ${n} candidate(s) loaded`
        : 'Editing saved task — add candidates below'
    }

    if (scroll) {
      document.getElementById('int-form-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
    if (!silent) window.toast?.('Draft loaded — edit below and save', 'tg')
    if (typeof window.reloadInterviewHub === 'function') void window.reloadInterviewHub()
    return true
  } catch (e) {
    if (!silent) window.toast?.(e.message || 'Could not open draft', 'tr')
    return false
  }
}

async function deleteInterviewOrder(orderId, { clearForm = true } = {}) {
  if (!orderId || !getAccessToken()) return false
  const ok = await confirmDialog({
    title: 'Delete interview task?',
    message: 'This removes the task, candidates, and uploaded CVs. This cannot be undone.',
    okLabel: 'Delete',
    danger: true,
  })
  if (!ok) return false
  try {
    await api(`/service-orders/${encodeURIComponent(orderId)}`, { method: 'DELETE' })
    if (clearForm && (interviewLaunch.draftOrderId === orderId || state.interviewOrderId === orderId)) {
      clearInterviewFormFields()
      interviewLaunch.draftOrderId = null
      state.interviewOrderId = null
      localStorage.removeItem(INTERVIEW_DRAFT_LS_KEY)
      updateInterviewReferenceCard(null)
      updateInterviewFormChrome(null)
    }
    if (typeof window.reloadInterviewHub === 'function') await window.reloadInterviewHub()
    window.toast?.('Interview task deleted', 'tg')
    return true
  } catch (e) {
    window.toast?.(e.message || 'Could not delete task', 'tr')
    return false
  }
}

async function startNewInterviewTask() {
  const hasWork =
    (interviewLaunch.recipients || []).length > 0 ||
    Boolean(document.getElementById('int-role')?.value?.trim()) ||
    Boolean(document.getElementById('int-criteria')?.value?.trim())
  if (hasWork) {
    const ok = window.confirm(
      'Start a new interview task? Your current draft stays saved under Running interviews → Live.',
    )
    if (!ok) return
  }
  try {
    const data = await api('/service-orders/interview/draft/new', { method: 'POST', body: '{}' })
    resetInterviewFormForNewTask()
    const order = data?.order
    if (order?.id) {
      interviewLaunch.draftOrderId = order.id
      state.interviewOrderId = order.id
      localStorage.setItem(INTERVIEW_DRAFT_LS_KEY, order.id)
      updateInterviewReferenceCard(order)
      updateInterviewFormChrome(order)
    }
    window.toast?.('New interview task ready — new reference ID assigned', 'tg')
    if (typeof window.reloadInterviewHub === 'function') void window.reloadInterviewHub()
  } catch (e) {
    window.toast?.(e.message || 'Could not create new interview task', 'tr')
  }
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
        const hasCv = Boolean(r.has_cv_file)
        const cvActions = hasCv
          ? `<button type="button" class="btn bsm btng int-cv-dl" data-int-cv="${r.id}" title="Download CV"><i class="ti ti-download"></i></button>`
          : ''
        return `<tr>
          <td>${escHtml(r.name || '—')}</td>
          <td>${phoneCell}</td>
          <td>${emailCell}</td>
          <td>${cvQualityBadge(r.cv_quality)}${r.cv_filename ? `<div class="muted" style="font-size:10px;margin-top:2px">${escHtml(r.cv_filename)}</div>` : ''}</td>
          <td style="font-size:10.5px;color:var(--amb)">${issues}</td>
          <td style="white-space:nowrap">${cvActions}<button type="button" class="btn bsm btnr int-del-btn" data-int-del="${r.id}" title="Remove"><i class="ti ti-trash"></i></button></td>
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
  tableWrap.querySelectorAll('[data-int-cv]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      void downloadInterviewRecipientCv(btn.getAttribute('data-int-cv'))
    })
  })

  interviewLaunch.contactCount = recipients.length
  interviewLaunch.contactCountKnown = true
  void refreshInterviewQuoteFromDraft()
  updateInterviewLaunchPhaseUi()
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
  updateInterviewReferenceCard(data?.order)
  renderInterviewCandidateList()
  return interviewLaunch.draftOrderId
}

function isCvEmailEnabled() {
  return document.getElementById('int-cv-email-toggle')?.classList.contains('on') ?? false
}

function setCvEmailEnabled(on) {
  const toggle = document.getElementById('int-cv-email-toggle')
  const panel = document.getElementById('int-cv-email-window')
  const label = document.getElementById('int-cv-email-state-label')
  if (!toggle) return
  toggle.classList.toggle('on', on)
  toggle.classList.toggle('off', !on)
  toggle.setAttribute('aria-checked', on ? 'true' : 'false')
  if (panel) panel.hidden = !on
  if (label) {
    label.textContent = on ? 'ON' : 'OFF'
    label.className = on ? 'bdg bg' : 'bdg ba'
  }
  if (typeof window.updateIntCvEmailWindow === 'function') window.updateIntCvEmailWindow()
  updateInterviewLaunchPhaseUi()
}

function getInterviewCvCollectionPhase() {
  const enabled = isCvEmailEnabled()
  const count = (interviewLaunch.recipients || []).length
  if (!enabled) {
    return { enabled: false, complete: true, blocksLaunch: false, state: 'disabled', endLabel: '', candidateCount: count }
  }
  if (interviewLaunch.cvClosedEarly) {
    const cv = cvEmailSchedulePayload()
    const end = cv.cv_email_end_at ? new Date(cv.cv_email_end_at) : new Date()
    const endLabel = end.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    return { enabled: true, complete: true, blocksLaunch: false, state: 'after', endLabel, candidateCount: count, closedEarly: true }
  }
  const cv = cvEmailSchedulePayload()
  if (!cv.cv_email_start_at || !cv.cv_email_end_at) {
    return { enabled: true, complete: false, blocksLaunch: true, state: 'incomplete', endLabel: '—', candidateCount: count }
  }
  const start = new Date(cv.cv_email_start_at)
  const end = new Date(cv.cv_email_end_at)
  const now = new Date()
  const endLabel = end.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return { enabled: true, complete: false, blocksLaunch: true, state: 'incomplete', endLabel: '—', candidateCount: count }
  }
  if (now <= end) {
    return {
      enabled: true,
      complete: false,
      blocksLaunch: true,
      state: now < start ? 'before' : 'open',
      endLabel,
      candidateCount: count,
    }
  }
  return { enabled: true, complete: true, blocksLaunch: false, state: 'after', endLabel, candidateCount: count }
}

function validateAiCallWindowAfterCvCollection() {
  const phase = getInterviewCvCollectionPhase()
  if (phase.blocksLaunch) {
    if (phase.state === 'before') {
      return 'CV email collection has not started yet — AI quote and launch unlock after the collection window ends'
    }
    if (phase.state === 'open') {
      return `CV email collection is open until ${phase.endLabel}. Wait for it to finish so pricing uses the final candidate list`
    }
    return 'Set CV email collection start and end times, or turn email intake OFF if you only use file upload'
  }
  if (!phase.enabled) return null
  const cv = cvEmailSchedulePayload()
  const sched = schedulePayload('int')
  if (!sched.scheduled_start_at || !cv.cv_email_end_at) return null
  const aiStart = new Date(sched.scheduled_start_at)
  const cvEnd = new Date(cv.cv_email_end_at)
  if (aiStart < cvEnd) {
    return `AI calling must start after CV collection ends (${phase.endLabel})`
  }
  return null
}

function updateInterviewLaunchPhaseUi() {
  const phase = getInterviewCvCollectionPhase()
  const banner = document.getElementById('int-cv-phase-banner')
  const bannerText = document.getElementById('int-cv-phase-banner-text')
  const previewBtn = document.getElementById('int-preview-open')
  const blockedNote = document.getElementById('int-launch-blocked-note')
  const aiWrap = document.getElementById('int-ai-call-window-wrap')
  const aiLockedNote = document.getElementById('int-ai-call-locked-note')
  const startDate = document.getElementById('int-start-date')

  if (banner && bannerText) {
    if (phase.enabled && phase.blocksLaunch) {
      banner.style.display = ''
      if (phase.state === 'before') {
        bannerText.textContent = `Step 1 not started yet. Email CV intake opens soon — ${phase.candidateCount} candidate(s) so far. Quote and AI calls unlock after collection ends (${phase.endLabel}).`
      } else if (phase.state === 'open') {
        bannerText.textContent = `Collecting CVs by email until ${phase.endLabel} — ${phase.candidateCount} candidate(s) so far. You cannot quote or launch AI interviews until this window closes.`
      } else {
        bannerText.textContent = 'Turn email intake ON and set start/end times for Step 1, or turn it OFF if you only upload files manually.'
      }
    } else if (phase.enabled && phase.complete) {
      banner.style.display = ''
      const earlyNote = phase.closedEarly ? ' (closed early)' : ''
      bannerText.textContent = `Step 1 complete${earlyNote} — email collection ended ${phase.endLabel}. ${phase.candidateCount} candidate(s) ready. You can now preview, quote, pay, and schedule AI calls (Step 2).`
    } else {
      banner.style.display = 'none'
    }
  }

  const blockLaunch = phase.blocksLaunch
  if (previewBtn) {
    previewBtn.disabled = blockLaunch
    previewBtn.title = blockLaunch ? 'Available after CV email collection ends' : 'Preview final list and get quote'
  }
  if (blockedNote) {
    if (blockLaunch) {
      blockedNote.style.display = ''
      blockedNote.textContent = phase.state === 'open'
        ? `Preview & quote locked until ${phase.endLabel} — final candidate count needed before billing.`
        : 'Preview & quote locked until Step 1 email collection is configured and finished.'
    } else {
      blockedNote.style.display = 'none'
    }
  }
  if (aiWrap) {
    aiWrap.style.opacity = blockLaunch ? '0.55' : ''
    aiWrap.style.pointerEvents = blockLaunch ? 'none' : ''
  }
  if (aiLockedNote) {
    aiLockedNote.style.display = blockLaunch ? '' : 'none'
  }
  const closeEarlyBtn = document.getElementById('int-cv-close-early')
  if (closeEarlyBtn) {
    const showClose = phase.enabled && phase.blocksLaunch && (phase.state === 'before' || phase.state === 'open')
    closeEarlyBtn.style.display = showClose ? '' : 'none'
    closeEarlyBtn.disabled = !interviewLaunch.draftOrderId && !state.interviewOrderId
  }

  if (startDate && phase.enabled && phase.complete && phase.endLabel) {
    const cv = cvEmailSchedulePayload()
    if (cv.cv_email_end_at) {
      const cvEnd = new Date(cv.cv_email_end_at)
      if (!Number.isNaN(cvEnd.getTime())) {
        const pad = (n) => String(n).padStart(2, '0')
        startDate.min = `${cvEnd.getFullYear()}-${pad(cvEnd.getMonth() + 1)}-${pad(cvEnd.getDate())}`
      }
    }
  } else if (startDate) {
    startDate.removeAttribute('min')
  }
}

function cvEmailSchedulePayload() {
  const sd = document.getElementById('int-cv-start-date')
  const st = document.getElementById('int-cv-start-time')
  const ed = document.getElementById('int-cv-end-date')
  const et = document.getElementById('int-cv-end-time')
  if (!sd?.value || !ed?.value) return {}
  return {
    cv_email_start_at: `${sd.value}T${st?.value || '09:00'}:00`,
    cv_email_end_at: `${ed.value}T${et?.value || '17:00'}:00`,
  }
}

function applyCvEmailFromConfig(cfg) {
  interviewLaunch.cvClosedEarly = Boolean(cfg?.cv_collection_closed_early_at)
  setCvEmailEnabled(Boolean(cfg?.cv_email_enabled))
  if (cfg?.cv_email_enabled && cfg.cv_email_start_at && cfg.cv_email_end_at) {
    applyIsoScheduleToForm('int-cv', cfg.cv_email_start_at, cfg.cv_email_end_at)
    if (typeof window.updateIntCvEmailWindow === 'function') window.updateIntCvEmailWindow()
  }
}

async function closeInterviewCvCollectionEarly() {
  const oid = interviewLaunch.draftOrderId || state.interviewOrderId
  if (!oid) {
    window.toast?.('Save the interview task first', 'tr')
    return
  }
  if (!isCvEmailEnabled()) {
    window.toast?.('Turn on CV email collection first', 'tr')
    return
  }
  const phase = getInterviewCvCollectionPhase()
  if (phase.complete) {
    window.toast?.('CV collection is already closed', 'tr')
    return
  }
  if (!window.confirm('Close CV email collection now? Quote and AI calls will unlock immediately.')) return
  try {
    const res = await api(`/service-orders/${encodeURIComponent(oid)}/interview/cv-collection/close-early`, {
      method: 'POST',
    })
    interviewLaunch.cvClosedEarly = Boolean(res?.closed_early)
    if (res?.end_at) {
      applyIsoScheduleToForm('int-cv', res.start_at, res.end_at)
    }
    updateInterviewLaunchPhaseUi()
    void refreshInterviewQuoteFromDraft().catch(() => {})
    window.toast?.('CV collection closed — you can quote and launch AI calls', 'tg')
  } catch (e) {
    window.toast?.(e?.message || 'Could not close CV collection', 'tr')
  }
}

function collectInterviewConfig() {
  const agent = selectedInterviewAgent()
  const scriptText = (document.getElementById('int-ai-script')?.value || '').trim()
  const cvOn = isCvEmailEnabled()
  return {
    role: (document.getElementById('int-role')?.value || '').trim(),
    criteria: (document.getElementById('int-criteria')?.value || '').trim(),
    delivery: deliveryFromInterviewForm(),
    agent_id: agent?.id || interviewLaunch.selectedAgentId || '',
    agent_voice_label: agent?.voice_label || agent?.name || '',
    script_mode: scriptModeFromButtons('interview'),
    approved_script: scriptText || state.interviewScriptPayload?.script_text || '',
    script_questions: state.interviewScriptPayload?.questions || [],
    system_prompt: state.interviewScriptPayload?.system_prompt || '',
    script_approved: state.interviewScriptApproved,
    cv_email_enabled: cvOn,
    ...(cvOn ? cvEmailSchedulePayload() : {}),
  }
}

function applyIsoScheduleToForm(prefix, startIso, endIso) {
  if (!startIso || !endIso) return
  const start = new Date(startIso)
  const end = new Date(endIso)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return
  const pad = (n) => String(n).padStart(2, '0')
  const fmtDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  const fmtTime = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`
  const sd = document.getElementById(`${prefix}-start-date`)
  const st = document.getElementById(`${prefix}-start-time`)
  const ed = document.getElementById(`${prefix}-end-date`)
  const et = document.getElementById(`${prefix}-end-time`)
  if (sd) sd.value = fmtDate(start)
  if (st) st.value = fmtTime(start)
  if (ed) ed.value = fmtDate(end)
  if (et) et.value = fmtTime(end)
  if (prefix === 'int' && typeof window.updateIntWindow === 'function') window.updateIntWindow()
  if (prefix === 'int-cv' && typeof window.updateIntCvEmailWindow === 'function') window.updateIntCvEmailWindow()
}

function applyInterviewOrderToForm(order) {
  const cfg = order?.config || {}
  const roleEl = document.getElementById('int-role')
  const criteriaEl = document.getElementById('int-criteria')
  const scriptEl = document.getElementById('int-ai-script')
  if (roleEl && cfg.role) roleEl.value = cfg.role
  if (criteriaEl && cfg.criteria) criteriaEl.value = cfg.criteria
  if (cfg.agent_id) {
    interviewLaunch.selectedAgentId = cfg.agent_id
    const sel = document.getElementById('int-agent-select')
    if (sel) sel.value = cfg.agent_id
  }
  const scriptText = cfg.approved_script || ''
  if (scriptText) {
    if (scriptEl) scriptEl.value = scriptText
    state.interviewScriptPayload = {
      ...(state.interviewScriptPayload || {}),
      script_text: scriptText,
      script_questions: cfg.script_questions || [],
      system_prompt: cfg.system_prompt || '',
    }
    showAiPanel('int', true)
  }
  if (cfg.script_approved) {
    state.interviewScriptApproved = true
    setAiStatus('int', true)
  } else {
    state.interviewScriptApproved = false
    setAiStatus('int', false)
  }
  applyIsoScheduleToForm('int', order.scheduled_start_at, order.scheduled_end_at)
  applyCvEmailFromConfig(cfg)
  const cvPhase = order?.cv_collection
  if (cvPhase) {
    interviewLaunch.cvClosedEarly = Boolean(cvPhase.closed_early)
  }
  updateInterviewReferenceCard(order)
  updateInterviewLaunchPhaseUi()
}

async function saveInterviewDraft({ silent = false } = {}) {
  if (interviewLaunch.saving) return false
  interviewLaunch.saving = true
  const saveBtn = document.getElementById('int-save-draft')
  if (saveBtn) saveBtn.disabled = true
  try {
    await ensureInterviewDraftOrder()
    if (isCvEmailEnabled()) {
      const cv = cvEmailSchedulePayload()
      if (!cv.cv_email_start_at || !cv.cv_email_end_at) {
        window.toast?.('CV collection via email is ON — set start and end date/time on the Task reference card', 'tr')
        return false
      }
    }
    const role = (document.getElementById('int-role')?.value || '').trim()
    const title = role || 'Interview draft'
    const sched = schedulePayload('int')
    const data = await api('/service-orders/interview/draft', {
      method: 'POST',
      body: JSON.stringify({
        order_id: interviewLaunch.draftOrderId || undefined,
        title,
        role,
        criteria: (document.getElementById('int-criteria')?.value || '').trim(),
        config: collectInterviewConfig(),
        ...sched,
      }),
    })
    interviewLaunch.draftOrderId = data?.order?.id || interviewLaunch.draftOrderId
    state.interviewOrderId = interviewLaunch.draftOrderId
    interviewLaunch.recipients = data?.recipients || interviewLaunch.recipients
    interviewLaunch.intakeSummary = data?.summary || interviewLaunch.intakeSummary
    updateInterviewReferenceCard(data?.order)
    updateInterviewFormChrome(data?.order)
    if (interviewLaunch.draftOrderId) {
      localStorage.setItem(INTERVIEW_DRAFT_LS_KEY, interviewLaunch.draftOrderId)
    }
    const statusEl = document.getElementById('int-save-status')
    if (statusEl) {
      statusEl.style.display = 'block'
      const n = (interviewLaunch.recipients || []).length
      statusEl.textContent = `Saved ${new Date().toLocaleTimeString()} — ${n ? `${n} candidate(s) on server` : 'form saved'} · safe to close this tab`
    }
    if (!silent) window.toast?.('Interview draft saved', 'tg')
    if (typeof window.reloadInterviewHub === 'function') void window.reloadInterviewHub()
    return true
  } catch (e) {
    if (!silent) window.toast?.(e.message || 'Could not save draft', 'tr')
    return false
  } finally {
    interviewLaunch.saving = false
    if (saveBtn) saveBtn.disabled = false
  }
}

async function restoreInterviewDraft() {
  if (!getAccessToken()) return
  const savedId = localStorage.getItem(INTERVIEW_DRAFT_LS_KEY)
  if (savedId) {
    const ok = await openInterviewDraft(savedId, { silent: true, scroll: false })
    if (ok) return
    localStorage.removeItem(INTERVIEW_DRAFT_LS_KEY)
  }
  try {
    const data = await api('/service-orders/interview/draft')
    const order = data?.order
    if (!order?.id) return
    interviewLaunch.draftOrderId = order.id
    state.interviewOrderId = order.id
    interviewLaunch.recipients = data.recipients || []
    interviewLaunch.intakeSummary = data.summary || null
    applyInterviewOrderToForm(order)
    renderInterviewCandidateList()
    updateInterviewFormChrome(order)
    setInterviewFormLocked(order.payment_status === 'approved')
    localStorage.setItem(INTERVIEW_DRAFT_LS_KEY, order.id)
    const statusEl = document.getElementById('int-save-status')
    if (statusEl && interviewLaunch.recipients.length) {
      statusEl.style.display = 'block'
      statusEl.textContent = `Draft restored — ${interviewLaunch.recipients.length} candidate(s) ready to continue`
    }
  } catch {
    /* no draft yet */
  }
}

function validateInterviewLaunch() {
  const errors = []
  const cvBlock = validateAiCallWindowAfterCvCollection()
  if (cvBlock) errors.push(cvBlock)
  const hasDraftList = (interviewLaunch.recipients || []).length > 0
  if (!hasDraftList && !state.interviewFile) {
    errors.push('Upload a candidate list or CV files first')
  }
  if (hasDraftList) {
    const ready = interviewIntakeReadyCount()
    const total = interviewLaunch.recipients.length
    if (ready === 0) errors.push('Add phone numbers for at least one candidate before launching')
    else if (ready < total) errors.push(`${total - ready} candidate(s) still missing phone — add or delete them first`)
  }
  const sched = schedulePayload('int')
  if (!sched.scheduled_start_at) errors.push('Please set a start and end date first')
  if (!state.interviewScriptApproved) errors.push('Generate your AI script, read it, then click Approve before launching')
  return errors
}

function buildInterviewPreviewHtml() {
  const role = (document.getElementById('int-role')?.value || '').trim() || '—'
  const criteria = (document.getElementById('int-criteria')?.value || '').trim() || '—'
  const agent = selectedInterviewAgent()
  const agentLabel = agent?.name || agent?.voice_label || 'Default agent'
  const sched = schedulePayload('int')
  const windowLabel = sched.scheduled_start_at
    ? `${formatScheduleLabel(sched.scheduled_start_at)} → ${formatScheduleLabel(sched.scheduled_end_at)}`
    : 'Not set — add dates on the form'
  const recipients = interviewLaunch.recipients || []
  const summary = interviewLaunch.intakeSummary || {}
  const scriptText = (document.getElementById('int-ai-script')?.value || state.interviewScriptPayload?.script_text || '').trim()
  const scriptStatus = state.interviewScriptApproved ? '<span class="bdg bg">Approved</span>' : '<span class="bdg ba">Draft — approve before pay</span>'
  const quote = interviewLaunch.quote
  const quoteLines = quote?.lines || []
  const quoteTotal = quote?.total_gbp || (quote?.total_pence != null ? fmtGbp(quote.total_pence) : interviewLaunch.preparedOrder?.quote_total_gbp || '—')

  const candidateRows = recipients.length
    ? `<div class="int-preview-table-wrap"><table class="res-table" style="font-size:11.5px"><thead><tr><th>Name</th><th>Phone</th><th>CV</th><th>Ready</th></tr></thead><tbody>${recipients
        .map(
          (r) => `<tr>
            <td>${escHtml(r.name || '—')}</td>
            <td>${escHtml(r.phone || '—')}</td>
            <td>${cvQualityBadge(r.cv_quality)}</td>
            <td>${r.intake_ready ? '<span class="bdg bg">Yes</span>' : '<span class="bdg br">No</span>'}</td>
          </tr>`,
        )
        .join('')}</tbody></table></div>`
    : '<p class="muted">No candidates uploaded yet.</p>'

  return `
    <div class="int-preview-section"><h4><i class="ti ti-briefcase"></i> Role &amp; criteria</h4>
      <div class="int-preview-meta"><strong>Role:</strong> ${escHtml(role)}<br/><strong>Criteria:</strong> ${escHtml(criteria)}</div></div>
    <div class="int-preview-section"><h4><i class="ti ti-microphone"></i> Voice agent &amp; window</h4>
      <div class="int-preview-meta"><strong>Agent:</strong> ${escHtml(agentLabel)}<br/><strong>Calling window:</strong> ${escHtml(windowLabel)}</div></div>
    <div class="int-preview-section"><h4><i class="ti ti-users"></i> Candidates (${summary.total || recipients.length})</h4>${candidateRows}</div>
    <div class="int-preview-section"><h4><i class="ti ti-script"></i> Interview script ${scriptStatus}</h4>
      <pre style="max-height:160px;overflow:auto;font-size:11.5px">${escHtml(scriptText || 'No script generated yet.')}</pre></div>
    <div class="int-preview-section"><h4><i class="ti ti-receipt"></i> Pricing</h4>
      ${quoteLines.length ? quoteLines.map((l) => `<div class="int-preview-meta">${escHtml(l.detail || l.label || '')}</div>`).join('') : '<div class="muted">Quote updates when candidates are ready — click Launch interviews to refresh.</div>'}
      <div class="int-preview-quote">${escHtml(String(quoteTotal))}</div></div>`
}

function closeInterviewPreview() {
  document.getElementById('int-preview-overlay')?.classList.remove('show')
}

async function openInterviewPreview() {
  const role = (document.getElementById('int-role')?.value || '').trim()
  const hasCandidates = (interviewLaunch.recipients || []).length > 0
  if (!role && !hasCandidates) {
    window.toast?.('Add a role or upload candidates before previewing', 'tr')
    return
  }
  await saveInterviewDraft({ silent: true })
  if (hasCandidates) await refreshInterviewQuoteFromDraft()
  const body = document.getElementById('int-preview-body')
  if (body) body.innerHTML = buildInterviewPreviewHtml()
  const payBtn = document.getElementById('int-preview-pay')
  if (payBtn) payBtn.disabled = !interviewLaunch.preparedOrder && !interviewLaunch.quote
  document.getElementById('int-preview-overlay')?.classList.add('show')
}

async function prepareInterviewLaunchOrder() {
  const errors = validateInterviewLaunch()
  if (errors.length) {
    window.toast?.(errors[0], 'tr')
    if (errors.some((e) => /script/i.test(e))) {
      showAiPanel('int', true)
      document.getElementById('int-ai-script')?.focus()
    }
    return null
  }

  await saveInterviewDraft({ silent: true })
  const title = (document.getElementById('int-role')?.value || 'Interview campaign').trim().slice(0, 120)
  const sched = schedulePayload('int')
  const config = collectInterviewConfig()

  try {
    let order
    if (interviewLaunch.draftOrderId) {
      order = await api(`/service-orders/${interviewLaunch.draftOrderId}`, {
        method: 'PATCH',
        body: JSON.stringify({ title, config, ...sched }),
      })
      order = await api(`/service-orders/${order.id}/quote`, { method: 'POST' })
    } else {
      order = await api('/service-orders', {
        method: 'POST',
        body: JSON.stringify({ service_code: 'interview', title, config }),
      })
      if (state.interviewFile) {
        order = await uploadRecipients(order.id, state.interviewFile)
      }
      await api(`/service-orders/${order.id}`, { method: 'PATCH', body: JSON.stringify(sched) })
      order = await api(`/service-orders/${order.id}/quote`, { method: 'POST' })
    }

    const quoteText = (order.quote_breakdown || []).map((l) => l.detail || l.label).join('\n')
    interviewLaunch.preparedOrder = order
    interviewLaunch.preparedQuoteText = quoteText
    interviewLaunch.quote = {
      total_pence: order.quote_total_pence,
      total_gbp: order.quote_total_gbp,
      lines: order.quote_breakdown || [],
    }
    return order
  } catch (e) {
    window.toast?.(e.message || 'Could not prepare launch', 'tr')
    return null
  }
}

async function payPreparedInterviewOrder() {
  let order = interviewLaunch.preparedOrder
  if (!order) {
    order = await prepareInterviewLaunchOrder()
    if (!order) return
    const body = document.getElementById('int-preview-body')
    if (body) body.innerHTML = buildInterviewPreviewHtml()
  }
  await offerOrderPayment(order, interviewLaunch.preparedQuoteText)
  closeInterviewPreview()
  await loadOrdersIntoUi()
}

async function launchInterviewFromPreview() {
  const order = await prepareInterviewLaunchOrder()
  if (!order) return
  const body = document.getElementById('int-preview-body')
  if (body) body.innerHTML = buildInterviewPreviewHtml()
  const payBtn = document.getElementById('int-preview-pay')
  if (payBtn) payBtn.disabled = false
  window.toast?.('Campaign quoted — click Pay to continue', 'tg')
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
  document.getElementById('int-role')?.addEventListener('focus', () => {
    void ensureInterviewDraftOrder().catch(() => {})
  })
  document.getElementById('int-new-task-btn')?.addEventListener('click', () => void startNewInterviewTask())
  document.getElementById('int-delete-draft-btn')?.addEventListener('click', () => {
    const id = interviewLaunch.draftOrderId
    if (!id) return
    void deleteInterviewOrder(id)
  })
  bindInterviewReferenceCopy()
  document.getElementById('int-cv-email-toggle')?.addEventListener('click', () => {
    setCvEmailEnabled(!isCvEmailEnabled())
  })
  document.getElementById('int-cv-close-early')?.addEventListener('click', () => void closeInterviewCvCollectionEarly())
  ;['int-cv-start-date', 'int-cv-start-time', 'int-cv-end-date', 'int-cv-end-time'].forEach((id) => {
    document.getElementById(id)?.addEventListener('input', () => {
      if (typeof window.updateIntCvEmailWindow === 'function') window.updateIntCvEmailWindow()
      updateInterviewLaunchPhaseUi()
    })
  })
  ;['int-start-date', 'int-start-time', 'int-end-date', 'int-end-time'].forEach((id) => {
    document.getElementById(id)?.addEventListener('input', () => updateInterviewLaunchPhaseUi())
  })
  document.getElementById('int-save-draft')?.addEventListener('click', () => void saveInterviewDraft())
  document.getElementById('int-preview-open')?.addEventListener('click', () => void openInterviewPreview())
  document.getElementById('int-preview-close')?.addEventListener('click', closeInterviewPreview)
  document.getElementById('int-preview-close-top')?.addEventListener('click', closeInterviewPreview)
  document.getElementById('int-preview-save')?.addEventListener('click', async () => {
    await saveInterviewDraft()
    const body = document.getElementById('int-preview-body')
    if (body) body.innerHTML = buildInterviewPreviewHtml()
  })
  document.getElementById('int-preview-launch')?.addEventListener('click', () => void launchInterviewFromPreview())
  document.getElementById('int-preview-pay')?.addEventListener('click', () => void payPreparedInterviewOrder())
  document.getElementById('int-preview-overlay')?.addEventListener('click', (e) => {
    if (e.target?.id === 'int-preview-overlay') closeInterviewPreview()
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
    if (typeof window.reloadInterviewHub === 'function') {
      await window.reloadInterviewHub()
    }
    const [interviews, credits, reportPayload] = await Promise.all([
      api('/service-orders?service_code=interview'),
      api('/service-orders/credits').catch(() => ({})),
      api('/service-orders/interview-reports?period=month').catch(() => null),
    ])
    renderInterviewKpis(interviews, credits, reportPayload?.overview)
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

  if (await tryStartPaidOrder(serviceCode)) return
  const order = await prepareInterviewLaunchOrder()
  if (!order) return
  await offerOrderPayment(order, interviewLaunch.preparedQuoteText)
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
  window.openInterviewDraft = openInterviewDraft
  window.deleteInterviewOrder = deleteInterviewOrder
  window.saveInterviewDraft = () => saveInterviewDraft()
  window.startNewInterviewTask = () => void startNewInterviewTask()
  window.openInterviewPreview = () => openInterviewPreview()
  window.launchIntCampaign = async () => {
    await openInterviewPreview()
  }
  async function refreshSchedulingOAuthStatus() {
    const el = document.getElementById('scheduling-oauth-status')
    if (!el) return
    try {
      const st = await api('/service-orders/scheduling/status')
      if (st?.connected) {
        el.textContent = `Connected: ${st.provider || 'scheduling'}${st.owner_name ? ` (${st.owner_name})` : ''}`
      } else {
        el.textContent = 'Not connected — choose Calendly or Cronofy'
      }
    } catch {
      el.textContent = ''
    }
  }
  window.startCalendlyOAuth = async () => {
    try {
      const res = await api('/service-orders/scheduling/oauth/calendly/start')
      if (res?.authorize_url) window.location.href = res.authorize_url
      else window.toast?.('Calendly OAuth is not configured on the server', 'tr')
    } catch (e) {
      window.toast?.(e?.message || 'Could not start Calendly connection', 'tr')
    }
  }
  window.startCronofyOAuth = async () => {
    try {
      const res = await api('/service-orders/scheduling/oauth/cronofy/start')
      if (res?.authorize_url) window.location.href = res.authorize_url
      else window.toast?.('Cronofy OAuth is not configured on the server', 'tr')
    } catch (e) {
      window.toast?.(e?.message || 'Could not start Cronofy connection', 'tr')
    }
  }
  document.getElementById('scheduling-oauth-calendly')?.addEventListener('click', () => window.startCalendlyOAuth())
  document.getElementById('scheduling-oauth-cronofy')?.addEventListener('click', () => window.startCronofyOAuth())
  void refreshSchedulingOAuthStatus()
  if (typeof URLSearchParams !== 'undefined' && window.location.search.includes('scheduling=connected')) {
    void refreshSchedulingOAuthStatus()
    window.toast?.('Scheduling provider connected', 'tg')
  }
  document.getElementById('int-results-export-csv')?.addEventListener('click', async () => {
    const oid = interviewResultsUi.orderId || state.interviewOrderId
    if (!oid) return
    await downloadAuthenticatedFile(`/service-orders/${encodeURIComponent(oid)}/interview-results/export.csv`)
  })
  document.getElementById('int-results-export-pdf')?.addEventListener('click', async () => {
    const oid = interviewResultsUi.orderId || state.interviewOrderId
    if (!oid) return
    await downloadAuthenticatedFile(`/service-orders/${encodeURIComponent(oid)}/interview-results/export.pdf`)
  })
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
  void restoreInterviewDraft().catch(() => {})
  updateInterviewLaunchPhaseUi()
}

if (typeof window !== 'undefined') {
  window.payAndScheduleSurvey = (event) => {
    event?.preventDefault?.()
    void runSurveyLaunchFlow()
  }
}
