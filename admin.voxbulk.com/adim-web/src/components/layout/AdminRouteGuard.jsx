import React from 'react'
import { useLocation } from 'react-router-dom'
import { useAdminProfile } from '../../context/AdminProfileContext'
import { canAccessAdminPath, defaultAdminHome, normalizeAdminRole } from '../../lib/adminPaths'

export default function AdminRouteGuard({ children }) {
  const location = useLocation()
  const { loading, error, reload, profile, adminRole } = useAdminProfile()

  if (loading) {
    return (
      <div className='card' style={{ margin: '24px auto', maxWidth: 540 }}>
        <div className='cardBody muted'>Loading profile…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className='card' style={{ margin: '24px auto', maxWidth: 560 }}>
        <div className='cardBody'>
          <h2 style={{ marginTop: 0 }}>Could not verify admin profile</h2>
          <p className='muted' style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>
            {error}
          </p>
          <div className='actions' style={{ marginTop: 12 }}>
            <button type='button' className='btn primary' onClick={() => reload?.()}>
              Retry
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!profile || profile.admin_access === false) {
    return (
      <div className='card' style={{ margin: '24px auto', maxWidth: 560 }}>
        <div className='cardBody'>
          <h2 style={{ marginTop: 0 }}>Admin access required</h2>
          <p className='muted'>Your session cannot use the platform admin console.</p>
        </div>
      </div>
    )
  }

  const r = normalizeAdminRole(adminRole || profile.admin_role)
  const ok = canAccessAdminPath(r, location.pathname)

  if (!ok) {
    const home = defaultAdminHome(r)
    return (
      <div className='card' style={{ margin: '24px auto', maxWidth: 640 }}>
        <div className='cardBody'>
          <h2 style={{ marginTop: 0 }}>Not authorised</h2>
          <p className='muted'>Your admin role ({r}) cannot open this area.</p>
          <div className='actions' style={{ marginTop: 12 }}>
            <button type='button' className='btn primary' onClick={() => (window.location.pathname = home)}>
              Go to your dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }

  return children
}
