import React, { useEffect, useRef, useState } from 'react'
import { adminLogoutRedirect } from '../../lib/api'
import { normalizeAdminRole } from '../../lib/adminPaths'
import { useAdminProfile } from '../../context/AdminProfileContext'

export default function Topbar({ dark, toggleTheme, onOpenMobile, collapsed, onToggleCollapse }) {
  const wrapRef = useRef(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const { loading, profile, adminRole } = useAdminProfile()
  const meEmail =
    loading ? 'Loading…' : profile?.email || (profile?.user_id ? `${String(profile.user_id).slice(0, 8)}…` : 'Admin')
  const roleLabel = normalizeAdminRole(adminRole || profile?.admin_role)
  const initials = String(meEmail).slice(0, 2).toUpperCase()

  useEffect(() => {
    if (!menuOpen) return
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setMenuOpen(false)
    }
    document.addEventListener('click', onDoc)
    return () => document.removeEventListener('click', onDoc)
  }, [menuOpen])

  return (
    <div className='topbar'>
      {collapsed ? (
        <button
          type='button'
          className='tb-sb-toggle'
          onClick={onToggleCollapse}
          aria-label='Show sidebar'
          title='Show menu'
        >
          <i className='ti ti-layout-sidebar-left-expand' />
        </button>
      ) : null}

      <button type='button' className='mob-ham' onClick={onOpenMobile} aria-label='Open menu'>
        <i className='ti ti-menu-2' />
      </button>

      <div className='tb-info'>
        <div className='tb-title'>Admin Console</div>
        <div className='tb-sub'>Platform management · {roleLabel}</div>
      </div>

      <div className='admin-search'>
        <i className='ti ti-search' />
        <input placeholder='Search organisations, invoices, jobs, users, tickets…' />
      </div>

      <div className='tb-r'>
        <span className='api-pill'>
          <span className='api-dot ldot' />
          API connected
        </span>

        <button type='button' className='tbbtn nbell' aria-label='Notifications'>
          <i className='ti ti-bell' />
          <span className='ndot' />
        </button>

        <button type='button' className='tbbtn' aria-label='Alerts'>
          <i className='ti ti-alert-triangle' />
        </button>

        <button type='button' className='tbbtn' onClick={toggleTheme} aria-label='Toggle theme'>
          <i className={`ti ${dark ? 'ti-sun' : 'ti-moon'}`} />
        </button>

        <div className='userMenuWrap' ref={wrapRef} style={{ position: 'relative' }}>
          <button
            type='button'
            className='user-row userMenuTrigger'
            onClick={() => setMenuOpen((v) => !v)}
            style={{ margin: 0, border: 'none', background: 'transparent', width: 'auto' }}
          >
            <div className='uav'>{initials}</div>
            <div className='u-info'>
              <div className='unm'>{meEmail}</div>
              <div className='uplan'>{roleLabel}</div>
            </div>
            <i className='ti ti-chevron-down' style={{ fontSize: 14, color: 'var(--t3)', flexShrink: 0 }} />
          </button>

          {menuOpen ? (
            <div className='npanel userMenuDropdown'>
              <div className='np-hd'>
                <span className='np-t'>Account</span>
              </div>
              <button
                type='button'
                className='nitem'
                style={{ width: '100%', border: 'none', background: 'transparent', textAlign: 'left' }}
                onClick={() => adminLogoutRedirect()}
              >
                <div className='nic' style={{ background: 'var(--rd)', color: 'var(--red)' }}>
                  <i className='ti ti-logout' />
                </div>
                <div>
                  <div className='nt'>Log out</div>
                  <div className='ns'>Return to sign in</div>
                </div>
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
