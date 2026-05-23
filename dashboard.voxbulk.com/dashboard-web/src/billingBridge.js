import { apiFetch, downloadAuthenticatedFile } from './lib/api.js'

const GC_FLOW_KEY = 'voxbulk_gc_redirect_flow_id'
const PLAN_ICONS = ['ti-rocket', 'ti-trending-up', 'ti-building-skyscraper']
const PLAN_ICON_CLASS = ['pig', 'pip', 'pia']

const state = {
  plans: [],
  plansLoading: false,
  plansError: '',
  subscription: null,
  currentPlan: null,
  usage: null,
  invoices: [],
  busyPlanId: null,
  paymentOptions: null,
  checkoutStatus: 'idle', // idle | loading | error | return-error
  checkoutMessage: '',
}

function paymentOptions() {
  return state.paymentOptions || state.subscription?.payment_options || {}
}

function gocardlessAvailable() {
  return Boolean(paymentOptions().gocardless_available || state.subscription?.gocardless_checkout_available)
}

function billingQueryParam(name) {
  try {
    return new URLSearchParams(window.location.search).get(name)
  } catch {
    return null
  }
}

function clearBillingQuery() {
  try {
    const url = new URL(window.location.href)
    url.searchParams.delete('billing')
    url.searchParams.delete('redirect_flow_id')
    window.history.replaceState({}, '', url.pathname + url.search + url.hash)
  } catch {
    /* ignore */
  }
}

function setCheckoutStatus(status, message = '') {
  state.checkoutStatus = status
  state.checkoutMessage = message
  renderCheckoutStatus()
}

function renderCheckoutStatus() {
  const el = document.getElementById('packages-checkout-status')
  if (!el) return

  const { checkoutStatus, checkoutMessage } = state
  if (checkoutStatus === 'idle' || !checkoutMessage) {
    el.hidden = true
    el.textContent = ''
    el.className = 'billing-checkout-status'
    return
  }

  el.hidden = false
  el.textContent = checkoutMessage
  el.className = `billing-checkout-status billing-checkout-status--${checkoutStatus}`
}

function logBilling(event, detail = {}) {
  console.info(`[billing] ${event}`, detail)
}

async function completeGocardlessReturn() {
  const billing = billingQueryParam('billing')
  if (billing === 'cancelled') {
    sessionStorage.removeItem(GC_FLOW_KEY)
    clearBillingQuery()
    setCheckoutStatus('error', 'Payment setup was cancelled. You can choose a plan again when ready.')
    if (typeof window.toast === 'function') window.toast('Payment setup cancelled.', 'tw')
    return
  }
  if (billing !== 'success') return

  const redirectFlowId = sessionStorage.getItem(GC_FLOW_KEY) || billingQueryParam('redirect_flow_id')
  sessionStorage.removeItem(GC_FLOW_KEY)
  clearBillingQuery()
  if (!redirectFlowId) {
    const msg = 'Payment completed at GoCardless, but no checkout session was found. Please refresh or contact support.'
    setCheckoutStatus('return-error', msg)
    logBilling('complete_skipped_missing_redirect_flow_id')
    if (typeof window.toast === 'function') window.toast(msg, 'tw')
    return
  }

  setCheckoutStatus('loading', 'Completing your subscription…')

  try {
    const result = await apiFetch('/billing/subscription/gocardless/complete', {
      method: 'POST',
      body: JSON.stringify({ redirect_flow_id: redirectFlowId }),
    })
    state.currentPlan = result?.plan || state.currentPlan
    state.subscription = {
      ...(state.subscription || {}),
      subscription: result?.subscription || state.subscription?.subscription,
      plan: result?.plan || state.currentPlan,
    }
    await loadBillingData()
    renderAll()
    setCheckoutStatus('idle')
    const planName = result?.plan?.name || 'your new plan'
    if (typeof window.toast === 'function') window.toast(`Subscription updated to ${planName}.`, 'tg')
  } catch (e) {
    const message = e?.message || 'Could not complete GoCardless checkout'
    setCheckoutStatus('return-error', message)
    logBilling('complete_failed', { redirectFlowId, message, status: e?.status })
    if (typeof window.toast === 'function') window.toast(message, 'tr')
    else window.alert(message)
  }
}

