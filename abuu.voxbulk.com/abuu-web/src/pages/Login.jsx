import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { loginRestaurant } from '../lib/api'

export default function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const onSubmit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await loginRestaurant(email.trim(), password)
      navigate('/orders')
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='main'>
      <div className='card'>
        <h1>Restaurant login</h1>
        <form className='form' onSubmit={onSubmit}>
          <label>
            Email
            <input type='email' value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            Password
            <input type='password' value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {error ? <p className='error'>{error}</p> : null}
          <button type='submit' className='btn primary' disabled={busy}>
            Sign in
          </button>
        </form>
      </div>
    </div>
  )
}
