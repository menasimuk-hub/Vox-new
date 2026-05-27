import { apiFetch } from './lib/api.js'

const DEFAULT_SERVICES = {
  interview: true,
  survey: true,
  recovery: false,
  follow_up: false,
}

export const servicesState = {
  interview: true,
  survey: true,
  recovery: false,
  follow_up: false,
  loaded: false,
}

const NAV_PAGE_SERVICES = {
  dashboard: null,
  services: null,
  'interviews-create': 'interview',
  interviews: 'interview',
  'results-i': 'interview',
  'reports-interview': 'interview',
  'surveys-create': 'survey',
  surveys: 'survey',
  'survey-detail': 'survey',
  'results-s': 'survey',
  'reports-survey': 'survey',
  queue: 'recovery',
  noshow: 'recovery',
  emergency: 'recovery',
  recall: 'recovery',
  offers: 'recovery',
  reminders: 'follow_up',
  profile: null,
  system: null,
  team: null,
  optout: null,
  audit: null,
  packages: null,
  billing: null,
  support: null,
}

function isEnabled(key) {
  return Boolean(servicesState[key])
}

export function getEnabledServices() {
  return { ...servicesState }
}

export async function loadEnabledServices() {
  try {
    const org = await apiFetch('/organisations/me')
    const raw = org?.enabled_services || {}
    servicesState.interview = raw.interview !== false
    servicesState.survey = raw.survey !== false
    servicesState.recovery = Boolean(raw.recovery)
    servicesState.follow_up = Boolean(raw.follow_up)
  } catch {
    Object.assign(servicesState, DEFAULT_SERVICES)
  }
  servicesState.loaded = true
  applyServicesNav()
  if (typeof window.applyDashboardServices === 'function') {
    window.applyDashboardServices()
  }
  return getEnabledServices()
}

export async function saveEnabledServices(patch) {
  const body = {}
  ;['interview', 'survey', 'recovery', 'follow_up'].forEach((key) => {
    if (patch[key] !== undefined) body[key] = Boolean(patch[key])
  })
  const result = await apiFetch('/organisations/me/enabled-services', {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
  const next = result?.enabled_services || {}
  servicesState.interview = Boolean(next.interview)
  servicesState.survey = Boolean(next.survey)
  servicesState.recovery = Boolean(next.recovery)
  servicesState.follow_up = Boolean(next.follow_up)
  applyServicesNav()
  if (typeof window.applyDashboardServices === 'function') {
    window.applyDashboardServices()
  }
  return getEnabledServices()
}

function setGroupVisible(groupId, visible) {
  const el = document.querySelector(`[data-nav-group="${groupId}"]`)
  if (el) el.style.display = visible ? '' : 'none'
}

function applyServicesNav() {
  setGroupVisible('interview', isEnabled('interview'))
  setGroupVisible('survey', isEnabled('survey'))
  setGroupVisible('recovery', isEnabled('recovery'))
  setGroupVisible('follow_up', isEnabled('follow_up'))
}

export function isPageAllowed(pageId) {
  const need = NAV_PAGE_SERVICES[pageId]
  if (!need) return true
  return isEnabled(need)
}

export function handleNavIntent(pageId) {
  if (pageId === 'interviews-create') {
    window.__voxNavIntent = { action: 'create-interview' }
    if (typeof window.go === 'function') window.go('interviews', null)
    return true
  }
  if (pageId === 'surveys-create') {
    window.__voxNavIntent = { action: 'create-survey' }
    if (typeof window.go === 'function') window.go('surveys', null)
    return true
  }
  if (!isPageAllowed(pageId)) {
    window.toast?.('Enable this service under Profile → Services', 'tr')
    if (typeof window.go === 'function') window.go('services', null)
    return true
  }
  if (pageId === 'services') {
    syncServicesToggles()
  }
  if (typeof window.go === 'function') window.go(pageId, null)
  return true
}

function bindNavGroups() {
  document.querySelectorAll('[data-nav-group-toggle]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      const group = btn.closest('[data-nav-group]')
      if (!group) return
      group.classList.toggle('collapsed')
    })
  })

  document.querySelectorAll('[data-nav-go]').forEach((el) => {
    el.addEventListener('click', (e) => {
      e.stopPropagation()
      const page = el.getAttribute('data-nav-go')
      if (page) handleNavIntent(page)
    })
  })
}

function bindServicesForm() {
  const saveBtn = document.getElementById('svc-save-btn')
  if (!saveBtn || saveBtn.dataset.bound) return
  saveBtn.dataset.bound = '1'
  saveBtn.addEventListener('click', async () => {
    const read = (id) => document.getElementById(id)?.classList.contains('on')
    try {
      await saveEnabledServices({
        interview: read('svc-tog-interview'),
        survey: read('svc-tog-survey'),
        recovery: read('svc-tog-recovery'),
        follow_up: read('svc-tog-followup'),
      })
      window.toast?.('Services updated', 'tg')
    } catch (e) {
      window.toast?.(e.message || 'Could not save services', 'tr')
    }
  })
}

function syncServicesToggles() {
  const set = (id, on) => {
    const el = document.getElementById(id)
    if (!el) return
    el.classList.toggle('on', on)
    el.classList.toggle('off', !on)
  }
  set('svc-tog-interview', isEnabled('interview'))
  set('svc-tog-survey', isEnabled('survey'))
  set('svc-tog-recovery', isEnabled('recovery'))
  set('svc-tog-followup', isEnabled('follow_up'))
}

export function initServicesBridge() {
  window.goNav = handleNavIntent
  bindNavGroups()
  bindServicesForm()
  void loadEnabledServices().then(() => syncServicesToggles())
}
