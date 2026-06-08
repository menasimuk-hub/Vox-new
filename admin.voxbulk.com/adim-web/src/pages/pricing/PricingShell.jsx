import React from 'react'

import { NavLink, Outlet } from 'react-router-dom'

import { PricingSettingsProvider } from './pricingUtils'



const LINKS = [

  ['Plans', 'plans'],

  ['Connection fee', 'connection-fee'],

  ['Service rates', 'services'],

  ['Top-up tiers', 'topups'],

  ['FX rates', 'fx'],

  ['Estimator', 'estimator'],

  ['Custom org', 'custom'],

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

        {LINKS.map(([label, segment]) => (

          <NavLink

            key={segment}

            to={segment}

            end={segment === 'plans'}

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

