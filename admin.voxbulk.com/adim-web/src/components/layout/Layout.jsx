import React, { useEffect, useLayoutEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import AdminRouteGuard from './AdminRouteGuard'
import { AdminProfileProvider } from '../../context/AdminProfileContext'
import { adminLogoutRedirect, consumeAdminAuthHandoffFromHash, ensureAdminSession, getPublicAppOrigin } from '../../lib/api'

export default function Layout() {
  const [dark, setDark] = useState(() => localStorage.getItem('vb-admin-dark') === '1')
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('vb-admin-sb-collapsed') === '1')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [session, setSession] = useState({ status: 'loading', message: '' })

  useEffect(() => {
    document.body.classList.toggle('dark', dark)
    localStorage.setItem('vb-admin-dark', dark ? '1' : '0')
  }, [dark])

  useEffect(() => {
    localStorage.setItem('vb-admin-sb-collapsed', collapsed ? '1' : '0')
  }, [collapsed])

  useLayoutEffect(() => {
    consumeAdminAuthHandoffFromHash()
  }, [])

  useEffect(() => {
    let cancelled = false
    setSession({ status: 'loading', message: '' })
    ;(async () => {
      const s = await ensureAdminSession()
      if (cancelled) return
      setSession(s)
    })()
    return () => {
      cancelled = true
    }
  }, [])

  if (session.status !== 'ready') {
    const msg =
      session.status === 'loading'
        ? 'Loading admin session…'
        : session.message || 'Admin session required.'

    const publicOrigin = getPublicAppOrigin()
    const goSignIn = () => window.location.assign(`${publicOrigin}/signin`)

    return (
      <div className='auth-shell'>
        <div className='auth-card'>
          <h2>Admin access</h2>
          <p className='muted' style={{ whiteSpace: 'pre-wrap' }}>{msg}</p>
          {session.status !== 'loading' && (
            <div className='auth-actions'>
              <button type='button' className='btn btng' onClick={goSignIn}>
                Go to sign in
              </button>
              <button type='button' className='btn' onClick={() => adminLogoutRedirect()}>
                Clear session
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <AdminProfileProvider>
      <div className='app'>
        <div
          className={`sb-overlay ${mobileOpen ? 'on' : ''}`}
          onClick={() => setMobileOpen(false)}
          aria-hidden={!mobileOpen}
        />
        <Sidebar
          collapsed={collapsed}
          mobileOpen={mobileOpen}
          onToggleCollapse={() => setCollapsed((v) => !v)}
          onNavigate={() => setMobileOpen(false)}
        />
        <main className={`main ${collapsed ? 'expanded' : ''}`}>
          <Topbar
            dark={dark}
            toggleTheme={() => setDark((v) => !v)}
            onOpenMobile={() => setMobileOpen(true)}
            collapsed={collapsed}
            onToggleCollapse={() => setCollapsed(false)}
          />
          <div className='content'>
            <AdminRouteGuard>
              <Outlet />
            </AdminRouteGuard>
          </div>
        </main>
      </div>
    </AdminProfileProvider>
  )
}
