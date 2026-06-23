import React, { Suspense, useEffect, useLayoutEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import AdminRouteGuard from './AdminRouteGuard'
import PageLoader from '../PageLoader'
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
    const mq = window.matchMedia('(min-width: 769px)')
    const closeIfDesktop = () => {
      if (mq.matches) setMobileOpen(false)
    }
    closeIfDesktop()
    mq.addEventListener('change', closeIfDesktop)
    return () => mq.removeEventListener('change', closeIfDesktop)
  }, [])

  useEffect(() => {
    if (!mobileOpen) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') setMobileOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mobileOpen])

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

  if (session.status === 'loading') {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <p className="muted">Loading admin session…</p>
        </div>
      </div>
    )
  }

  if (session.status === 'none' || session.status === 'blocked') {
    const msg = session.message || (session.status === 'blocked' ? 'Admin access required.' : 'Sign in to continue.')
    const publicOrigin = getPublicAppOrigin()
    const goSignIn = () => window.location.assign(`${publicOrigin}/signin`)

    return (
      <div className='auth-shell'>
        <div className='auth-card'>
          <h2>Admin access</h2>
          <p className='muted'>{msg}</p>
          <div className='auth-actions'>
            <button type='button' className='btn btng' onClick={goSignIn}>
              Go to sign in
            </button>
            <button type='button' className='btn' onClick={() => adminLogoutRedirect()}>
              Clear session
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <AdminProfileProvider initialProfile={session.profile || null}>
      <div className='app'>
        <div
          className={`sb-overlay ${mobileOpen ? 'on' : ''}`}
          onClick={() => setMobileOpen(false)}
          aria-hidden={!mobileOpen}
        />
        <Sidebar
          dark={dark}
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
              <Suspense fallback={<PageLoader />}>
                <Outlet />
              </Suspense>
            </AdminRouteGuard>
          </div>
        </main>
      </div>
    </AdminProfileProvider>
  )
}