async function startGocardlessUpgrade(plan) {
  logBilling('gocardless_start_request', { planId: plan.id, planCode: plan.code })

  const result = await apiFetch('/billing/subscription/gocardless/start', {
    method: 'POST',
    body: JSON.stringify({ plan_id: plan.id }),
  })

  const redirectFlowId = result?.redirect_flow_id
  const authorizationUrl = result?.authorization_url
  if (!redirectFlowId || !authorizationUrl) {
    throw new Error('GoCardless did not return a checkout URL')
  }

  sessionStorage.setItem(GC_FLOW_KEY, redirectFlowId)
  logBilling('gocardless_start_redirect', { planId: plan.id, redirectFlowId, environment: result?.environment })
  window.location.assign(authorizationUrl)
}

function fmtGbp(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(0)}`
}

function fmtGbpPrecise(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(2)}`
}

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function parseFeatures(plan) {
  try {
    const parsed = JSON.parse(plan.features_json || '[]')
    if (Array.isArray(parsed) && parsed.length) return parsed.map(String)
  } catch {
    /* ignore */
  }
  const out = []
  if (plan.calls_included) out.push(`${plan.calls_included} calls per month`)
  if (plan.whatsapp_included) out.push(`${plan.whatsapp_included} WhatsApp messages`)
  if (plan.sms_included) out.push(`${plan.sms_included} SMS messages`)
  if (plan.overage_per_min_pence) {
    out.push(`Overage ${fmtGbpPrecise(plan.overage_per_min_pence)}/min after included usage`)
  }
  return out.length ? out : ['Recovery queue', 'WhatsApp reminders', 'Usage wallet']
}

function planButtonLabel(plan, currentPlan) {
  if (state.busyPlanId === plan.id) return 'Redirecting to GoCardless…'
  if (!currentPlan) return `Choose ${plan.name}`
  if (plan.id === currentPlan.id) return 'Current plan'
  const oldPrice = Number(currentPlan.price_gbp_pence || 0)
  const newPrice = Number(plan.price_gbp_pence || 0)
  if (newPrice > oldPrice) return `Upgrade to ${plan.name}`
  if (newPrice < oldPrice) return `Downgrade to ${plan.name}`
  return `Switch to ${plan.name}`
}

function planButtonClass(plan, currentPlan) {
  if (!currentPlan || plan.id === currentPlan.id) return 'pbtn'
  const oldPrice = Number(currentPlan.price_gbp_pence || 0)
  const newPrice = Number(plan.price_gbp_pence || 0)
  return newPrice > oldPrice ? 'pbtn pg' : 'pbtn'
}

