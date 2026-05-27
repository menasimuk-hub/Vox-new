import { getEnabledServices } from './servicesBridge.js'

function bindTogglePanel(toggleId, panelId) {
  const tog = document.getElementById(toggleId)
  const panel = document.getElementById(panelId)
  if (!tog || !panel) return
  const sync = () => {
    panel.hidden = !tog.classList.contains('on')
  }
  if (!tog.dataset.bound) {
    tog.dataset.bound = '1'
    tog.addEventListener('click', () => {
      setTimeout(sync, 0)
    })
  }
  sync()
}

export function applySystemSettingsMode() {
  const enabled = getEnabledServices()
  const clinic = document.getElementById('sys-clinic-booking')
  const interview = document.getElementById('sys-interview-integrations')
  const apiTab = document.querySelector('#pg-system .tbrow .tb[onclick*="api"]')

  if (enabled.interview && !enabled.recovery) {
    if (clinic) clinic.style.display = 'none'
    if (interview) interview.style.display = ''
    if (apiTab) apiTab.classList.add('on')
    document.querySelectorAll('#pg-system .tbrow .tb').forEach((t) => {
      if (t !== apiTab) t.classList.remove('on')
    })
    document.querySelectorAll('#pg-system .tpcont').forEach((p) => p.classList.remove('on'))
    document.getElementById('stp-api')?.classList.add('on')
    bindTogglePanel('sys-tog-calendly', 'sys-panel-calendly')
    bindTogglePanel('sys-tog-cronofy', 'sys-panel-cronofy')
    bindTogglePanel('sys-tog-zoom', 'sys-panel-zoom')
    return
  }

  if (clinic) clinic.style.display = ''
  if (interview) interview.style.display = enabled.interview ? '' : 'none'
}

export function initSystemSettingsBridge() {
  window.applySystemSettingsMode = applySystemSettingsMode
  applySystemSettingsMode()
  document.getElementById('sys-test-calendly')?.addEventListener('click', () => {
    if (typeof window.startCalendlyOAuth === 'function') void window.startCalendlyOAuth()
    else window.toast?.('Calendly OAuth not available', 'tr')
  })
  document.getElementById('sys-test-cronofy')?.addEventListener('click', () => {
    if (typeof window.startCronofyOAuth === 'function') void window.startCronofyOAuth()
    else window.toast?.('Cronofy OAuth not available', 'tr')
  })
  document.getElementById('sys-test-zoom')?.addEventListener('click', () => {
    const key = document.getElementById('sys-zoom-api-key')?.value?.trim()
    if (!key) {
      window.toast?.('Enter a Zoom API key or secret first', 'tr')
      return
    }
    window.toast?.('Zoom API saved locally — full validation coming in Phase 5', 'tg')
  })
}
