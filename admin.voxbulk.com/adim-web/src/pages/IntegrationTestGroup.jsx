import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

export default function IntegrationTestGroup() {
  const [items, setItems] = useState([])
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [flash, setFlash] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await apiFetch('/admin/integration-testers')
      setItems(Array.isArray(res?.items) ? res.items : [])
    } catch (e) {
      setError(e?.message || 'Failed to load testers')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const add = async (e) => {
    e.preventDefault()
    const value = email.trim()
    if (!value) return
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/integration-testers', {
        method: 'POST',
        body: JSON.stringify({ email: value }),
      })
      setEmail('')
      setFlash('Tester added')
      window.setTimeout(() => setFlash(''), 3000)
      await load()
    } catch (err) {
      setError(err?.message || 'Could not add email')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id) => {
    setBusy(true)
    setError('')
    try {
      await apiFetch(`/admin/integration-testers/${id}`, { method: 'DELETE' })
      setFlash('Tester removed')
      window.setTimeout(() => setFlash(''), 3000)
      await load()
    } catch (err) {
      setError(err?.message || 'Could not remove')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='pageShell'>
      <div className='pageHead'>
        <div>
          <h1>Integration Test group</h1>
          <p className='muted'>
            Login emails that can see integrations set to <strong>Testing</strong> (dashboard tiles and linked FAQs).
            Live integrations are visible to everyone.
          </p>
        </div>
      </div>

      {flash ? <div className='note'>{flash}</div> : null}
      {error ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>{error}</div> : null}

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardBody'>
          <form onSubmit={add} style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
            <input
              className='input'
              type='email'
              placeholder='tester@example.com'
              value={email}
              onChange={(ev) => setEmail(ev.target.value)}
              style={{ minWidth: 260, flex: 1 }}
              disabled={busy}
            />
            <button type='submit' className='btn primary' disabled={busy || !email.trim()}>
              {busy ? 'Saving…' : 'Add email'}
            </button>
          </form>
        </div>
      </div>

      <div className='card'>
        <div className='cardHead'>
          <h3>Testers ({items.length})</h3>
          <button type='button' className='btn soft' onClick={() => void load()} disabled={loading || busy}>
            Refresh
          </button>
        </div>
        <div className='cardBody' style={{ padding: 0 }}>
          {loading ? (
            <div className='muted' style={{ padding: 16 }}>Loading…</div>
          ) : items.length === 0 ? (
            <div className='muted' style={{ padding: 16 }}>No tester emails yet.</div>
          ) : (
            <table className='table'>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Added</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.id}>
                    <td>{row.email}</td>
                    <td className='muted'>{row.created_at ? String(row.created_at).replace('T', ' ').slice(0, 19) : '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button type='button' className='btn soft' disabled={busy} onClick={() => void remove(row.id)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