function renderPlanCard(plan, index, currentPlan, onSelect) {
  const isCurrent = currentPlan && plan.id === currentPlan.id
  const isBusy = state.busyPlanId === plan.id
  const isFeatured = index === 1 && (state.plans?.length || 0) >= 2
  const features = parseFeatures(plan)
  const icon = PLAN_ICONS[index % PLAN_ICONS.length]
  const iconClass = PLAN_ICON_CLASS[index % PLAN_ICON_CLASS.length]
  const interval = plan.interval === 'year' || plan.interval === 'yearly' ? '/yr' : '/mo'
  const creditLine = plan.overage_per_min_pence
    ? `Extra usage at ${fmtGbpPrecise(plan.overage_per_min_pence)}/min`
    : plan.description || 'Monthly subscription'

  const card = document.createElement('div')
  card.className = `plan${isFeatured && !isCurrent ? ' ft' : ''}`
  card.innerHTML = `
    ${isFeatured && !isCurrent ? '<div class="pptop">Popular</div>' : ''}
    <div class="pic ${iconClass}"><i class="ti ${icon}"></i></div>
    <div class="pnm">${escapeHtml(plan.name)}</div>
    <div class="pfor">${escapeHtml(plan.code)}</div>
    <div class="ppr">${fmtGbp(plan.price_gbp_pence)}<span>${interval}</span></div>
    <div class="pcr">${escapeHtml(creditLine)}</div>
    ${features.map((f) => `<div class="pfe"><i class="ti ti-check ck"></i>${escapeHtml(f)}</div>`).join('')}
    <button class="${planButtonClass(plan, currentPlan)}" type="button" ${isCurrent || isBusy || Boolean(state.busyPlanId) ? 'disabled' : ''}>
      ${escapeHtml(planButtonLabel(plan, currentPlan))}
    </button>
  `

  const btn = card.querySelector('button')
  if (btn && !isCurrent && !state.busyPlanId) {
    btn.addEventListener('click', () => onSelect(plan))
  }
  return card
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function setText(id, value) {
  const el = document.getElementById(id)
  if (el) el.textContent = value
}

function renderPlanGrid(containerId, onSelect) {
  const grid = document.getElementById(containerId)
  if (!grid) return
  grid.innerHTML = ''

  if (state.plansLoading) {
    grid.innerHTML = '<div style="grid-column:1/-1;padding:24px;text-align:center;color:var(--t3);font-size:13px">Loading subscription plans…</div>'
    return
  }

  if (state.plansError) {
    grid.innerHTML = `<div style="grid-column:1/-1;padding:24px;text-align:center;color:var(--red,#dc2626);font-size:13px">${escapeHtml(state.plansError)}</div>`
    return
  }

  if (!state.plans.length) {
    grid.innerHTML = '<div style="grid-column:1/-1;padding:24px;text-align:center;color:var(--t3);font-size:13px">No subscription plans available.</div>'
    return
  }

  state.plans.forEach((plan, index) => {
    grid.appendChild(renderPlanCard(plan, index, state.currentPlan, onSelect))
  })
}

function renderBillingSummary() {
  const plan = state.currentPlan
  const sub = state.subscription?.subscription || state.subscription
  setText('billing-plan-name', plan?.name || 'No plan')
  setText(
    'billing-plan-renew',
    sub?.current_period_end ? `Renews ${fmtDate(sub.current_period_end)}` : 'No renewal date',
  )

  const usage = state.usage
  if (usage?.calls) {
    const { used, included } = usage.calls
    setText('billing-calls-used', `${used} / ${included}`)
    setText('billing-calls-label', included ? `${Math.max(0, included - used)} calls remaining` : 'calls this period')

    const usageCard = document.getElementById('billing-usage-card')
    const usageBody = document.getElementById('billing-usage-body')
    if (usageCard && usageBody) {
      usageCard.style.display = ''
      const lines = [
        `Period: ${fmtDate(usage.period_start)} – ${fmtDate(usage.period_end)}`,
        `Calls: ${usage.calls.used} of ${usage.calls.included} (${usage.calls.percent}%)`,
      ]
      if (usage.whatsapp?.included) {
        lines.push(`WhatsApp: ${usage.whatsapp.used} of ${usage.whatsapp.included}`)
      }
      if (usage.estimated_overage_gbp > 0) {
        lines.push(`Estimated overage: ${fmtGbpPrecise(Math.round(usage.estimated_overage_gbp * 100))}`)
      }
      if (usage.warn_at_80) {
        lines.push('You have used 80% or more of an included allowance.')
      }
      usageBody.innerHTML = lines.map((line) => `<div>${escapeHtml(line)}</div>`).join('')
    }
  } else {
    setText('billing-calls-used', '—')
    setText('billing-calls-label', 'Usage not available yet')
  }

  const planEl = document.querySelector('.uplan')
  const email = planEl?.textContent?.includes('·') ? planEl.textContent.split('·').slice(1).join('·').trim() : ''
  if (planEl && plan?.name) {
    planEl.textContent = email ? `${plan.name} · ${email}` : `${plan.name} · Profile area`
  }
}

function renderInvoicesList() {
  const root = document.getElementById('billing-invoices-list')
  if (!root) return
  const rows = Array.isArray(state.invoices) ? state.invoices : []
  if (!rows.length) {
    root.innerHTML = '<div style="padding:12px;font-size:13px;color:var(--t3);">No invoices yet.</div>'
    return
  }
  root.innerHTML = rows
    .map((row, index) => {
      const number = row.invoice_number || row.external_invoice_id || row.id
      const date = fmtDate(row.created_at)
      const desc = row.description || 'Invoice'
      const amount = fmtGbpPrecise(row.amount_gbp_pence)
      const border = index === rows.length - 1 ? 'border:none' : ''
      return `<div class="qr" style="${border}" data-invoice-id="${escapeHtml(row.id)}">
        <span style="font-size:11px;color:var(--t3);min-width:88px;font-family:ui-monospace,monospace;">${escapeHtml(number)}</span>
        <span style="font-size:11px;color:var(--t3);min-width:72px;">${escapeHtml(date)}</span>
        <span style="font-size:12.5px;color:var(--t1);flex:1;">${escapeHtml(desc)}</span>
        <span style="font-size:13px;font-weight:700;color:var(--t1);">${escapeHtml(amount)}</span>
        <button class="btn bsm billing-invoice-pdf" type="button" data-invoice-id="${escapeHtml(row.id)}" data-invoice-number="${escapeHtml(number)}" style="margin-left:9px" title="Download PDF"><i class="ti ti-download"></i></button>
      </div>`
    })
    .join('')

  root.querySelectorAll('.billing-invoice-pdf').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-invoice-id')
      const number = btn.getAttribute('data-invoice-number') || id
      try {
        await downloadAuthenticatedFile(`/billing/invoices/${encodeURIComponent(id)}/pdf`, `invoice-${number}.pdf`)
      } catch (e) {
        const message = e?.message || 'Download failed'
        if (typeof window.toast === 'function') window.toast(message, 'tr')
        else window.alert(message)
      }
    })
  })
}

