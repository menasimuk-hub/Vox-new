import React, { useMemo } from 'react'
import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import LeadSalesPipelineStrip from '../components/LeadSalesPipelineStrip'

const TABS = [
  { to: '/marketing/leads/demos', label: 'Demos', stage: 'demo' },
  { to: '/marketing/leads/inbound', label: 'Inbound', stage: 'inbound' },
  { to: '/marketing/leads/tasks', label: 'Sales tasks', stage: 'sales' },
  { to: '/marketing/leads/offers', label: 'Offers', stage: 'offer' },
]

function stageFromPath(pathname) {
  if (pathname.includes('/leads/demos')) return 'demo'
  if (pathname.includes('/leads/inbound')) return 'inbound'
  if (pathname.includes('/leads/offers')) return 'offer'
  return 'sales'
}

export default function LeadsHub() {
  const { pathname } = useLocation()
  const active = useMemo(() => stageFromPath(pathname), [pathname])

  if (pathname === '/marketing/leads' || pathname === '/marketing/leads/') {
    return <Navigate to="/marketing/leads/tasks" replace />
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Leads &amp; sales</h1>
          <p>
            One pipeline: demo or inbound intake → sales call → offer. Open any stage below — task icons always land on
            Sales tasks with the same detail view.
          </p>
        </div>
      </div>

      <LeadSalesPipelineStrip active={active} />

      <div
        role="tablist"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 6,
          marginBottom: 16,
          padding: 4,
          borderRadius: 10,
          border: '1px solid var(--ds-border)',
          background: 'var(--ds-surface-secondary, #f8fafc)',
        }}
      >
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            role="tab"
            style={({ isActive }) => ({
              padding: '8px 14px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: isActive ? 600 : 450,
              textDecoration: 'none',
              color: isActive ? '#fff' : 'var(--ds-text-primary)',
              background: isActive ? 'var(--ds-primary, #1e6fd9)' : 'transparent',
            })}
          >
            {tab.label}
          </NavLink>
        ))}
      </div>

      <Outlet />
    </>
  )
}
