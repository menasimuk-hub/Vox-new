import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'

export default function Organisations() {
  const navigate = useNavigate()
  const [items, setItems] = useState(null)
  const [listError, setListError] = useState('')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async (q) => {
    setListError('')
    let cancelled = false
    try {
      const qs = new URLSearchParams()
      if (q && String(q).trim()) qs.set('search', String(q).trim())
      qs.set('limit', '200')
      const data = await apiFetch(`/admin/organisations?${qs.toString()}`)
      if (!cancelled) setItems(Array.isArray(data) ? data : [])
    } catch (e) {
      if (!cancelled) {
        setItems([])
        setListError(e?.message || 'Could not load organisations')
      }
    }
    return () => {
      cancelled = true
    }
  }

  useEffect(() => {
    let cancelled = false
    setListError('')
    setBusy(true)
    ;(async () => {
      try {
        const qs = new URLSearchParams()
        if (search && search.trim()) qs.set('search', search.trim())
        qs.set('limit', '200')
        const data = await apiFetch(`/admin/organisations?${qs.toString()}`)
        if (!cancelled) setItems(Array.isArray(data) ? data : [])
      } catch (e) {
        if (!cancelled) {
          setItems([])
          setListError(e?.message || 'Could not load organisations')
        }
      } finally {
        if (!cancelled) setBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [search])

  const createOrg = async () => {
    const name = window.prompt('Organisation / clinic name?')
    if (!name) return
    try {
      const created = await apiFetch('/admin/organisations', {
        method: 'POST',
        body: JSON.stringify({ name: String(name).trim() }),
      })
      localStorage.setItem('retover_admin_selected_org_id', created.id)
      navigate('/organisations/profile')
    } catch (e) {
      window.alert(e?.message || 'Could not create organisation')
    }
  }

  return (
    <>
      {listError && (
        <div className='card' style={{ marginBottom: 16, borderColor: '#fecaca' }}>
          <div className='cardBody' style={{ color: '#b91c1c', fontSize: 14 }}>{listError}</div>
        </div>
      )}
      <div className='pageTop'>
        <div>
          <h1>All organisations</h1>
          <p>Manage organisations, categories, contacts, and suspension state.</p>
        </div>
        <div className='actions'>
          <button className='btn' onClick={() => load(search)} disabled={busy}>
            Refresh
          </button>
          <button className='btn primary' onClick={createOrg}>New organisation</button>
        </div>
      </div>
      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardBody'>
          <div className='filters'>
            <input
              className='input'
              placeholder='Search organisations…'
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className='card'>
        <div className='cardHead'>
          <h3>Organisation list</h3>
          <span className='pill p-cyan'>{items ? `${items.length}` : '—'}</span>
        </div>
        <div className='cardBody'>
          <div className='tableWrap'>
            <table className='table'>
              <thead>
                <tr>
                  <th>Organisation</th>
                  <th>Category</th>
                  <th>Plan</th>
                  <th>Status</th>
                  <th>Contact</th>
                  <th>Users</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {(items || []).map((o) => (
                  <tr key={o.id}>
                    <td>
                      <div style={{ display: 'grid' }}>
                        <strong>{o.name}</strong>
                        <span className='muted' style={{ fontSize: 12 }}>
                          {o.city || o.country ? `${o.city || ''}${o.city && o.country ? ', ' : ''}${o.country || ''}` : '—'}
                        </span>
                      </div>
                    </td>
                    <td>{o.category_name || '—'}</td>
                    <td>{o.plan_name || o.plan_code || '—'}</td>
                    <td>
                      {o.is_suspended ? <span className='pill p-amber'>Suspended</span> : <span className='pill p-green'>Active</span>}
                    </td>
                    <td>{o.contact_email || o.contact_name || '—'}</td>
                    <td>{o.user_count} users</td>
                    <td>
                      <button
                        className='btn soft'
                        onClick={() => {
                          localStorage.setItem('retover_admin_selected_org_id', o.id)
                          navigate('/organisations/profile')
                        }}
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
                {!items && (
                  <tr>
                    <td colSpan={7}>Loading…</td>
                  </tr>
                )}
                {items && items.length === 0 && (
                  <tr>
                    <td colSpan={7}>No organisations found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  )
}
