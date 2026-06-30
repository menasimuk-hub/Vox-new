import React, { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'
import './orgControlCenter.css'

function money(minor, currency = 'GBP') {
  const n = Number(minor || 0) / 100
  const sym = currency === 'USD' ? '$' : currency === 'AUD' ? 'A$' : currency === 'CAD' ? 'C$' : '£'
  return `${sym}${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function Modal({ title, onClose, children, wide }) {
  return (
    <div className='occ-modal-overlay open' role='presentation' onClick={onClose}>
      <div
        className='occ-modal'
        role='dialog'
        style={wide ? { maxWidth: 900, width: '92vw' } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div className='occ-modal-head'>
          <h3>{title}</h3>
          <button type='button' className='occ-modal-close' onClick={onClose}>×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

const EMPTY_FORM = { name: '', email: '', password: '', promo_code: '', country: '', caller_id: '' }
const PROMO_CODE_RE = /^[A-Z0-9]{4,12}$/
const SALESMAN_EMAIL_DOMAIN = 'voxbulk.com'

// Suggest the next free salesman{N}@voxbulk.com based on existing reps.
function nextSalesmanEmail(reps) {
  let max = 0
  for (const r of reps || []) {
    const m = /^salesman(\d+)@voxbulk\.com$/i.exec(String(r?.email || '').trim())
    if (m) max = Math.max(max, parseInt(m[1], 10))
  }
  return `salesman${max + 1}@${SALESMAN_EMAIL_DOMAIN}`
}

export default function Salesmen() {
  const [reps, setReps] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState(EMPTY_FORM)
  const [createErr, setCreateErr] = useState('')

  const [editRep, setEditRep] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', promo_code: '', country: '', caller_id: '' })

  const [pwRep, setPwRep] = useState(null)
  const [pwValue, setPwValue] = useState('')

  const [profileRep, setProfileRep] = useState(null)
  const [profile, setProfile] = useState(null)

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
    setCreateErr('')
    setMsg('')

    const name = createForm.name.trim()
    const email = createForm.email.trim().toLowerCase()
    const password = createForm.password
    const promoCode = createForm.promo_code.replace(/[^A-Za-z0-9]/g, '').toUpperCase()

    if (!name) {
      setCreateErr('Full name is required.')
      setBusy(false)
      return
    }
    if (!email || !email.includes('@')) {
      setCreateErr('A valid email is required.')
      setBusy(false)
      return
    }
    if (!password || password.length < 6) {
      setCreateErr('Password must be at least 6 characters.')
      setBusy(false)
      return
    }
    if (!PROMO_CODE_RE.test(promoCode)) {
      setCreateErr('Promo code must be 4–12 letters or numbers (e.g. UK4F2A).')
      setBusy(false)
      return
    }

    try {
      const res = await apiFetch('/admin/sales-reps', {
        method: 'POST',
        body: JSON.stringify({
          name,
          email,
          password,
          promo_code: promoCode,
          country: createForm.country.trim().toUpperCase(),
          caller_id: createForm.caller_id.trim(),
        }),
      })
      setMsg(`Created ${res?.rep?.email || email} · promo code ${res?.rep?.promo_code || promoCode}. They sign in at the dashboard with this email + password.`)
      setCreateForm(EMPTY_FORM)
      setCreateErr('')
      setShowCreate(false)
      load()
    } catch (e2) {
      const message = e2?.message || 'Create failed'
      setCreateErr(message)
      setErr(message)
    } finally {
      setBusy(false)
    }
  }

  const openEdit = (rep) => {
    setEditRep(rep)
    setEditForm({
      name: rep.name || '',
      promo_code: rep.promo_code || '',
      country: rep.country || '',
      caller_id: rep.caller_id || '',
    })
  }

  const saveEdit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setMsg('')
    try {
      await apiFetch(`/admin/sales-reps/${editRep.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: editForm.name.trim(),
          promo_code: editForm.promo_code.trim().toUpperCase(),
          country: editForm.country.trim().toUpperCase(),
          caller_id: editForm.caller_id.trim(),
        }),
      })
      setMsg(`Updated ${editForm.name || editRep.email}.`)
      setEditRep(null)
      load()
    } catch (e2) {
      setErr(e2?.message || 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  const savePassword = async (e) => {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setMsg('')
    try {
      await apiFetch(`/admin/sales-reps/${pwRep.id}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({ password: pwValue }),
      })
      setMsg(`Password reset for ${pwRep.name || pwRep.email}.`)
      setPwRep(null)
      setPwValue('')
    } catch (e2) {
      setErr(e2?.message || 'Reset failed')
    } finally {
      setBusy(false)
    }
  }

  const toggleActive = async (rep) => {
    setErr('')
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !rep.is_active }) })
      load()
    } catch (e) {
      setErr(e?.message || 'Update failed')
    }
  }

  const remove = async (rep) => {
    if (!window.confirm(`Delete salesman ${rep.name || rep.email}? Their login is disabled and their pipeline records are removed.`)) return
    setErr('')
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, { method: 'DELETE' })
      setMsg(`Deleted ${rep.name || rep.email}.`)
      load()
    } catch (e) {
      setErr(e?.message || 'Delete failed')
    }
  }

  const openProfile = async (rep) => {
    setProfileRep(rep)
    setProfile(null)
    try {
      const [cust, dash] = await Promise.all([
        apiFetch(`/admin/sales-reps/${rep.id}/customers`),
        apiFetch(`/admin/sales-reps/${rep.id}/dashboard`),
      ])
      setProfile({ customers: cust?.items || [], stats: dash?.stats || null, sample: false })
    } catch (e) {
      setProfile({ customers: [], stats: null, sample: false })
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Salesmen</h1>
          <p>Field reps who sign in to the dashboard and see only the Sales portal. Create a login, assign their promo code, and track their pipeline.</p>
        </div>
        <div className='actions'>
          <button className='btn soft' onClick={load}>Refresh</button>
          <button className='btn primary' onClick={() => { setErr(''); setMsg(''); setCreateErr(''); setCreateForm({ ...EMPTY_FORM, email: nextSalesmanEmail(reps) }); setShowCreate(true) }}>
            + Create salesman
          </button>
        </div>
      </div>

      {err ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.45)', marginBottom: 12 }}>{err}</div> : null}
      {msg ? <div className='note' style={{ marginBottom: 12 }}>{msg}</div> : null}

      <div className='card'>
        <div className='cardHead'>
          <h3>Salesmen ({reps.length})</h3>
        </div>
        <div className='cardBody'>
          {loading ? (
            <div className='muted'>Loading…</div>
          ) : reps.length === 0 ? (
            <div className='muted'>No salesmen yet. Click <strong>Create salesman</strong> to add one.</div>
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
                    <th style={{ width: 1 }} />
                  </tr>
                </thead>
                <tbody>
                  {reps.map((r) => (
                    <tr key={r.id}>
                      <td><strong>{r.name}</strong></td>
                      <td className='muted'>{r.email}</td>
                      <td style={{ fontFamily: 'ui-monospace, monospace' }}>{r.promo_code}</td>
                      <td>{r.customers ?? 0}</td>
                      <td>{money(r.commission_minor)}</td>
                      <td>
                        <span className={`pill ${r.is_active ? 'p-green' : 'p-amber'}`}>{r.is_active ? 'Active' : 'Disabled'}</span>
                      </td>
                      <td>
                        <div className='actions' style={{ flexWrap: 'nowrap', justifyContent: 'flex-end' }}>
                          <button className='btn soft' onClick={() => openProfile(r)}>Profile</button>
                          <button className='btn soft' onClick={() => openEdit(r)}>Edit</button>
                          <button className='btn soft' onClick={() => { setErr(''); setMsg(''); setPwValue(''); setPwRep(r) }}>Reset password</button>
                          <button className='btn soft' onClick={() => toggleActive(r)}>{r.is_active ? 'Disable' : 'Enable'}</button>
                          <button className='btn soft' style={{ color: '#dc2626' }} onClick={() => remove(r)}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {showCreate ? (
        <Modal title='Create salesman' onClose={() => { if (!busy) { setShowCreate(false); setCreateErr('') } }}>
          <form onSubmit={create} noValidate>
            <div className='occ-modal-body' style={{ display: 'grid', gap: 12 }}>
              <p className='muted' style={{ margin: 0 }}>Creates a dashboard login. The salesman signs in with this email + password and sees only the Sales portal.</p>
              {createErr ? (
                <div className='note' style={{ borderColor: 'rgba(220,38,38,0.45)', margin: 0 }} role='alert'>
                  {createErr}
                </div>
              ) : null}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 12 }}>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Full name</span>
                  <input className='input' value={createForm.name} onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })} placeholder='Jane Smith' required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Email (login)</span>
                  <input className='input' type='email' value={createForm.email} onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })} placeholder='jane@voxbulk.com' required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Temporary password</span>
                  <input className='input' type='password' value={createForm.password} onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })} placeholder='Min 6 characters' minLength={6} required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Promo code (you type it)</span>
                  <input className='input' style={{ textTransform: 'uppercase', fontFamily: 'ui-monospace, monospace' }} value={createForm.promo_code} onChange={(e) => setCreateForm({ ...createForm, promo_code: e.target.value })} placeholder='UK4F2A' required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Country (ISO, optional)</span>
                  <input className='input' style={{ textTransform: 'uppercase' }} value={createForm.country} onChange={(e) => setCreateForm({ ...createForm, country: e.target.value })} placeholder='GB' maxLength={2} />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Demo caller ID (optional)</span>
                  <input className='input' value={createForm.caller_id} onChange={(e) => setCreateForm({ ...createForm, caller_id: e.target.value })} placeholder='+4420…' />
                </label>
              </div>
            </div>
            <div className='occ-modal-foot'>
              <button type='button' className='btn soft' onClick={() => setShowCreate(false)} disabled={busy}>Cancel</button>
              <button type='submit' className='btn primary' disabled={busy}>{busy ? 'Creating…' : 'Create salesman'}</button>
            </div>
          </form>
        </Modal>
      ) : null}

      {editRep ? (
        <Modal title={`Edit ${editRep.name || editRep.email}`} onClose={() => setEditRep(null)}>
          <form onSubmit={saveEdit}>
            <div className='occ-modal-body' style={{ display: 'grid', gap: 12 }}>
              <div className='muted' style={{ fontSize: 12 }}>{editRep.email}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 12 }}>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Full name</span>
                  <input className='input' value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Promo code</span>
                  <input className='input' style={{ textTransform: 'uppercase', fontFamily: 'ui-monospace, monospace' }} value={editForm.promo_code} onChange={(e) => setEditForm({ ...editForm, promo_code: e.target.value })} required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Country (ISO)</span>
                  <input className='input' style={{ textTransform: 'uppercase' }} value={editForm.country} onChange={(e) => setEditForm({ ...editForm, country: e.target.value })} maxLength={2} />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Demo caller ID</span>
                  <input className='input' value={editForm.caller_id} onChange={(e) => setEditForm({ ...editForm, caller_id: e.target.value })} placeholder='+4420…' />
                </label>
              </div>
            </div>
            <div className='occ-modal-foot'>
              <button type='button' className='btn soft' onClick={() => setEditRep(null)} disabled={busy}>Cancel</button>
              <button type='submit' className='btn primary' disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button>
            </div>
          </form>
        </Modal>
      ) : null}

      {pwRep ? (
        <Modal title={`Reset password — ${pwRep.name || pwRep.email}`} onClose={() => setPwRep(null)}>
          <form onSubmit={savePassword}>
            <div className='occ-modal-body' style={{ display: 'grid', gap: 12 }}>
              <p className='muted' style={{ margin: 0 }}>Set a new dashboard password for this salesman. Share it with them securely.</p>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='label'>New password</span>
                <input className='input' type='text' value={pwValue} onChange={(e) => setPwValue(e.target.value)} placeholder='Min 6 characters' minLength={6} required />
              </label>
            </div>
            <div className='occ-modal-foot'>
              <button type='button' className='btn soft' onClick={() => setPwRep(null)} disabled={busy}>Cancel</button>
              <button type='submit' className='btn primary' disabled={busy || pwValue.length < 6}>{busy ? 'Saving…' : 'Reset password'}</button>
            </div>
          </form>
        </Modal>
      ) : null}

      {profileRep ? (
        <Modal title={`${profileRep.name || profileRep.email} — profile`} onClose={() => { setProfileRep(null); setProfile(null) }} wide>
          <div className='occ-modal-body' style={{ display: 'grid', gap: 14 }}>
            {!profile ? (
              <div className='muted'>Loading…</div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <span className='pill p-cyan' style={{ fontFamily: 'ui-monospace, monospace' }}>{profileRep.promo_code}</span>
                  <span className={`pill ${profileRep.is_active ? 'p-green' : 'p-amber'}`}>{profileRep.is_active ? 'Active' : 'Disabled'}</span>
                  {profileRep.country ? <span className='muted'>{profileRep.country}</span> : null}
                  {profile.sample ? <span className='pill p-amber'>Sample data</span> : null}
                </div>
                {profile.stats ? (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 12 }}>
                    <div className='note'><div className='muted'>Won deals</div><strong>{profile.stats.won_deals.count}</strong></div>
                    <div className='note'><div className='muted'>Active companies</div><strong>{profile.stats.wallet.active_companies}</strong></div>
                    <div className='note'><div className='muted'>Revenue</div><strong>{money(profile.stats.wallet.revenue_minor)}</strong></div>
                    <div className='note'><div className='muted'>Commission (pending)</div><strong>{money(profile.stats.wallet.commission_pending_minor)}</strong></div>
                  </div>
                ) : null}
                <div>
                  <strong>Customers ({profile.customers.length})</strong>
                  {profile.customers.length === 0 ? (
                    <div className='muted' style={{ marginTop: 8 }}>No customers yet — they appear once this salesman adds prospects or converts a sale.</div>
                  ) : (
                    <table className='table' style={{ marginTop: 6 }}>
                      <thead>
                        <tr><th>Company</th><th>Contact</th><th>Mobile</th><th>Type</th><th>Branches</th><th>Status</th><th>Converted</th></tr>
                      </thead>
                      <tbody>
                        {profile.customers.map((c) => (
                          <tr key={c.id}>
                            <td>{c.company_name || c.full_name}</td>
                            <td className='muted'>{c.full_name}</td>
                            <td className='muted'>{c.mobile || '—'}</td>
                            <td className='muted'>{c.business_type || '—'}</td>
                            <td>{c.branches ?? '—'}</td>
                            <td><span className={`pill ${c.status === 'won' ? 'p-green' : c.status === 'contacted' ? 'p-cyan' : 'p-amber'}`}>{c.status}</span></td>
                            <td className='muted'>{c.org_id ? 'Yes' : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </>
            )}
          </div>
          <div className='occ-modal-foot'>
            <button type='button' className='btn soft' onClick={() => { setProfileRep(null); setProfile(null) }}>Close</button>
            <button type='button' className='btn primary' onClick={() => { const r = profileRep; setProfileRep(null); setProfile(null); openEdit(r) }}>Edit salesman</button>
          </div>
        </Modal>
      ) : null}
    </>
  )
}
