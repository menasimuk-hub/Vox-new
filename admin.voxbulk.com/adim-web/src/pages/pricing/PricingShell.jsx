import React from 'react'
import { NavLink, Outlet } from 'react-router-dom'

const LINKS = [
  ['Plans', '/pricing/plans'],
  ['Connection fee', '/pricing/connection-fee'],
  ['Service rates', '/pricing/services'],
  ['Top-up tiers', '/pricing/topups'],
  ['FX rates', '/pricing/fx'],
  ['Estimator', '/pricing/estimator'],
  ['Custom org', '/pricing/custom'],
]

export default function PricingShell() {
  return (
    <div className="pricingShell">
      <header className="pricingShellHeader">
        <h1 className="pageTitle">VoxBulk pricing</h1>
        <p className="pricingShellIntro">
          Configure what customers see on the dashboard. Plans auto-calculate included minutes and surveys from monthly price ÷ unit rates.
          GoCardless checkout will connect here next.
        </p>
      </header>
      <nav className="pricingSubnav" aria-label="Pricing sections">
        {LINKS.map(([label, to]) => (
          <NavLink key={to} to={to} className={({ isActive }) => `pricingSubnavLink${isActive ? ' on' : ''}`}>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="pricingShellBody">
        <Outlet />
      </div>
    </div>
  )
}
