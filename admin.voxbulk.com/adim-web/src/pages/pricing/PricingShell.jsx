import React from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { PricingSettingsProvider } from './pricingUtils'

const LINKS = [
  ['Packages', 'packages'],
  ['Private packages', 'private'],
  ['Currency rates', 'currency-rates'],
  ['Connection fee', 'connection-fee'],
  ['Service rates', 'services'],
  ['Top-up tiers', 'topups'],
  ['Invoice settings', 'invoice-settings'],
  ['Estimator', 'estimator'],
  ['Custom org', 'custom'],
]

export default function PricingShell() {
  return (
    <div className="pricingShell">
      <header className="pricingShellHeader">
        <h1 className="pageTitle">Core platform pricing</h1>
        <p className="pricingShellIntro">
          Packages for Core, Customer Feedback, and Expo. Author in GBP — other currencies sync from FX rates unless you set a market price by hand.
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
