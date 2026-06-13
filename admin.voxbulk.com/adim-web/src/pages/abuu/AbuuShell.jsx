import React from 'react'
import { NavLink, Outlet } from 'react-router-dom'

const LINKS = [
  ['Orders', 'orders'],
  ['Menus', 'menus'],
  ['Restaurants', 'restaurants'],
  ['Drivers', 'drivers'],
  ['Customers', 'customers'],
]

export default function AbuuShell() {
  return (
    <div className='pageShell'>
      <header className='pageTop'>
        <div>
          <h1 className='pageTitle'>Abuu food delivery</h1>
          <p className='muted'>Platform admin — restaurants, orders, drivers, and manual payment.</p>
        </div>
      </header>
      <nav className='pricingSubnav' aria-label='Abuu sections'>
        {LINKS.map(([label, segment]) => (
          <NavLink
            key={segment}
            to={segment}
            end={segment === 'orders'}
            className={({ isActive }) => `pricingSubnavLink${isActive ? ' on' : ''}`}
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  )
}