async function loadBillingData() {
  state.plansLoading = true
  state.plansError = ''
  renderPlanGrid('packages-plan-grid', purchaseSubscriptionPlan)
  renderPlanGrid('billing-plan-grid', purchaseSubscriptionPlan)

  try {
    const [plansRes, subRes, usageRes, optionsRes, invoicesRes] = await Promise.all([
      apiFetch('/billing/plans'),
      apiFetch('/billing/subscription').catch(() => null),
      apiFetch('/billing/usage-summary').catch(() => null),
      apiFetch('/billing/payment-options').catch(() => null),
      apiFetch('/billing/invoices').catch(() => []),
    ])

    state.plans = Array.isArray(plansRes) ? plansRes : []
    state.subscription = subRes
    state.currentPlan = subRes?.plan || null
    state.usage = usageRes?.usage || null
    state.paymentOptions = optionsRes || subRes?.payment_options || null
    state.invoices = Array.isArray(invoicesRes) ? invoicesRes : []
    state.plansError = ''
  } catch (e) {
    state.plans = []
    state.plansError = e?.message || 'Could not load subscription plans'
    logBilling('plans_load_failed', { message: state.plansError })
  } finally {
    state.plansLoading = false
  }
}

function purchaseSubscriptionPlan(plan) {
  if (state.busyPlanId) return

  if (state.currentPlan && plan.id === state.currentPlan.id) {
    return
  }

  if (!gocardlessAvailable()) {
    const msg = 'Online checkout is not available yet. Ask your admin to enable GoCardless in Integrations.'
    setCheckoutStatus('error', msg)
    if (typeof window.toast === 'function') window.toast(msg, 'tw')
    return
  }

  const label = planButtonLabel(plan, state.currentPlan)
  const confirmed = window.confirm(
    `${label}?\n\nYou will be redirected to GoCardless to set up your subscription payment.`,
  )
  if (!confirmed) return

  void startPlanPurchase(plan)
}

async function startPlanPurchase(plan) {
  if (state.busyPlanId) return

  state.busyPlanId = plan.id
  setCheckoutStatus('loading', `Starting GoCardless checkout for ${plan.name}…`)
  renderAll()

  try {
    await startGocardlessUpgrade(plan)
  } catch (e) {
    const message = e?.message || 'Could not start GoCardless checkout'
    state.busyPlanId = null
    setCheckoutStatus('error', message)
    logBilling('gocardless_start_failed', { planId: plan.id, message, status: e?.status })
    renderAll()
    if (typeof window.toast === 'function') window.toast(message, 'tr')
  }
}

function renderAll() {
  renderCheckoutStatus()
  renderPlanGrid('packages-plan-grid', purchaseSubscriptionPlan)
  renderPlanGrid('billing-plan-grid', purchaseSubscriptionPlan)
  renderBillingSummary()
  renderInvoicesList()
}

async function refreshBillingViews() {
  try {
    await loadBillingData()
    renderAll()
  } catch {
    /* keep last good render */
  }
}

export async function initBillingBridge(session) {
  if (!session) return

  state.subscription = session.subscription || null
  state.currentPlan = session.subscription?.plan || null

  await completeGocardlessReturn()
  await refreshBillingViews()

  if (typeof window.go === 'function' && !window.__billingGoWrapped) {
    const originalGo = window.go
    window.go = function wrappedGo(id, el) {
      originalGo(id, el)
      if (id === 'packages' || id === 'billing') refreshBillingViews()
    }
    window.__billingGoWrapped = true
  }
}
