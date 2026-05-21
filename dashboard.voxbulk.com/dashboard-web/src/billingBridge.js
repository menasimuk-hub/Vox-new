import { apiFetch } from './lib/api.js'

const GC_FLOW_KEY = 'voxbulk_gc_redirect_flow_id'
const PLAN_ICONS = ['ti-rocket', 'ti-trending-up', 'ti-building-skyscraper']
const PLAN_ICON_CLASS = ['pig', 'pip', 'pia']

const state = {
  plans: [],
  subscription: null,
  currentPlan: null,
  usage: null,
  busyPlanId: null,
  paymentOptions: null,
}

function paymentOptions() {
  return state.paymentOptions || state.subscription?.payment_options || {}
}

function gocardlessAvailable() {
  return Boolean(paymentOptions().gocardless_available || state.subscription?.gocardless_checkout_available)
}

function cashAvailable() {
  return paymentOptions().cash_available !== false
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
    window.history.replaceState({}, '', url.pathname + url.search + url.hash)
  } catch {
    /* ignore */
  }
}

async function completeGocardlessReturn() {
  const billing = billingQueryParam('billing')
  if (billing === 'cancelled') {
    sessionStorage.removeItem(GC_FLOW_KEY)
    clearBillingQuery()
    if (typeof window.toast === 'function') window.toast('Payment setup cancelled.', 'tw')
    return
  }
  if (billing !== 'success') return

  const redirectFlowId = sessionStorage.getItem(GC_FLOW_KEY) || billingQueryParam('redirect_flow_id')
  sessionStorage.removeItem(GC_FLOW_KEY)
  clearBillingQuery()
  if (!redirectFlowId) {
    if (typeof window.toast === 'function') window.toast('Payment completed — refresh if your plan did not update.', 'tw')
    return
  }

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
    const planName = result?.plan?.name || 'your new plan'
    if (typeof window.toast === 'function') window.toast(`Subscription updated to ${planName}.`, 'tg')
  } catch (e) {
    const message = e?.message || 'Could not complete GoCardless checkout'
    if (typeof window.toast === 'function') window.toast(message, 'tr')
    else window.alert(message)
  }
}

async function startGocardlessUpgrade(plan) {
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
  if (!currentPlan) return `Choose ${plan.name}`
  if (plan.id === currentPlan.id) return 'Current plan'
  const oldPrice = Number(currentPlan.price_gbp_pence || 0)
  const newPrice = Number(plan.price_gbp_pence || 0)
  if (newPrice > oldPrice) return `Upgrade to ${plan.name}`
  if (newPrice < oldPrice) return `Downgrade to ${plan.name}`
  return 'Current plan'
}

function planButtonClass(plan, currentPlan) {
  if (!currentPlan || plan.id === currentPlan.id) return 'pbtn'
  const oldPrice = Number(currentPlan.price_gbp_pence || 0)
  const newPrice = Number(plan.price_gbp_pence || 0)
  return newPrice > oldPrice ? 'pbtn pg' : 'pbtn'
}

function renderPlanCard(plan, index, currentPlan, onSelect) {
  const isCurrent = currentPlan && plan.id === currentPlan.id
  const isFeatured = index === 1 && (state.plans?.length || 0) >= 2
  const features = parseFeatures(plan)
  const icon = PLAN_ICONS[index % PLAN_ICONS.length]
  const iconClass = PLAN_ICON_CLASS[index % PLAN_ICON_CLASS.length]
  const interval = plan.interval === 'year' ? '/yr' : '/mo'
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
    <button class="${planButtonClass(plan, currentPlan)}" type="button" ${isCurrent ? 'disabled' : ''}>
      ${escapeHtml(planButtonLabel(plan, currentPlan))}
    </button>
  `

  const btn = card.querySelector('button')
  if (btn && !isCurrent) {
    btn.disabled = Boolean(state.busyPlanId)
    btn.addEventListener('click', () => onSelect(plan))
  } else if (btn && state.busyPlanId) {
    btn.disabled = true
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
  const pending = state.subscription?.pending_plan
  setText('billing-plan-name', pending ? `${plan?.name || 'No plan'} (pending: ${pending.name})` : (plan?.name || 'No plan'))
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
  const orgName = document.querySelector('.unm')?.textContent || 'Your clinic'
  const email = planEl?.textContent?.includes('·') ? planEl.textContent.split('·').slice(1).join('·').trim() : ''
  if (planEl && plan?.name) {
    planEl.textContent = email ? `${plan.name} · ${email}` : `${plan.name} · Profile area`
  }
}

async function loadBillingData() {
  const [plansRes, subRes, usageRes, optionsRes] = await Promise.all([
    apiFetch('/billing/plans').catch(() => []),
    apiFetch('/billing/subscription').catch(() => null),
    apiFetch('/billing/usage-summary').catch(() => null),
    apiFetch('/billing/payment-options').catch(() => null),
  ])

  state.plans = Array.isArray(plansRes) ? plansRes : []
  state.subscription = subRes
  state.currentPlan = subRes?.plan || null
  state.usage = usageRes?.usage || null
  state.paymentOptions = optionsRes || subRes?.payment_options || null
}

function confirmPlanChange(plan) {
  const label = planButtonLabel(plan, state.currentPlan)
  const gc = gocardlessAvailable()
  const cash = cashAvailable()
  const pending = state.subscription?.pending_plan

  if (pending && pending.id === plan.id) {
    const msg = 'This plan change is already submitted and waiting for admin approval (cash payment).'
    if (typeof window.toast === 'function') window.toast(msg, 'tw')
    else window.alert(msg)
    return
  }

  if (gc && cash) {
    const useGc = window.confirm(
      `${label}?\n\nOK = Pay with GoCardless (sandbox, activates automatically)\nCancel = Pay cash (testing, admin approval required)`,
    )
    applyPlanChange(plan, useGc ? 'gocardless' : 'cash')
    return
  }

  if (gc) {
    applyPlanChange(plan, 'gocardless')
    return
  }

  const msg = `${label}? Cash payment requires admin approval before your plan changes.`
  if (typeof window.showConfirm === 'function') {
    window.showConfirm('Cash payment (testing)', msg, 'Submit for approval', () => applyPlanChange(plan, 'cash'))
    return
  }
  if (window.confirm(msg)) applyPlanChange(plan, 'cash')
}

async function applyPlanChange(plan, method = 'cash') {
  if (state.busyPlanId) return
  state.busyPlanId = plan.id
  renderAll()

  try {
    if (method === 'gocardless') {
      await startGocardlessUpgrade(plan)
      return
    }

    const result = await apiFetch('/billing/subscription/change-plan', {
      method: 'POST',
      body: JSON.stringify({ plan_id: plan.id }),
    })
    await loadBillingData()
    renderAll()

    const pendingName = result?.pending_plan?.name || plan.name
    const message = result?.awaiting_admin_approval
      ? `Cash payment submitted for ${pendingName}. An admin must approve before it activates.`
      : `Plan change submitted for ${pendingName}.`
    if (typeof window.toast === 'function') window.toast(message, 'tg')
  } catch (e) {
    const message = e?.message || 'Could not change plan'
    if (typeof window.toast === 'function') window.toast(message, 'tr')
    else window.alert(message)
  } finally {
    state.busyPlanId = null
    renderAll()
  }
}

function renderAll() {
  renderPlanGrid('packages-plan-grid', confirmPlanChange)
  renderPlanGrid('billing-plan-grid', confirmPlanChange)
  renderBillingSummary()
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
