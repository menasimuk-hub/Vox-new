import { apiFetch } from './lib/api.js'

const LOG_PREFIX = '[survey-pricing]'

const state = {
  loading: false,
  loaded: false,
  error: '',
  catalog: null,
  selected: null,
}

function log(event, detail = {}) {
  console.info(LOG_PREFIX, event, detail)
}

function fmtGbp(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(2)}`
}

function perContact(pence, size) {
  const n = Number(size || 0)
  if (!n) return '—'
  return fmtGbp(Number(pence || 0) / n)
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function channelMeta(channel) {
  if (channel === 'whatsapp') {
    return {
      key: 'whatsapp',
      title: 'WhatsApp surveys',
      icon: 'ti-brand-whatsapp',
      iconClass: 'isWhatsApp',
      blurb: 'Outbound WhatsApp survey messages with full response tracking.',
    }
  }
  return {
    key: 'ai_call',
    title: 'AI phone surveys',
    icon: 'ti-phone',
    iconClass: 'isAiCall',
    blurb: 'AI calls each contact with your approved script and transcripts.',
  }
}

export function getSurveyPackagesCatalog() {
  return state.catalog
}

export function getSelectedSurveyPackage() {
  return state.selected
}

export async function fetchSurveyPackages(force = false) {
  if (state.loaded && !force && state.catalog) return state.catalog
  state.loading = true
  state.error = ''
  log('fetch_start')
  try {
    const data = await apiFetch('/service-orders/survey-packages')
    state.catalog = data || null
    state.loaded = true
    log('fetch_ok', {
      ai_call: data?.packages?.ai_call?.length || 0,
      whatsapp: data?.packages?.whatsapp?.length || 0,
      setup_fee_pence: data?.setup_fee_pence || 0,
    })
    return state.catalog
  } catch (e) {
    state.error = e?.message || 'Could not load survey packages'
    state.catalog = null
    log('fetch_failed', { message: state.error })
    throw e
  } finally {
    state.loading = false
  }
}

function renderPackageCard(pkg, channel) {
  const size = Number(pkg.bundle_size || 0)
  const price = fmtGbp(pkg.bundle_price_pence)
  const each = perContact(pkg.bundle_price_pence, size)
  const overage = pkg.overage_unit_price_pence != null ? fmtGbp(pkg.overage_unit_price_pence) : null
  const isSelected =
    state.selected &&
    state.selected.id === pkg.id &&
    state.selected.channel === channel

  return `
    <article class="survey-pkg-card${isSelected ? ' isSelected' : ''}" data-package-id="${escapeHtml(pkg.id)}" data-channel="${escapeHtml(channel)}">
      <div class="survey-pkg-size">${size}</div>
      <div class="survey-pkg-unit">contacts</div>
      <div class="survey-pkg-name">${escapeHtml(pkg.label || `${size} contacts`)}</div>
      <div class="survey-pkg-price">${price}</div>
      <div class="survey-pkg-each">${each} each</div>
      ${overage ? `<div class="survey-pkg-overage">+ ${overage} / extra contact</div>` : ''}
      <button type="button" class="survey-pkg-btn${isSelected ? ' isSelected' : ''}" data-package-id="${escapeHtml(pkg.id)}" data-channel="${escapeHtml(channel)}">
        ${isSelected ? 'Selected' : 'Select package'}
      </button>
    </article>
  `
}

function renderChannelSection(channel, packages) {
  const meta = channelMeta(channel)
  const list = Array.isArray(packages) ? packages : []
  const gridClass = list.length >= 4 ? 'survey-pkg-grid isWide' : 'survey-pkg-grid'

  return `
    <section class="survey-pkg-channel" data-channel="${meta.key}">
      <div class="survey-pkg-channelHead">
        <div class="survey-pkg-channelIcon ${meta.iconClass}"><i class="ti ${meta.icon}"></i></div>
        <div>
          <h3>${meta.title}</h3>
          <p>${meta.blurb}</p>
        </div>
      </div>
      ${
        list.length
          ? `<div class="${gridClass}">${list.map((pkg) => renderPackageCard(pkg, channel)).join('')}</div>`
          : `<div class="survey-pkg-empty muted">No ${meta.title.toLowerCase()} packages available right now.</div>`
      }
    </section>
  `
}

function bindPackageSelection(root) {
  if (!root) return
  root.querySelectorAll('.survey-pkg-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      const id = btn.getAttribute('data-package-id')
      const channel = btn.getAttribute('data-channel')
      const packages = state.catalog?.packages?.[channel] || []
      const pkg = packages.find((row) => String(row.id) === String(id))
      if (!pkg) return

      state.selected = { ...pkg, channel }
      log('package_selected', { id, channel, label: pkg.label })
      renderPackagesPage()
      renderSurveysPricingSummary()

      if (typeof window.toast === 'function') {
        window.toast(`${pkg.label} selected for ${channel === 'whatsapp' ? 'WhatsApp' : 'AI call'}`, 'tg')
      }
    })
  })
}

export function renderPackagesPage() {
  const root = document.getElementById('survey-packages-section')
  if (!root) return

  if (state.loading) {
    root.innerHTML = '<div class="survey-pkg-loading muted">Loading survey packages…</div>'
    return
  }

  if (state.error) {
    root.innerHTML = `
      <div class="survey-pkg-error">
        <p>${escapeHtml(state.error)}</p>
        <button type="button" class="btn soft bsm" id="survey-packages-retry">Retry</button>
      </div>
    `
    root.querySelector('#survey-packages-retry')?.addEventListener('click', () => {
      void loadAndRender(true)
    })
    return
  }

  const catalog = state.catalog
  if (!catalog) {
    root.innerHTML = '<div class="survey-pkg-empty muted">Survey pricing is not available yet.</div>'
    return
  }

  const setupFee = Number(catalog.setup_fee_pence || 0)
  const setupNote = document.getElementById('packages-survey-setup-note')
  if (setupNote) {
    setupNote.textContent =
      setupFee > 0
        ? `${fmtGbp(setupFee)} setup fee per survey order · Extra contacts billed at package overage rate`
        : 'Pay per survey campaign · Extra contacts billed at package overage rate'
  }

  root.innerHTML = `
    <div class="survey-pkg-shell">
      <div class="survey-pkg-intro">
        <h2>Survey packages — pay as you go</h2>
        <p class="muted">Prices are managed by your admin team and update automatically here.</p>
        ${setupFee > 0 ? `<div class="survey-pkg-setup"><i class="ti ti-receipt"></i> Setup fee: <strong>${fmtGbp(setupFee)}</strong> per order</div>` : ''}
      </div>
      ${renderChannelSection('ai_call', catalog.packages?.ai_call)}
      ${renderChannelSection('whatsapp', catalog.packages?.whatsapp)}
    </div>
  `

  bindPackageSelection(root)
}

export function renderSurveysPricingSummary() {
  const root = document.getElementById('sur-pricing-summary')
  if (!root) return

  if (state.loading) {
    root.innerHTML = '<div class="survey-pkg-summary muted">Loading survey pricing…</div>'
    return
  }

  if (state.error || !state.catalog) {
    root.innerHTML = ''
    return
  }

  const ai = state.catalog.packages?.ai_call || []
  const wa = state.catalog.packages?.whatsapp || []
  const setupFee = Number(state.catalog.setup_fee_pence || 0)

  const miniCards = (channel, packages) =>
    packages
      .slice(0, 3)
      .map(
        (pkg) => `
        <button type="button" class="survey-pkg-mini${state.selected?.id === pkg.id ? ' isSelected' : ''}" data-package-id="${escapeHtml(pkg.id)}" data-channel="${escapeHtml(channel)}">
          <span>${Number(pkg.bundle_size || 0)} contacts</span>
          <strong>${fmtGbp(pkg.bundle_price_pence)}</strong>
        </button>
      `,
      )
      .join('')

  root.innerHTML = `
    <div class="survey-pkg-summary">
      <div class="survey-pkg-summaryHead">
        <strong>Survey pricing</strong>
        <a href="#" class="survey-pkg-summaryLink" id="sur-pricing-view-all">View all packages</a>
      </div>
      ${setupFee > 0 ? `<div class="survey-pkg-summarySetup muted">${fmtGbp(setupFee)} setup fee per order</div>` : ''}
      <div class="survey-pkg-summaryBlock">
        <span class="survey-pkg-summaryLabel"><i class="ti ti-phone"></i> AI call</span>
        <div class="survey-pkg-miniRow">${miniCards('ai_call', ai) || '<span class="muted">No packages</span>'}</div>
      </div>
      <div class="survey-pkg-summaryBlock">
        <span class="survey-pkg-summaryLabel"><i class="ti ti-brand-whatsapp"></i> WhatsApp</span>
        <div class="survey-pkg-miniRow">${miniCards('whatsapp', wa) || '<span class="muted">No packages</span>'}</div>
      </div>
      ${
        state.selected
          ? `<div class="survey-pkg-summarySelected">Selected: <strong>${escapeHtml(state.selected.label)}</strong> · ${state.selected.channel === 'whatsapp' ? 'WhatsApp' : 'AI call'}</div>`
          : ''
      }
    </div>
  `

  root.querySelector('#sur-pricing-view-all')?.addEventListener('click', (e) => {
    e.preventDefault()
    if (typeof window.go === 'function') window.go('packages')
  })

  root.querySelectorAll('.survey-pkg-mini').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-package-id')
      const channel = btn.getAttribute('data-channel')
      const packages = state.catalog?.packages?.[channel] || []
      const pkg = packages.find((row) => String(row.id) === String(id))
      if (!pkg) return
      state.selected = { ...pkg, channel }
      log('package_selected', { id, channel, source: 'surveys_summary' })
      renderSurveysPricingSummary()
      renderPackagesPage()
    })
  })
}

async function loadAndRender(force = false) {
  try {
    await fetchSurveyPackages(force)
  } catch {
    /* state.error set */
  }
  renderPackagesPage()
  renderSurveysPricingSummary()
}

export async function initSurveyPricingBridge() {
  log('init')
  await loadAndRender(false)

  if (typeof window.go === 'function' && !window.__surveyPricingGoWrapped) {
    const originalGo = window.go
    window.go = function wrappedGoForSurveyPricing(id, el) {
      originalGo(id, el)
      if (id === 'packages' || id === 'surveys') {
        if (!state.loaded && !state.loading) void loadAndRender(false)
        else {
          renderPackagesPage()
          renderSurveysPricingSummary()
        }
      }
    }
    window.__surveyPricingGoWrapped = true
  }

  window.getSurveyPackagesCatalog = getSurveyPackagesCatalog
  window.getSelectedSurveyPackage = getSelectedSurveyPackage
}
