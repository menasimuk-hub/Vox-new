import React, { useEffect, useLayoutEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import AdminRouteGuard from './AdminRouteGuard'
import { AdminProfileProvider } from '../../context/AdminProfileContext'
import { adminLogoutRedirect, consumeAdminAuthHandoffFromHash, ensureAdminSession, getPublicAppOrigin } from '../../lib/api'

export default function Layout() {
  const [theme, setTheme] = useState('light')
  const [session, setSession] = useState({ status: 'loading', message: '' })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

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
      <div className='layout'>
        <main className='main' style={{ padding: 24 }}>
          <div className='content'>
            <div className='card' style={{ maxWidth: 720, margin: '48px auto' }}>
              <div className='cardBody'>
                <h2 style={{ marginTop: 0 }}>Admin access</h2>
                <p className='muted' style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>
                  {msg}
                </p>
                {session.status !== 'loading' && (
                  <div className='actions' style={{ marginTop: 14, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <button type='button' className='btn primary' onClick={goSignIn}>
                      Go to sign in
                    </button>
                    <button type='button' className='btn soft' onClick={() => adminLogoutRedirect()}>
                      Clear session
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    )
  }

  return (
    <AdminProfileProvider>
      <div className='layout'>
        <Sidebar />
        <main className='main'>
          <Topbar theme={theme} toggleTheme={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))} />
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
