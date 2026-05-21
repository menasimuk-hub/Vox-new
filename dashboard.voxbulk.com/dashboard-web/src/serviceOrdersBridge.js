import { apiFetch, downloadAuthenticatedFile, getAccessToken, getApiBaseUrl } from './lib/api.js'
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

function deliveryFromInterviewForm() {
  const grp = document.getElementById('int-fmt-grp')
  if (!grp) return 'ai_call'
  const sel = grp.querySelector('.vo.sel')
  const txt = (sel && sel.textContent ? sel.textContent : '').toLowerCase()
  return txt.includes('zoom') ? 'zoom' : 'ai_call'
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
    if (!document.getElementById('prof-organiser-name')?.value?.trim()) {
      window.toast?.('Add Survey organiser in Profile settings (name heard on the call)', 'tr')
      return
    }
  }
  if (!isSurvey && !(roleEl?.value || '').trim()) {
    window.toast?.('Enter the role / position before generating', 'tr')
    roleEl?.focus()
    return
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

  const payload = isSurvey
    ? {
        service_code: 'survey',
        goal: goalEl?.value || '',
        contact_method: selectValue(document.getElementById('sur-contact-method')),
        max_call_length: selectValue(document.getElementById('sur-max-length')),
        client_context: getClientContextForApi(),
      }
    : {
        service_code: 'interview',
        role: roleEl?.value || '',
        criteria: criteriaEl?.value || '',
        delivery: deliveryFromInterviewForm(),
        client_context: getClientContextForApi(),
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
    if (isSurvey) state.surveyScriptPayload = materialised
    else state.interviewScriptPayload = materialised
    syncSurveyWhatsAppUi()
    window.toast?.(
      isSurvey && surveyUsesWhatsApp()
        ? 'Script ready — review it, use WhatsApp preview, then Approve'
        : 'Script ready — read it below and click Approve when happy',
      'tg',
    )
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
  window.toast?.('Script approved — you can launch when ready', 'tg')
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
  if (status === 'running') return '<span class="stat-live"><span style="width:6px;height:6px;border-radius:50%;background:var(--grn);display:inline-block;animation:lpulse 1.2s infinite"></span>Live</span>'
  if (status === 'paid' || status === 'scheduled') return '<span class="stat-wait">Ready to start</span>'
  if (status === 'completed') return '<span class="stat-done">Completed</span>'
  return `<span class="stat-wait">${status}</span>`
}

function renderOrderRow(order) {
  const icon = order.service_code === 'interview' ? 'ti-briefcase' : 'ti-clipboard-list'
  const target = order.service_code === 'interview' ? 'results-i' : 'results-s'
  const dispatch =
    order.report && order.status === 'running'
      ? ` · ${order.report.sent || 0} sent${order.report.failed ? `, ${order.report.failed} failed` : ''}${order.report.skipped ? `, ${order.report.skipped} skipped` : ''}`
      : ''
  const meta = `${order.recipient_count} contacts · ${order.quote_total_gbp}${order.payment_status === 'pending_approval' ? ' · payment pending' : ''}${dispatch}`
  return `<div class="proj-row" onclick="goNav('${target}')">
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
    const [surveys, interviews] = await Promise.all([
      api('/service-orders?service_code=survey'),
      api('/service-orders?service_code=interview'),
    ])
    const surHost = document.getElementById('sur-live-orders')
    const intHost = document.getElementById('int-live-orders')
    if (surHost) {
      const surRows = (surveys || []).slice(0, 8).map(renderOrderRow).join('')
      surHost.innerHTML = surRows
      const surEmpty = document.getElementById('sur-projects-empty')
      if (surEmpty) surEmpty.style.display = surRows ? 'none' : ''
    }
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

function bindUploads() {
  const surInput = document.getElementById('sur-file-input')
  const intInput = document.getElementById('int-file-input')
  const surZone = document.getElementById('sur-upload-zone')
  const intZone = document.getElementById('int-upload-zone')
  const surTpl = document.getElementById('sur-template-dl')
  const intTpl = document.getElementById('int-template-dl')

  async function ingestRecipientFile(file, serviceCode) {
    if (!file) {
      if (serviceCode === 'survey') setSampleRecipientFirstName('')
      return
    }
    const firstName = await parseFirstNameFromRecipientFile(file)
    if (serviceCode === 'survey') setSampleRecipientFirstName(firstName)
    if (firstName) {
      window.toast?.(`Preview will use contact: ${firstName}`, 'tg')
    }
  }

  if (surTpl) {
    surTpl.addEventListener('click', async (e) => {
      e.preventDefault()
      try {
        await downloadAuthenticatedFile('/service-orders/template.csv', 'voxbulk-contacts-template.csv')
      } catch (err) {
        window.toast?.(err.message || 'Could not download template', 'tr')
      }
    })
  }
  if (intTpl) {
    intTpl.addEventListener('click', async (e) => {
      e.preventDefault()
      try {
        await downloadAuthenticatedFile('/service-orders/template.csv', 'voxbulk-contacts-template.csv')
      } catch (err) {
        window.toast?.(err.message || 'Could not download template', 'tr')
      }
    })
  }
  if (surZone && surInput) {
    surZone.addEventListener('click', () => surInput.click())
    surInput.addEventListener('change', async () => {
      state.surveyFile = surInput.files?.[0] || null
      if (state.surveyFile) {
        window.toast?.(`Selected ${state.surveyFile.name}`, 'tg')
        await ingestRecipientFile(state.surveyFile, 'survey')
      }
    })
  }
  if (intZone && intInput) {
    intZone.addEventListener('click', () => intInput.click())
    intInput.addEventListener('change', async () => {
      state.interviewFile = intInput.files?.[0] || null
      if (state.interviewFile) {
        window.toast?.(`Selected ${state.interviewFile.name}`, 'tg')
        await ingestRecipientFile(state.interviewFile, 'interview')
      }
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
      await api(`/service-orders/${order.id}/start`, { method: 'POST' })
      window.toast?.('GoCardless payment approved — campaign started', 'tg')
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
  try {
    const credits = await api('/service-orders/credits')
    const available =
      order.service_code === 'survey'
        ? Number(credits?.survey_credits || 0)
        : Number(credits?.interview_credits || 0)
    if (available >= Number(order.recipient_count || 0) && order.recipient_count > 0) {
      const usePromo = window.confirm(
        `You have ${available} promo ${order.service_code} credit(s).\nThis order needs ${order.recipient_count}.\n\nUse promo credits instead of paying?`,
      )
      if (usePromo) {
        await submitPromoCreditPayment(order.id)
        return
      }
    }
  } catch {
    // fall through to normal payment options
  }

  const gc = Boolean(state.paymentOptions?.gocardless_available)
  const cash = state.paymentOptions?.cash_available !== false

  if (gc && cash) {
    const useGc = window.confirm(
      `${quoteText}\n\nOK = Pay with GoCardless (sandbox, no admin approval)\nCancel = Pay cash (testing, admin approval required)`,
    )
    if (useGc) {
      await startGocardlessOrderPayment(order.id)
      return
    }
    await submitCashOrderPayment(order.id)
    return
  }

  if (gc) {
    await startGocardlessOrderPayment(order.id)
    return
  }

  window.showConfirm?.(
    `Total ${order.quote_total_gbp}`,
    `${quoteText}\n\nAfter you pay cash, admin must approve before the campaign can start.`,
    'I paid cash',
    () => submitCashOrderPayment(order.id),
  )
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
  const base = getApiBaseUrl()
  const url = `${base}/service-orders/${orderId}/recipients/upload`
  const fd = new FormData()
  fd.append('file', file)
  const headers = new Headers()
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const orgId = localStorage.getItem('retover_org_id')
  if (orgId) headers.set('X-Retover-Org-Id', orgId)
  const res = await fetch(url, { method: 'POST', headers, body: fd })
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) throw new Error(data?.detail || 'Upload failed')
  return data
}

async function tryStartPaidOrder(serviceCode) {
  try {
    const orders = await api(`/service-orders?service_code=${encodeURIComponent(serviceCode)}`)
    const paid = (orders || []).find(
      (o) => o.payment_status === 'approved' && (o.status === 'paid' || o.status === 'scheduled'),
    )
    if (!paid) return false
    await api(`/service-orders/${paid.id}/start`, { method: 'POST' })
    window.toast?.('Campaign started — survey messages are being sent via Telnyx', 'tg')
    await loadOrdersIntoUi()
    return true
  } catch {
    return false
  }
}

async function runOrderFlow(serviceCode) {
  const isSurvey = serviceCode === 'survey'
  if (await tryStartPaidOrder(serviceCode)) return
  const file = isSurvey ? state.surveyFile : state.interviewFile
  const prefix = isSurvey ? 'sur' : 'int'
  if (!file) {
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
    let order = await api('/service-orders', {
      method: 'POST',
      body: JSON.stringify({ service_code: serviceCode, title, config }),
    })
    order = await uploadRecipients(order.id, file)
    await api(`/service-orders/${order.id}`, {
      method: 'PATCH',
      body: JSON.stringify(sched),
    })
    order = await api(`/service-orders/${order.id}/quote`, { method: 'POST' })

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
  document.getElementById('sur-ai-generate')?.addEventListener('click', () => generateServiceScript('survey'))
  document.getElementById('sur-ai-regen')?.addEventListener('click', () => generateServiceScript('survey'))
  document.getElementById('sur-ai-approve')?.addEventListener('click', () => approveServiceScript('survey'))
  document.getElementById('sur-wa-preview-btn')?.addEventListener('click', openSurveyWaPreview)
  document.getElementById('sur-contact-method')?.addEventListener('change', syncSurveyWhatsAppUi)

  document.getElementById('int-ai-generate')?.addEventListener('click', () => generateServiceScript('interview'))
  document.getElementById('int-ai-regen')?.addEventListener('click', () => generateServiceScript('interview'))
  document.getElementById('int-ai-approve')?.addEventListener('click', () => approveServiceScript('interview'))
}

export function initServiceOrdersBridge() {
  window.launchSurCampaign = () => runOrderFlow('survey')
  window.launchIntCampaign = async () => {
    await runOrderFlow('interview')
    const banner = document.getElementById('int-live-banner')
    if (banner) banner.style.display = 'none'
  }
  window.openSurveyWaPreview = openSurveyWaPreview
  window.closeSurveyWaPreview = closeSurveyWaPreview
  window.resetSurveyWaPreview = resetSurveyWaPreview
  document.getElementById('sur-wa-preview-overlay')?.addEventListener('click', (e) => {
    if (e.target?.id === 'sur-wa-preview-overlay') closeSurveyWaPreview()
  })
  bindUploads()
  bindScriptEditors()
  wireHelpChat()
  wireAiButtons()
  syncSurveyWhatsAppUi()
  syncWaPreviewHeader()
  loadPaymentOptions()
  completeGocardlessOrderReturn()
  loadOrdersIntoUi()
}
