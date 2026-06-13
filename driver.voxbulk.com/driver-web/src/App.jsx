import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Assignments from './pages/Assignments'
import Login from './pages/Login'
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
        <Route index element={<Navigate to='/assignments' replace />} />
        <Route path='/assignments' element={<Assignments />} />
      </Route>
    </Routes>
  )
}
