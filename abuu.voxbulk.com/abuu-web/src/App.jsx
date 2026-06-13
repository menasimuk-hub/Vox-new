import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Login from './pages/Login'
import Menu from './pages/Menu'
import Orders from './pages/Orders'
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
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to='/orders' replace />} />
        <Route path='/orders' element={<Orders />} />
        <Route path='/menu' element={<Menu />} />
      </Route>
    </Routes>
  )
}
