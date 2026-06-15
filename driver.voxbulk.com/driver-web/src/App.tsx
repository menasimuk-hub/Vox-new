import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Login from './pages/Login'
import DriverConsole from './pages/DriverConsole'
import { getToken } from './lib/api'

function RequireAuth({ children }) {
  if (!getToken()) return <Navigate to='/login' replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path='/login' element={<Login />} />
      <Route
        path='/*'
        element={
          <RequireAuth>
            <DriverConsole />
          </RequireAuth>
        }
      />
    </Routes>
  )
}
