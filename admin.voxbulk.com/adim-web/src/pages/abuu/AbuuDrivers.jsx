import React, { useCallback, useEffect, useState } from 'react'
import { createAbuuDriver, fetchAbuuDrivers } from '../../lib/abuuApi'

const EMPTY = { name: '', login_email: '', password: '', phone: '', is_available: true }

export default function AbuuDrivers() {
  const [rows, setRows] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const data = await fetchAbuuDrivers({ limit: 100 })
    setRows(Array.isArray(data) ? data : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const onCreate = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await createAbuuDriver(form)
      setForm(EMPTY)
      await load()
    } catch (err) {
      setError(err?.message || 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='card'>
      <div className='cardBody'>
        <form className='formGrid' onSubmit={onCreate}>
          <h2 className='h3'>Add driver</h2>
          <label>
            Name
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label>
            Login email
            <input
              type='email'
              value={form.login_email}
              onChange={(e) => setForm({ ...form, login_email: e.target.value })}
              required
            />
          </label>
          <label>
            Password
            <input
              type='password'
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </label>
          <label>
            Phone
            <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </label>
          <label className='checkboxRow'>
            <input
              type='checkbox'
              checked={form.is_available}
              onChange={(e) => setForm({ ...form, is_available: e.target.checked })}
            />
            Available
          </label>
          <button type='submit' className='btn primary' disabled={busy}>
            Create driver
          </button>
        </form>
        {error ? <p className='formError'>{error}</p> : null}
        {loading ? (
          <p className='muted'>Loading drivers…</p>
        ) : (
          <div className='tableWrap' style={{ marginTop: 24 }}>
            <table className='table'>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Phone</th>
                  <th>Status</th>
                  <th>Available</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.name}</td>
                    <td>{row.login_email || '—'}</td>
                    <td>{row.phone || '—'}</td>
                    <td>{row.status}</td>
                    <td>{row.is_available ? 'Yes' : 'No'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
