import { useEffect, useRef } from 'react'
import bodyHtml from './bodyHtml.js'
import { logoutDashboard } from './lib/api.js'
import { setClientSession } from './clientContext.js'

function initialsFromName(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return String(name || 'VB').slice(0, 2).toUpperCase()
}

function App({ session }) {
  const voxbulkUiLoaded = useRef(false)
  const profile = session?.profile || {}
  const org = session?.org || {}
  const subscription = session?.subscription || {}
  const orgName = org.name || org.display_name || profile.email || 'Your clinic'
  const planName = subscription?.plan?.name || subscription?.plan_name || 'Plan'
  const avatar = initialsFromName(orgName)

  useEffect(() => {
    setClientSession(session)
  }, [session])

  useEffect(() => {
    window.__voxbulkLogout = logoutDashboard

    function onLogoutActivate(event) {
      const logoutEl = event.target.closest?.('#dashboard-logout, .sb-bot .logout')
      if (!logoutEl) return
      event.preventDefault()
      event.stopPropagation()
      logoutDashboard()
    }

    function onLogoutKeydown(event) {
      if (event.key !== 'Enter' && event.key !== ' ') return
      const logoutEl = event.target.closest?.('#dashboard-logout, .sb-bot .logout')
      if (!logoutEl) return
      event.preventDefault()
      logoutDashboard()
    }

    document.addEventListener('click', onLogoutActivate)
    document.addEventListener('keydown', onLogoutKeydown)

    return () => {
      document.removeEventListener('click', onLogoutActivate)
      document.removeEventListener('keydown', onLogoutKeydown)
      delete window.__voxbulkLogout
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function bootDashboardUi() {
      if (!voxbulkUiLoaded.current) {
        voxbulkUiLoaded.current = true
        const { default: jsCode } = await import('./voxbulk.js?raw')
        const script = document.createElement('script')
        script.textContent = jsCode
        document.body.appendChild(script)
      }

      if (cancelled) return

      const { initModalBridge } = await import('./modalBridge.js')
      initModalBridge()

      const { initInterviewHubBridge } = await import('./interviewHubBridge.js')
      initInterviewHubBridge()

      const { initServiceOrdersBridge } = await import('./serviceOrdersBridge.js')
      initServiceOrdersBridge()

      const { initSurveyHubBridge } = await import('./surveyHubBridge.js')
      initSurveyHubBridge()

      const { initDashboardBridge } = await import('./dashboardBridge.js')
      initDashboardBridge()

      const { initProfileBridge } = await import('./profileBridge.js')
      initProfileBridge(session)

      const { initBillingBridge } = await import('./billingBridge.js')
      initBillingBridge(session)

      const { initSurveyPricingBridge } = await import('./surveyPricingBridge.js')
      initSurveyPricingBridge()

      const { initSurveyResultsBridge } = await import('./surveyResultsBridge.js')
      initSurveyResultsBridge()

      const { initInterviewReportsBridge } = await import('./interviewReportsBridge.js')
      initInterviewReportsBridge()

      const nameEl = document.querySelector('.unm')
      const planEl = document.querySelector('.uplan')
      const avatarEl = document.querySelector('.uav')
      if (nameEl) nameEl.textContent = orgName
      if (planEl) planEl.textContent = `${planName} · ${profile.email || 'Profile area'}`
      if (avatarEl) avatarEl.textContent = avatar
    }

    void bootDashboardUi()

    return () => {
      cancelled = true
    }
  }, [avatar, orgName, planName, profile.email, session])

  useEffect(() => {
    const overlay = document.getElementById('sb-overlay')
    const sb = document.getElementById('sb')

    function openMobileSidebar() {
      sb?.classList.add('mobile-open')
      overlay?.classList.add('on')
    }
    function closeMobileSidebar() {
      sb?.classList.remove('mobile-open')
      overlay?.classList.remove('on')
    }

    document.getElementById('mob-ham')?.addEventListener('click', openMobileSidebar)
    overlay?.addEventListener('click', closeMobileSidebar)

    sb?.querySelectorAll('.ni').forEach((ni) => {
      ni.addEventListener('click', () => {
        if (window.innerWidth <= 768) closeMobileSidebar()
      })
    })
  }, [avatar, orgName, planName, profile.email])

  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      const topbar = document.querySelector('.topbar')
      if (topbar && !document.getElementById('mob-ham')) {
        const ham = document.createElement('button')
        ham.id = 'mob-ham'
        ham.className = 'mob-ham'
        ham.innerHTML = '<i class="ti ti-menu-2"></i>'
        topbar.insertBefore(ham, topbar.firstChild)
      }

      if (!document.getElementById('sb-overlay')) {
        const overlay = document.createElement('div')
        overlay.id = 'sb-overlay'
        overlay.className = 'sb-overlay'
        document.body.appendChild(overlay)
      }
    })
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <div
      style={{ minHeight: '100vh', width: '100%' }}
      dangerouslySetInnerHTML={{ __html: bodyHtml }}
    />
  )
}

export default App
