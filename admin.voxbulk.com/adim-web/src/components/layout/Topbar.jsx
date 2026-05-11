import React, { useEffect, useRef, useState } from 'react'
import { Search, Bell, TriangleAlert, Moon, Sun, LogOut } from 'lucide-react'
import { adminLogoutRedirect } from '../../lib/api'
import { normalizeAdminRole } from '../../lib/adminPaths'
import { useAdminProfile } from '../../context/AdminProfileContext'

export default function Topbar({ theme, toggleTheme }) {
  const wrapRef = useRef(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const { loading, profile, adminRole } = useAdminProfile()
  const meEmail =
    loading ? 'Loading…' : profile?.email || (profile?.user_id ? `${String(profile.user_id).slice(0, 8)}…` : 'Admin')
  const roleLabel = normalizeAdminRole(adminRole || profile?.admin_role)

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
      <div className='search'>
        <Search size={16}/>
        <input placeholder='Search organisations, invoices, jobs, users, tickets...' />
      </div>
      <div className='topbarRight'>
        <button type='button' className='iconBtn'><Bell size={17}/></button>
        <button type='button' className='iconBtn'><TriangleAlert size={17}/></button>
        <button type='button' className='iconBtn' onClick={toggleTheme}>
          {theme === 'dark' ? <Sun size={17}/> : <Moon size={17}/>}
        </button>
        <div className='userMenuWrap' ref={wrapRef} style={{ position: 'relative' }}>
          <button
            type='button'
            className='user userMenuTrigger'
            onClick={() => setMenuOpen((v) => !v)}
            style={{ border: '1px solid var(--border)', background: 'var(--surface)', cursor: 'pointer' }}
          >
            <div className='avatar'>A</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{meEmail}</div>
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>Platform role: {roleLabel}</div>
            </div>
            <span style={{ fontSize: 10, marginLeft: 4, opacity: 0.6 }}>▼</span>
          </button>
          {menuOpen && (
            <div
              className='userMenuDropdown'
              style={{
                position: 'absolute',
                right: 0,
                top: 'calc(100% + 6px)',
                minWidth: 200,
                background: 'var(--panel)',
                border: '1px solid var(--border)',
                borderRadius: 12,
                boxShadow: '0 12px 32px rgba(15,23,42,.12)',
                zIndex: 50,
              }}
            >
              <button
                type='button'
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  width: '100%',
                  padding: '10px 12px',
                  border: 'none',
                  background: 'transparent',
                  cursor: 'pointer',
                  fontSize: 13,
                  color: 'var(--heading)',
                  borderRadius: 12,
                }}
                onClick={() => adminLogoutRedirect()}
              >
                <LogOut size={16} /><span>Log out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
