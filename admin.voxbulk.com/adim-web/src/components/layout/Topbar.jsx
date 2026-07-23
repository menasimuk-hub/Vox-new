import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, adminLogoutRedirect } from '../../lib/api'
import { filterSidebarNav, normalizeAdminRole } from '../../lib/adminPaths'
import { NAV, searchAdminPages } from '../../lib/adminNav'
import { useAdminProfile } from '../../context/AdminProfileContext'

export default function Topbar({ dark, toggleTheme, onOpenMobile, collapsed, onToggleCollapse }) {
  const navigate = useNavigate()
  const wrapRef = useRef(null)
  const notifyRef = useRef(null)
  const searchRef = useRef(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [notifyOpen, setNotifyOpen] = useState(false)
  const [notifyCount, setNotifyCount] = useState(0)
  const [notifyItems, setNotifyItems] = useState([])
  const [notifyLoading, setNotifyLoading] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchIdx, setSearchIdx] = useState(0)
  const { loading, profile, adminRole } = useAdminProfile()
  const meEmail =
    loading ? 'Loading…' : profile?.email || (profile?.user_id ? `${String(profile.user_id).slice(0, 8)}…` : 'Admin')
  const roleLabel = normalizeAdminRole(adminRole || profile?.admin_role)
  const initials = String(meEmail).slice(0, 2).toUpperCase()

  const filteredNav = useMemo(() => filterSidebarNav(adminRole, NAV), [adminRole])
  const searchResults = useMemo(() => searchAdminPages(filteredNav, searchQ, 12), [filteredNav, searchQ])

  useEffect(() => {
    if (!menuOpen && !notifyOpen && !searchOpen) return
    const onDoc = (e) => {
      if (wrapRef.current && wrapRef.current.contains(e.target)) return
      if (notifyRef.current && notifyRef.current.contains(e.target)) return
      if (searchRef.current && searchRef.current.contains(e.target)) return
      setMenuOpen(false)
      setNotifyOpen(false)
      setSearchOpen(false)
    }
    document.addEventListener('click', onDoc)
    return () => document.removeEventListener('click', onDoc)
  }, [menuOpen, notifyOpen, searchOpen])

  const loadSummary = async () => {
    try {
      const res = await apiFetch('/admin/notifications/summary')
      setNotifyCount(Number(res?.total || 0))
    } catch {
      setNotifyCount(0)
    }
  }

  const loadFeed = async () => {
    setNotifyLoading(true)
    try {
      const res = await apiFetch('/admin/notifications?limit=20')
      setNotifyItems(Array.isArray(res?.items) ? res.items : [])
    } catch {
      setNotifyItems([])
    } finally {
      setNotifyLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (cancelled) return
      await loadSummary()
    }
    const defer = window.requestIdleCallback || ((fn) => window.setTimeout(fn, 1200))
    const idleId = defer(() => {
      void load()
    })
    const id = window.setInterval(load, 60_000)
    return () => {
      cancelled = true
      window.clearInterval(id)
      if (window.cancelIdleCallback && typeof idleId === 'number') {
        window.cancelIdleCallback(idleId)
      }
    }
  }, [])

  useEffect(() => {
    if (!notifyOpen) return
    void loadFeed()
    void loadSummary()
  }, [notifyOpen])

  useEffect(() => {
    setSearchIdx(0)
  }, [searchQ])

  const openNotify = () => {
    setMenuOpen(false)
    setSearchOpen(false)
    setNotifyOpen((v) => !v)
  }

  const clearTickets = async () => {
    setClearing(true)
    try {
      await apiFetch('/admin/notifications/clear-tickets', { method: 'POST' })
      await loadFeed()
      await loadSummary()
    } catch {
      /* keep panel open */
    } finally {
      setClearing(false)
    }
  }

  const goNotify = (item) => {
    setNotifyOpen(false)
    if (item?.href) navigate(item.href)
  }

  const goSearchResult = (page) => {
    if (!page?.path) return
    setSearchQ('')
    setSearchOpen(false)
    navigate(page.path)
  }

  const onSearchKeyDown = (e) => {
    if (!searchOpen && (e.key === 'ArrowDown' || e.key === 'Enter') && searchResults.length) {
      setSearchOpen(true)
    }
    if (e.key === 'Escape') {
      setSearchOpen(false)
      return
    }
    if (!searchResults.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSearchIdx((i) => Math.min(i + 1, searchResults.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSearchIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      goSearchResult(searchResults[searchIdx] || searchResults[0])
    }
  }

  const unreadTickets = notifyItems.filter((n) => n.kind === 'support_ticket').length

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

      <div className='admin-search' ref={searchRef}>
        <i className='ti ti-search' />
        <input
          placeholder='Search pages…'
          value={searchQ}
          onChange={(e) => {
            setSearchQ(e.target.value)
            setSearchOpen(true)
          }}
          onFocus={() => setSearchOpen(true)}
          onKeyDown={onSearchKeyDown}
          aria-label='Search admin pages'
          aria-autocomplete='list'
          aria-expanded={searchOpen && searchQ.trim().length > 0}
        />
        {searchOpen && searchQ.trim() ? (
          <div className='npanel search-results-panel'>
            <div className='np-hd'>
              <span className='np-t'>
                {searchResults.length ? `${searchResults.length} page${searchResults.length === 1 ? '' : 's'}` : 'No pages'}
              </span>
            </div>
            {searchResults.length ? (
              searchResults.map((page, i) => (
                <button
                  type='button'
                  key={`${page.path}-${page.label}`}
                  className={`nitem search-result-item ${i === searchIdx ? 'active' : ''}`}
                  onMouseEnter={() => setSearchIdx(i)}
                  onClick={() => goSearchResult(page)}
                >
                  <div className='nic' style={{ background: 'var(--s2)', color: 'var(--t2)' }}>
                    <i className='ti ti-file' />
                  </div>
                  <div>
                    <div className='nt'>{page.label}</div>
                    <div className='ns'>{page.group} · {page.path}</div>
                  </div>
                </button>
              ))
            ) : (
              <div className='nitem' style={{ cursor: 'default' }}>
                <div>
                  <div className='nt'>No matching pages</div>
                  <div className='ns'>Try another word (e.g. telnyx, user)</div>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>

      <div className='tb-r'>
        <div className='notifyWrap' ref={notifyRef} style={{ position: 'relative' }}>
          <button
            type='button'
            className='tbbtn nbell'
            aria-label='Notifications'
            title='Notifications'
            aria-expanded={notifyOpen}
            onClick={openNotify}
          >
            <i className='ti ti-bell' />
            {notifyCount > 0 ? <span className='ndot'>{notifyCount > 9 ? '9+' : notifyCount}</span> : null}
          </button>

          {notifyOpen ? (
            <div className='npanel notify-panel'>
              <div className='np-hd'>
                <span className='np-t'>Notifications</span>
                <div className='np-hd-actions'>
                  {notifyCount > 0 ? <span className='np-count'>{notifyCount} pending</span> : null}
                  {unreadTickets > 0 ? (
                    <button
                      type='button'
                      className='np-clear'
                      disabled={clearing}
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        void clearTickets()
                      }}
                    >
                      {clearing ? 'Clearing…' : 'Clear all'}
                    </button>
                  ) : null}
                </div>
              </div>
              {notifyLoading ? (
                <div className='nitem' style={{ cursor: 'default' }}>
                  <div className='nt'>Loading…</div>
                </div>
              ) : notifyItems.length === 0 ? (
                <div className='nitem' style={{ cursor: 'default' }}>
                  <div className='nt'>No pending notifications</div>
                  <div className='ns'>Billing requests and unread tickets appear here</div>
                </div>
              ) : (
                notifyItems.map((item) => (
                  <button
                    type='button'
                    key={item.id}
                    className='nitem'
                    style={{ width: '100%', border: 'none', background: 'transparent', textAlign: 'left' }}
                    onClick={() => goNotify(item)}
                  >
                    <div
                      className='nic'
                      style={{
                        background: item.kind === 'support_ticket' ? 'var(--bd)' : 'var(--gd)',
                        color: item.kind === 'support_ticket' ? 'var(--blu)' : 'var(--grn)',
                      }}
                    >
                      <i className={`ti ${item.kind === 'support_ticket' ? 'ti-lifebuoy' : 'ti-receipt'}`} />
                    </div>
                    <div>
                      <div className='nt'>{item.title}</div>
                      <div className='ns'>{item.subtitle}</div>
                    </div>
                  </button>
                ))
              )}
            </div>
          ) : null}
        </div>

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
            onClick={() => {
              setNotifyOpen(false)
              setSearchOpen(false)
              setMenuOpen((v) => !v)
            }}
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
