import React, { useCallback, useEffect, useState } from 'react'
import { fetchAbuuRestaurants, patchAbuuRestaurant } from '../../lib/abuuApi'

export default function AbuuRestaurants() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')
  const [editing, setEditing] = useState(null)

  const load = useCallback(async () => {
    const data = await fetchAbuuRestaurants({ limit: 100 })
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

  const startEdit = (row) => {
    setEditing({
      id: row.id,
      login_email: row.login_email || '',
      password: '',
    })
    setError('')
  }

  const savePortalLogin = async (e) => {
    e.preventDefault()
    if (!editing?.id) return
    if (!editing.login_email.trim()) {
      setError('Login email is required')
      return
    }
    if (!editing.password.trim()) {
      setError('Password is required (set a new portal password)')
      return
    }
    setBusyId(editing.id)
    setError('')
    try {
      await patchAbuuRestaurant(editing.id, {
        login_email: editing.login_email.trim().toLowerCase(),
        password: editing.password,
      })
      setEditing(null)
      await load()
    } catch (err) {
      setError(err?.message || 'Save failed')
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className='card'>
      <div className='cardBody'>
        <p className='muted'>
          Seeded restaurants have no portal login until you set one here. Use that email + password at{' '}
          <strong>abuu.voxbulk.com</strong>.
        </p>
        {error ? <p className='formError'>{error}</p> : null}
        {loading ? (
          <p className='muted'>Loading restaurants…</p>
        ) : (
          <div className='tableWrap'>
            <table className='table'>
              <thead>
                <tr>
                  <th>Name (EN)</th>
                  <th>Name (AR)</th>
                  <th>Status</th>
                  <th>Portal login</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.name_en}</td>
                    <td dir='rtl'>{row.name_ar}</td>
                    <td>{row.status}</td>
                    <td>
                      {row.login_email ? (
                        <>
                          {row.login_email}
                          {row.has_password ? ' ✓' : ''}
                        </>
                      ) : (
                        <span className='muted'>Not set</span>
                      )}
                    </td>
                    <td>
                      <button type='button' className='btn sm' onClick={() => startEdit(row)}>
                        {row.login_email ? 'Reset password' : 'Set portal login'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {editing ? (
          <form className='formGrid card nested' style={{ marginTop: 20 }} onSubmit={savePortalLogin}>
            <h3 className='h3'>Restaurant portal login</h3>
            <label>
              Login email (for abuu.voxbulk.com)
              <input
                type='email'
                value={editing.login_email}
                onChange={(e) => setEditing({ ...editing, login_email: e.target.value })}
                required
              />
            </label>
            <label>
              New password
              <input
                type='password'
                value={editing.password}
                onChange={(e) => setEditing({ ...editing, password: e.target.value })}
                required
                minLength={6}
                placeholder='Min 6 characters'
              />
            </label>
            <div className='formActions'>
              <button type='submit' className='btn primary' disabled={busyId === editing.id}>
                Save
              </button>
              <button type='button' className='btn' onClick={() => setEditing(null)}>
                Cancel
              </button>
            </div>
          </form>
        ) : null}
      </div>
    </div>
  )
}
