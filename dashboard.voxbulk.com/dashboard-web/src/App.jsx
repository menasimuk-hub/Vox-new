import { useEffect, useRef } from 'react'
import bodyHtml from './bodyHtml.js'
import { logoutDashboard } from './lib/api.js'

function initialsFromName(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return String(name || 'VB').slice(0, 2).toUpperCase()
}

function App({ session }) {
  const scriptsRan = useRef(false)
  const profile = session?.profile || {}
  const org = session?.org || {}
  const subscription = session?.subscription || {}
  const onboarding = session?.onboarding || {}
  const orgName = org.name || org.display_name || profile.email || 'Your clinic'
  const planName = subscription?.plan?.name || subscription?.plan_name || 'Plan'
  const avatar = initialsFromName(orgName)

  useEffect(() => {
    if (scriptsRan.current) return
    scriptsRan.current = true

    import('./voxbulk.js?raw').then(({ default: jsCode }) => {
      const script = document.createElement('script')
      script.textContent = jsCode
      document.body.appendChild(script)

      window.__voxbulkLogout = logoutDashboard

      const logoutBtn = document.querySelector('.logout')
      logoutBtn?.addEventListener('click', logoutDashboard)

      const nameEl = document.querySelector('.unm')
      const planEl = document.querySelector('.uplan')
      const avatarEl = document.querySelector('.uav')
      if (nameEl) nameEl.textContent = orgName
      if (planEl) planEl.textContent = `${planName} · ${profile.email || 'Profile area'}`
      if (avatarEl) avatarEl.textContent = avatar

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

  const setupIncomplete = onboarding && onboarding.onboarding_complete === false

  return (
    <>
      {setupIncomplete ? (
        <div className="setup-banner">
          Account setup is not complete yet. Some features will stay in preview until onboarding is finished.
        </div>
      ) : null}
      <div
        style={{ minHeight: '100vh', width: '100%' }}
        dangerouslySetInnerHTML={{ __html: bodyHtml }}
      />
    </>
  )
}

export default App
