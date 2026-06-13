import React from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { setToken } from '../lib/api'

export default function Layout() {
  const navigate = useNavigate()

  const logout = () => {
    setToken('')
    navigate('/login')
  }

  return (
    <div className='shell'>
      <header className='topbar'>
        <strong>Abuu Driver</strong>
        <button type='button' className='btn' onClick={logout}>
          Logout
        </button>
      </header>
      <main className='main'>
        <Outlet />
      </main>
    </div>
  )
}
