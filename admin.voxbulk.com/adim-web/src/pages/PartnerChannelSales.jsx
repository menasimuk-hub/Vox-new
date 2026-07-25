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
        style={wide ? { maxWidth: 960, width: '94vw' } : undefined}
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

const EMPTY_FORM = {
  company_name: '',
  name: '',
  email: '',
  password: '',
  promo_code: '',
  country: '',
  commission_pct: '15',
}
const PROMO_CODE_RE = /^[A-Z0-9]{4,12}$/

export default function PartnerChannelSales() {
  const [reps, setReps] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState(EMPTY_FORM)
  const [createErr, setCreateErr] = useState('')

  const [editRep, setEditRep] = useState(null)
  const [editForm, setEditForm] = useState({
    company_name: '',
    name: '',
    promo_code: '',
    country: '',
    commission_pct: '15',
  })

  const [pwRep, setPwRep] = useState(null)
  const [pwValue, setPwValue] = useState('')

  const [profileRep, setProfileRep] = useState(null)
  const [profile, setProfile] = useState(null)

  const load = async () => {
    setLoading(true)
    setErr('')
    try {
      const res = await apiFetch('/admin/sales-reps?kind=partner_channel')
      setReps(res?.items || [])
    } catch (e) {
      setErr(e?.message || 'Failed to load partner channel accounts')
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

    const companyName = createForm.company_name.trim()
    const name = createForm.name.trim() || companyName
    const email = createForm.email.trim().toLowerCase()
    const password = createForm.password
    const promoCode = createForm.promo_code.replace(/[^A-Za-z0-9]/g, '').toUpperCase()
    const commissionPct = Number(createForm.commission_pct || 15)

    if (!companyName) {
      setCreateErr('Company / partner name is required.')
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
      setCreateErr('Promo code must be 4–12 letters or numbers (e.g. PARTNER01).')
      setBusy(false)
      return
    }

    try {
      const res = await apiFetch('/admin/sales-reps', {
        method: 'POST',
        body: JSON.stringify({
          kind: 'partner_channel',
          company_name: companyName,
          name,
          email,
          password,
          promo_code: promoCode,
          country: createForm.country.trim().toUpperCase(),
          commission_pct: commissionPct,
        }),
      })
      setMsg(
        `Created ${res?.rep?.email || email} · promo ${res?.rep?.promo_code || promoCode} · ${res?.rep?.commission_pct ?? commissionPct}% on every paid subscription. They sign in at the dashboard.`,
      )
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
      company_name: rep.company_name || '',
      name: rep.name || '',
      promo_code: rep.promo_code || '',
      country: rep.country || '',
      commission_pct: String(rep.commission_pct ?? 15),
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
          company_name: editForm.company_name.trim(),
          name: editForm.name.trim(),
          promo_code: editForm.promo_code.trim().toUpperCase(),
          country: editForm.country.trim().toUpperCase(),
          commission_pct: Number(editForm.commission_pct || 15),
        }),
      })
      setMsg(`Updated ${editForm.company_name || editForm.name || editRep.email}.`)
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
      setMsg(`Password reset for ${pwRep.email || pwRep.name}.`)
      setPwRep(null)
      setPwValue('')
    } catch (e2) {
      setErr(e2?.message || 'Password reset failed')
    } finally {
      setBusy(false)
    }
  }

  const toggleActive = async (rep) => {
    setBusy(true)
    setErr('')
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !rep.is_active }),
      })
      load()
    } catch (e2) {
      setErr(e2?.message || 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (rep) => {
    if (!window.confirm(`Delete partner channel ${rep.company_name || rep.name || rep.email}?`)) return
    setBusy(true)
    setErr('')
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, { method: 'DELETE' })
      load()
    } catch (e2) {
      setErr(e2?.message || 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const openProfile = async (rep) => {
    setProfileRep(rep)
    setProfile(null)
    try {
      const dash = await apiFetch(`/admin/sales-reps/${rep.id}/dashboard`)
      setProfile({ stats: dash?.stats || null })
    } catch (e2) {
      setErr(e2?.message || 'Failed to load profile')
      setProfileRep(null)
    }
  }

  const markAllPaid = async (rep) => {
    if (!window.confirm(`Mark all pending commissions paid for ${rep.company_name || rep.name}?`)) return
    setBusy(true)
    setErr('')
    setMsg('')
    try {
      const res = await apiFetch(`/admin/sales-reps/${rep.id}/commissions/mark-paid`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
      setMsg(`Marked ${res?.marked_paid ?? 0} commission(s) paid · ${money(res?.amount_minor)}.`)
      if (profileRep?.id === rep.id) openProfile(rep)
      load()
    } catch (e2) {
      setErr(e2?.message || 'Mark paid failed')
    } finally {
      setBusy(false)
    }
  }

  const resetPartnerServices = async () => {
    if (
      !window.confirm(
        'Reset all Partner Channel workspaces to normal service defaults?\n\n' +
          'They will inherit Admin Onboarding Services grants, start with Interview + Survey visible, ' +
          'and modules you turned Off will stay hidden. Forced “all services on” overrides are cleared.',
      )
    ) {
      return
    }
    setBusy(true)
    setErr('')
    setMsg('')
    try {
      const res = await apiFetch('/admin/sales-reps/partner-channel/reset-services', { method: 'POST', body: '{}' })
      setMsg(`Reset services for ${res?.reset ?? 0} partner workspace(s).`)
    } catch (e2) {
      setErr(e2?.message || 'Reset services failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Partner Channel Sales</h1>
          <p>
            Partners get the normal user dashboard (only Admin-granted / active services) plus Partner Channel Sales
            (Overview, Wallet & commission, Send offer). They can use wallet balance from commission or any
            payment method on enabled modules.
          </p>
        </div>
        <div className='actions'>
          <button className='btn soft' onClick={load} disabled={busy}>Refresh</button>
          <button className='btn soft' onClick={resetPartnerServices} disabled={busy}>
            Reset partner services
          </button>
          <button
            className='btn primary'
            disabled={busy}
            onClick={() => {
              setErr('')
              setMsg('')
              setCreateErr('')
              setCreateForm(EMPTY_FORM)
              setShowCreate(true)
            }}
          >
            + Create partner
          </button>
        </div>
      </div>

      {err ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.45)', marginBottom: 12 }}>{err}</div> : null}
      {msg ? <div className='note' style={{ marginBottom: 12 }}>{msg}</div> : null}

      <div className='card'>
        <div className='cardHead'>
          <h3>Partners ({reps.length})</h3>
        </div>
        <div className='cardBody'>
          {loading ? (
            <div className='muted'>Loading…</div>
          ) : reps.length === 0 ? (
            <div className='muted'>No partner channel accounts yet. Click <strong>Create partner</strong> to add one.</div>
          ) : (
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Contact</th>
                    <th>Email</th>
                    <th>Promo code</th>
                    <th>Rate</th>
                    <th>Companies</th>
                    <th>Commission</th>
                    <th>Status</th>
                    <th style={{ width: 1 }} />
                  </tr>
                </thead>
                <tbody>
                  {reps.map((r) => (
                    <tr key={r.id}>
                      <td><strong>{r.company_name || r.name}</strong></td>
                      <td className='muted'>{r.name}</td>
                      <td className='muted'>{r.email}</td>
                      <td style={{ fontFamily: 'ui-monospace, monospace' }}>{r.promo_code}</td>
                      <td>{Number(r.commission_pct ?? 15)}%</td>
                      <td>{r.customers ?? 0}</td>
                      <td>{money(r.commission_minor)}</td>
                      <td>
                        <span className={`pill ${r.is_active ? 'p-green' : 'p-amber'}`}>{r.is_active ? 'Active' : 'Disabled'}</span>
                      </td>
                      <td>
                        <div className='actions' style={{ flexWrap: 'nowrap', justifyContent: 'flex-end' }}>
                          <button className='btn soft' onClick={() => openProfile(r)}>KPIs</button>
                          <button className='btn soft' onClick={() => markAllPaid(r)}>Mark paid</button>
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
        <Modal title='Create partner channel' onClose={() => { if (!busy) { setShowCreate(false); setCreateErr('') } }}>
          <form onSubmit={create} noValidate>
            <div className='occ-modal-body' style={{ display: 'grid', gap: 12 }}>
              <p className='muted' style={{ margin: 0 }}>
                Creates a normal dashboard login that follows Admin Onboarding Services (disabled modules stay hidden),
                plus Partner Channel Sales (Overview, Wallet & commission, Send offer). Starts with Interview + Survey
                visible. Commission accrues on every paid subscription using their promo code.
              </p>
              {createErr ? (
                <div className='note' style={{ borderColor: 'rgba(220,38,38,0.45)', margin: 0 }} role='alert'>
                  {createErr}
                </div>
              ) : null}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 12 }}>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Company / partner name</span>
                  <input className='input' value={createForm.company_name} onChange={(e) => setCreateForm({ ...createForm, company_name: e.target.value })} placeholder='Acme Partners Ltd' required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Contact name</span>
                  <input className='input' value={createForm.name} onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })} placeholder='Jane Smith' />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Email (login)</span>
                  <input className='input' type='email' value={createForm.email} onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })} placeholder='partner@company.com' required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Temporary password</span>
                  <input className='input' type='password' value={createForm.password} onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })} placeholder='Min 6 characters' minLength={6} required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Promo code</span>
                  <input className='input' style={{ textTransform: 'uppercase', fontFamily: 'ui-monospace, monospace' }} value={createForm.promo_code} onChange={(e) => setCreateForm({ ...createForm, promo_code: e.target.value })} placeholder='PARTNER01' required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Commission %</span>
                  <input className='input' type='number' min='0' max='100' step='0.01' value={createForm.commission_pct} onChange={(e) => setCreateForm({ ...createForm, commission_pct: e.target.value })} required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Country (ISO, optional)</span>
                  <input className='input' style={{ textTransform: 'uppercase' }} value={createForm.country} onChange={(e) => setCreateForm({ ...createForm, country: e.target.value })} placeholder='GB' maxLength={2} />
                </label>
              </div>
            </div>
            <div className='occ-modal-foot'>
              <button type='button' className='btn soft' onClick={() => setShowCreate(false)} disabled={busy}>Cancel</button>
              <button type='submit' className='btn primary' disabled={busy}>{busy ? 'Creating…' : 'Create partner'}</button>
            </div>
          </form>
        </Modal>
      ) : null}

      {editRep ? (
        <Modal title={`Edit ${editRep.company_name || editRep.name || editRep.email}`} onClose={() => setEditRep(null)}>
          <form onSubmit={saveEdit}>
            <div className='occ-modal-body' style={{ display: 'grid', gap: 12 }}>
              <div className='muted' style={{ fontSize: 12 }}>{editRep.email}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 12 }}>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Company / partner name</span>
                  <input className='input' value={editForm.company_name} onChange={(e) => setEditForm({ ...editForm, company_name: e.target.value })} />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Contact name</span>
                  <input className='input' value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Promo code</span>
                  <input className='input' style={{ textTransform: 'uppercase', fontFamily: 'ui-monospace, monospace' }} value={editForm.promo_code} onChange={(e) => setEditForm({ ...editForm, promo_code: e.target.value })} required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Commission %</span>
                  <input className='input' type='number' min='0' max='100' step='0.01' value={editForm.commission_pct} onChange={(e) => setEditForm({ ...editForm, commission_pct: e.target.value })} required />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className='label'>Country (ISO)</span>
                  <input className='input' style={{ textTransform: 'uppercase' }} value={editForm.country} onChange={(e) => setEditForm({ ...editForm, country: e.target.value })} maxLength={2} />
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
        <Modal title={`Reset password — ${pwRep.company_name || pwRep.name || pwRep.email}`} onClose={() => setPwRep(null)}>
          <form onSubmit={savePassword}>
            <div className='occ-modal-body' style={{ display: 'grid', gap: 12 }}>
              <p className='muted' style={{ margin: 0 }}>Set a new dashboard password for this partner. Share it securely.</p>
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
        <Modal title={`${profileRep.company_name || profileRep.name || profileRep.email} — KPIs`} onClose={() => { setProfileRep(null); setProfile(null) }} wide>
          <div className='occ-modal-body' style={{ display: 'grid', gap: 14 }}>
            {!profile ? (
              <div className='muted'>Loading…</div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <span className='pill p-cyan' style={{ fontFamily: 'ui-monospace, monospace' }}>{profileRep.promo_code}</span>
                  <span className='pill p-cyan'>{Number(profileRep.commission_pct ?? 15)}% every paid invoice</span>
                  <span className={`pill ${profileRep.is_active ? 'p-green' : 'p-amber'}`}>{profileRep.is_active ? 'Active' : 'Disabled'}</span>
                </div>
                {profile.stats ? (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 12 }}>
                    <div className='note'><div className='muted'>Active companies</div><strong>{profile.stats.wallet.active_companies}</strong></div>
                    <div className='note'><div className='muted'>Codes used</div><strong>{profile.stats.wallet.codes_used}</strong></div>
                    <div className='note'><div className='muted'>Revenue</div><strong>{money(profile.stats.wallet.revenue_minor)}</strong></div>
                    <div className='note'><div className='muted'>Commission pending</div><strong>{money(profile.stats.wallet.commission_pending_minor)}</strong></div>
                  </div>
                ) : null}
                <div>
                  <strong>Commission ledger ({(profile.stats?.commissions || []).length})</strong>
                  {(profile.stats?.commissions || []).length === 0 ? (
                    <div className='muted' style={{ marginTop: 8 }}>No commissions yet — they appear when attributed customers pay a subscription invoice.</div>
                  ) : (
                    <table className='table' style={{ marginTop: 6 }}>
                      <thead>
                        <tr><th>Company</th><th>Amount</th><th>Status</th><th>Note</th><th>Date</th></tr>
                      </thead>
                      <tbody>
                        {(profile.stats.commissions || []).map((c) => (
                          <tr key={c.id}>
                            <td>{c.org_name || c.org_id}</td>
                            <td>{money(c.amount_minor, c.currency)}</td>
                            <td><span className={`pill ${c.status === 'paid' ? 'p-green' : 'p-amber'}`}>{c.status}</span></td>
                            <td className='muted'>{c.note || '—'}</td>
                            <td className='muted'>{c.created_at ? String(c.created_at).slice(0, 10) : '—'}</td>
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
            <button type='button' className='btn primary' onClick={() => markAllPaid(profileRep)} disabled={busy}>Mark pending paid</button>
          </div>
        </Modal>
      ) : null}
    </>
  )
}
