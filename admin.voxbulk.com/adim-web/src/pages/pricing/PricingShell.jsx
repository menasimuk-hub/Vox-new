import React from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { PricingSettingsProvider } from './pricingUtils'

const LINKS = [
  ['Packages', 'packages'],
  ['Private packages', 'private'],
  ['Top-up tiers', 'topups'],
  ['Invoice settings', 'invoice-settings'],
  ['Estimator', 'estimator'],
]

export default function PricingShell() {
  return (
    <div className="pricingShell">
      <header className="pricingShellHeader">
        <h1 className="pageTitle">Package pricing</h1>
        <p className="pricingShellIntro">
          One place for Core, Customer Feedback, Expo and Smart Card. Each Core package has its own AI, WA and ATS
          rates. Only the connection fee and usage-calculation rules are shared. Author in GBP — FX fills other markets.
        </p>
      </header>
      <nav className="pricingSubnav" aria-label="Pricing sections">
        {LINKS.map(([label, segment]) => (
          <NavLink
            key={segment}
            to={segment}
            end={segment === 'packages'}
            className={({ isActive }) => `pricingSubnavLink${isActive ? ' on' : ''}`}
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="pricingShellBody">
        <PricingSettingsProvider>
          <Outlet />
        </PricingSettingsProvider>
      </div>
    </div>
  )
}
