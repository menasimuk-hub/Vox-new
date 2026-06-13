import React, { useCallback, useEffect, useState } from 'react'
import {
  createAbuuDriver,
  deleteAbuuDriver,
  fetchAbuuDrivers,
  patchAbuuDriver,
} from '../../lib/abuuApi'

const EMPTY = { name: '', login_email: '', password: '', phone: '', is_available: true }

export default function AbuuDrivers() {
  const [rows, setRows] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [editing, setEditing] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

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
    setBusy('create')
    setError('')
    try {
      await createAbuuDriver(form)
      setForm(EMPTY)
      await load()
    } catch (err) {
      setError(err?.message || 'Create failed')
    } finally {
      setBusy('')
    }
  }

  const startEdit = (row) => {
    setEditing({
      id: row.id,
      name: row.name || '',
      login_email: row.login_email || '',
      phone: row.phone || '',
      is_available: row.is_available !== false,
      password: '',
    })
    setError('')
  }

  const saveEdit = async (e) => {
    e.preventDefault()
    if (!editing?.id) return
    setBusy(editing.id)
    setError('')
    try {
      const payload = {
        name: editing.name.trim(),
        login_email: editing.login_email.trim().toLowerCase(),
        phone: editing.phone.trim() || null,
        is_available: editing.is_available,
      }
      if (editing.password.trim()) {
        payload.password = editing.password
      }
      await patchAbuuDriver(editing.id, payload)
      setEditing(null)
      await load()
    } catch (err) {
      setError(err?.message || 'Update failed')
    } finally {
      setBusy('')
    }
  }

  const onDelete = async (row) => {
    if (!window.confirm(`Remove driver ${row.name}?`)) return
    setBusy(`del-${row.id}`)
    setError('')
    try {
      await deleteAbuuDriver(row.id)
      await load()
    } catch (err) {
      setError(err?.message || 'Delete failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className='card'>
      <div className='cardBody'>
        <p className='muted'>
          Drivers log in at <strong>driver.voxbulk.com</strong> with the email and password you set here.
        </p>
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
              minLength={6}
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
          <button type='submit' className='btn primary' disabled={busy === 'create'}>
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
                  <th>Available</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.name}</td>
                    <td>{row.login_email || '—'}</td>
                    <td>{row.phone || '—'}</td>
                    <td>{row.is_available ? 'Yes' : 'No'}</td>
                    <td className='tableActions'>
                      <button type='button' className='btn sm' onClick={() => startEdit(row)}>
                        Edit / reset password
                      </button>
                      <button
                        type='button'
                        className='btn sm'
                        disabled={busy === `del-${row.id}`}
                        onClick={() => onDelete(row)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {editing ? (
          <form className='formGrid card nested' style={{ marginTop: 20 }} onSubmit={saveEdit}>
            <h3 className='h3'>Edit driver</h3>
            <label>
              Name
              <input
                value={editing.name}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                required
              />
            </label>
            <label>
              Login email
              <input
                type='email'
                value={editing.login_email}
                onChange={(e) => setEditing({ ...editing, login_email: e.target.value })}
                required
              />
            </label>
            <label>
              New password (leave blank to keep current)
              <input
                type='password'
                value={editing.password}
                onChange={(e) => setEditing({ ...editing, password: e.target.value })}
                minLength={6}
                placeholder='Optional'
              />
            </label>
            <label>
              Phone
              <input
                value={editing.phone}
                onChange={(e) => setEditing({ ...editing, phone: e.target.value })}
              />
            </label>
            <label className='checkboxRow'>
              <input
                type='checkbox'
                checked={editing.is_available}
                onChange={(e) => setEditing({ ...editing, is_available: e.target.checked })}
              />
              Available for deliveries
            </label>
            <div className='formActions'>
              <button type='submit' className='btn primary' disabled={busy === editing.id}>
                Save changes
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
