import React, { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

function money(minor, currency = 'GBP') {
  const n = Number(minor || 0) / 100
  const sym = currency === 'USD' ? '$' : currency === 'AUD' ? 'A$' : currency === 'CAD' ? 'C$' : '£'
  return `${sym}${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function Salesmen() {
  const [reps, setReps] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [expanded, setExpanded] = useState(null)
  const [detail, setDetail] = useState(null)

  const [form, setForm] = useState({ name: '', email: '', password: '', promo_code: '', country: '', caller_id: '' })

  const load = async () => {
    setLoading(true)
    setErr('')
    try {
      const res = await apiFetch('/admin/sales-reps')
      setReps(res?.items || [])
    } catch (e) {
      setErr(e?.message || 'Failed to load salesmen')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const create = async (e) => {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setMsg('')
    try {
      const res = await apiFetch('/admin/sales-reps', {
        method: 'POST',
        body: JSON.stringify({
          name: form.name.trim(),
          email: form.email.trim(),
          password: form.password,
          promo_code: form.promo_code.trim().toUpperCase(),
          country: form.country.trim().toUpperCase(),
          caller_id: form.caller_id.trim(),
        }),
      })
      setMsg(`Created salesman ${res?.rep?.email || form.email} with promo code ${res?.rep?.promo_code}. They sign in at the dashboard with this email + password.`)
      setForm({ name: '', email: '', password: '', promo_code: '', country: '', caller_id: '' })
      load()
    } catch (e2) {
      setErr(e2?.message || 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  const toggleActive = async (rep) => {
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !rep.is_active }) })
      load()
    } catch (e) {
      setErr(e?.message || 'Update failed')
    }
  }

  const openDetail = async (rep) => {
    if (expanded === rep.id) {
      setExpanded(null)
      setDetail(null)
      return
    }
    setExpanded(rep.id)
    setDetail(null)
    try {
      const [cust, dash] = await Promise.all([
        apiFetch(`/admin/sales-reps/${rep.id}/customers`),
        apiFetch(`/admin/sales-reps/${rep.id}/dashboard`),
      ])
      setDetail({ customers: cust?.items || [], stats: dash?.stats || null })
    } catch (e) {
      setDetail({ error: e?.message || 'Failed to load' })
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Salesmen</h1>
          <p>Create a salesman login and assign their promo code. They sign in to the dashboard and see only the Sales portal.</p>
        </div>
      </div>

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardHead'>
          <h3>Add salesman</h3>
          <span className='pill p-cyan'>Creates dashboard login</span>
        </div>
        <div className='cardBody'>
          {err ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.45)' }}>{err}</div> : null}
          {msg ? <div className='note'>{msg}</div> : null}
          <form onSubmit={create} className='stack' style={{ gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 12 }}>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Full name</label>
                <input className='input' value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder='Jane Smith' required />
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Email (login)</label>
                <input className='input' type='email' value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder='jane@voxbulk.com' required />
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Temporary password</label>
                <input className='input' type='password' value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder='Min 6 characters' minLength={6} required />
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Promo code (you type it)</label>
                <input className='input' style={{ textTransform: 'uppercase', fontFamily: 'ui-monospace, monospace' }} value={form.promo_code} onChange={(e) => setForm({ ...form, promo_code: e.target.value })} placeholder='UK4F2A' required />
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Country (ISO, optional)</label>
                <input className='input' style={{ textTransform: 'uppercase' }} value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} placeholder='GB' maxLength={2} />
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Demo caller ID (optional)</label>
                <input className='input' value={form.caller_id} onChange={(e) => setForm({ ...form, caller_id: e.target.value })} placeholder='+4420…' />
              </div>
            </div>
            <div className='actions'>
              <button className='btn primary' disabled={busy}>{busy ? 'Creating…' : 'Create salesman'}</button>
            </div>
          </form>
        </div>
      </div>

      <div className='card'>
        <div className='cardHead'>
          <h3>Salesmen ({reps.length})</h3>
          <button className='btn soft' onClick={load}>Refresh</button>
        </div>
        <div className='cardBody'>
          {loading ? (
            <div className='muted'>Loading…</div>
          ) : reps.length === 0 ? (
            <div className='muted'>No salesmen yet. Add one above.</div>
          ) : (
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Promo code</th>
                    <th>Customers</th>
                    <th>Commission</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {reps.map((r) => (
                    <React.Fragment key={r.id}>
                      <tr>
                        <td><strong>{r.name}</strong></td>
                        <td className='muted'>{r.email}</td>
                        <td style={{ fontFamily: 'ui-monospace, monospace' }}>{r.promo_code}</td>
                        <td>{r.customers ?? 0}</td>
                        <td>{money(r.commission_minor)}</td>
                        <td>
                          <span className={`pill ${r.is_active ? 'p-green' : 'p-amber'}`}>{r.is_active ? 'Active' : 'Disabled'}</span>
                        </td>
                        <td>
                          <div className='actions'>
                            <button className='btn soft' onClick={() => openDetail(r)}>{expanded === r.id ? 'Hide' : 'View'}</button>
                            <button className='btn soft' onClick={() => toggleActive(r)}>{r.is_active ? 'Disable' : 'Enable'}</button>
                          </div>
                        </td>
                      </tr>
                      {expanded === r.id ? (
                        <tr>
                          <td colSpan={7} style={{ background: 'rgba(0,0,0,0.02)' }}>
                            {!detail ? (
                              <div className='muted'>Loading…</div>
                            ) : detail.error ? (
                              <div className='note'>{detail.error}</div>
                            ) : (
                              <div className='stack' style={{ gap: 12 }}>
                                {detail.stats ? (
                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 12 }}>
                                    <div className='note'><div className='muted'>Won deals</div><strong>{detail.stats.won_deals.count}</strong></div>
                                    <div className='note'><div className='muted'>Active companies</div><strong>{detail.stats.wallet.active_companies}</strong></div>
                                    <div className='note'><div className='muted'>Revenue</div><strong>{money(detail.stats.wallet.revenue_minor)}</strong></div>
                                    <div className='note'><div className='muted'>Commission (pending)</div><strong>{money(detail.stats.wallet.commission_pending_minor)}</strong></div>
                                  </div>
                                ) : null}
                                <div>
                                  <strong>Customers ({detail.customers.length})</strong>
                                  {detail.customers.length === 0 ? (
                                    <div className='muted'>No customers added yet.</div>
                                  ) : (
                                    <table className='table' style={{ marginTop: 6 }}>
                                      <thead>
                                        <tr><th>Company</th><th>Contact</th><th>Mobile</th><th>Status</th><th>Converted org</th></tr>
                                      </thead>
                                      <tbody>
                                        {detail.customers.map((c) => (
                                          <tr key={c.id}>
                                            <td>{c.company_name || c.full_name}</td>
                                            <td className='muted'>{c.full_name}</td>
                                            <td className='muted'>{c.mobile || '—'}</td>
                                            <td><span className={`pill ${c.status === 'won' ? 'p-green' : c.status === 'contacted' ? 'p-cyan' : 'p-amber'}`}>{c.status}</span></td>
                                            <td className='muted'>{c.org_id ? 'Yes' : '—'}</td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  )}
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      ) : null}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
