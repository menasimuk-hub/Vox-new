import React, { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { filterSidebarNav } from '../../lib/adminPaths'
import { GROUP_ICONS, GROUP_SECTION, NAV } from '../../lib/adminNav'
import { brandAssets } from '../../lib/brand'
import { useAdminProfile } from '../../context/AdminProfileContext'

function findGroupForPath(pathname, tree) {
  for (const [group, items] of tree) {
    if (items.some(([, path]) => path === pathname || (pathname.startsWith(`${path}/`) && path !== '/'))) {
      return group
    }
  }
  return null
}

function buildInitialOpen(pathname) {
  const activeGroup = findGroupForPath(pathname, NAV) || 'Dashboard'
  return Object.fromEntries(NAV.map(([name]) => [name, name === activeGroup]))
}

export default function Sidebar({ collapsed, mobileOpen, onToggleCollapse, onNavigate }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { adminRole } = useAdminProfile()

  const nav = useMemo(() => filterSidebarNav(adminRole, NAV), [adminRole])

  const [open, setOpen] = useState(() => buildInitialOpen(location.pathname))

  useEffect(() => {
    const activeGroup = findGroupForPath(location.pathname, nav)
    if (!activeGroup) return
    setOpen((prev) => ({ ...prev, [activeGroup]: true }))
  }, [location.pathname, nav])

  const toggleGroup = (group) => {
    setOpen((prev) => {
      const willOpen = !prev[group]
      if (!willOpen) return { ...prev, [group]: false }
      return Object.fromEntries(NAV.map(([name]) => [name, name === group]))
    })
  }

  const handleNavigate = (path) => {
    if (location.pathname !== path) navigate(path)
    onNavigate?.()
  }

  let lastSection = ''

  return (
    <aside className={`sb ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`} id='sb'>
      <div className='sb-logo'>
        <button
          type='button'
          className='sb-logo-btn'
          onClick={collapsed ? onToggleCollapse : undefined}
          aria-label={collapsed ? 'Expand sidebar' : 'VOXBULK Admin'}
          title={collapsed ? 'Show menu' : 'VOXBULK Admin'}
        >
          <img src={brandAssets.logoBlack} alt='VOXBULK' className='sb-logo-img logo-light sb-logo-full' />
          <img src={brandAssets.logoWhite} alt='VOXBULK' className='sb-logo-img logo-dark sb-logo-full' />
          <span className='sb-logo-icon' aria-hidden={!collapsed}>
            <img src={brandAssets.iconBlack} alt='' className='icon-light' />
            <img src={brandAssets.iconWhite} alt='' className='icon-dark' />
          </span>
        </button>
        {!collapsed ? (
          <button type='button' className='sb-toggle' onClick={onToggleCollapse} aria-label='Collapse sidebar'>
            <i className='ti ti-chevrons-left' />
          </button>
        ) : null}
      </div>

      <div className='sb-nav'>
        {nav.map(([group, items]) => {
          const isGroupActive = items.some(([, path]) => location.pathname === path || location.pathname.startsWith(`${path}/`))
          const icon = GROUP_ICONS[group] || 'ti-circle-dot'
          const section = GROUP_SECTION[group] || ''
          const showSection = section && section !== lastSection
          if (showSection) lastSection = section

          return (
            <div className='nav-group' key={group}>
              {showSection ? <div className='nav-sec'>{section}</div> : null}

              <button
                type='button'
                className={`ni ni-group ${open[group] ? 'open' : ''} ${isGroupActive ? 'has-active' : ''}`}
                onClick={() => toggleGroup(group)}
                aria-expanded={Boolean(open[group])}
              >
                <i className={`ti ${icon} nav-ic`} />
                <span className='ni-label'>{group}</span>
                <i className={`ti ti-chevron-down nav-chev ${open[group] ? 'open' : ''}`} />
                <span className='ni-tip'>{group}</span>
              </button>

              {open[group] ? (
                <div className='nav-children'>
                  {items.map(([label, path]) => {
                    const active = location.pathname === path || (path !== '/' && location.pathname.startsWith(`${path}/`))
                    return (
                      <button
                        type='button'
                        key={`${group}-${path}-${label}`}
                        className={`ni ni-sub ${active ? 'on' : ''}`}
                        onClick={() => handleNavigate(path)}
                      >
                        <span className='ni-sub-dot' aria-hidden='true' />
                        <span className='ni-label'>{label}</span>
                        <span className='ni-tip'>{label}</span>
                      </button>
                    )
                  })}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
