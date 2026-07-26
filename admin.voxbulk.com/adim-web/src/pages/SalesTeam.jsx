import React, { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import './orgControlCenter.css'
import './salesTeam.css'

function money(minor, currency = 'GBP') {
  const n = Number(minor || 0) / 100
  const sym = currency === 'USD' ? '$' : '£'
  return `${sym}${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function Modal({ title, onClose, children, wide }) {
  return (
    <div className='occ-modal-overlay open' role='presentation' onClick={onClose}>
      <div
        className='occ-modal'
        role='dialog'
        style={wide ? { maxWidth: 640, width: '94vw' } : undefined}
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
  name: '',
  email: '',
  password: '',
  mobile: '',
  promo_code: '',
  company_name: '',
  commission_type: 'month2',
  commission_pct: '15',
  commission_fixed_gbp: '',
  payout_method: 'bank',
  bank_holder_name: '',
  bank_name: '',
  bank_sort_code: '',
  bank_account_number: '',
  bank_address: '',
  paypal_email: '',
}

function tabFromPath(pathname, search) {
  const q = new URLSearchParams(search || '')
  if (q.get('tab') === 'partners' || pathname.includes('partner-channel')) return 'partners'
  return 'salesman'
}

function commissionBadge(rep) {
  const t = String(rep.commission_type || 'month2')
  if (t === 'fixed') return <span className='st-badge fixed'>Fixed {money(rep.commission_fixed_minor)}</span>
  if (t === 'percent') return <span className='st-badge percent'>{Number(rep.commission_pct || 0)}% on pay</span>
  return <span className='st-badge month2'>{Number(rep.commission_pct || 0)}% 2nd month</span>
}

function statusBadge(status) {
  const s = String(status || 'pending')
  if (s === 'active') return <span className='st-badge active'>Active</span>
  if (s === 'frozen') return <span className='st-badge frozen'>Frozen</span>
  const cls = s === 'paid' ? 'paid' : s === 'requested' || s === 'submitted' ? 'submitted' : s === 'rejected' ? 'rejected' : 'pending'
  const label = s === 'requested' || s === 'submitted' ? 'Awaiting approval' : s === 'pending' ? 'No invoice yet' : s
  return <span className={`st-badge ${cls}`}>{label}</span>
}

export default function SalesTeam({ initialTab }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [tab, setTab] = useState(() => initialTab || tabFromPath(location.pathname, location.search))
  const [reps, setReps] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [search, setSearch] = useState('')

  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formErr, setFormErr] = useState('')

  const [pwRep, setPwRep] = useState(null)
  const [pwValue, setPwValue] = useState('')

  const [profileRep, setProfileRep] = useState(null)
  const [profile, setProfile] = useState(null)
  const [invoiceDetail, setInvoiceDetail] = useState(null)

  const kind = tab === 'partners' ? 'partner_channel' : 'salesman'

  const load = async () => {
    setLoading(true)
    setErr('')
    try {
      const res = await apiFetch(`/admin/sales-reps?kind=${kind}`)
      setReps(res?.items || [])
    } catch (e) {
      setErr(e?.message || 'Failed to load sales team')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const next = initialTab || tabFromPath(location.pathname, location.search)
    setTab(next)
  }, [location.pathname, location.search, initialTab])

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return reps
    return reps.filter((r) =>
      [r.name, r.email, r.mobile, r.promo_code, r.company_name].some((v) => String(v || '').toLowerCase().includes(q))
    )
  }, [reps, search])

  const switchTab = (next) => {
    setTab(next)
    setProfileRep(null)
    setProfile(null)
    setInvoiceDetail(null)
    navigate(next === 'partners' ? '/marketing/partner-channel-sales' : '/marketing/salesmen')
  }

  const openCreate = () => {
    setEditId(null)
    setForm({
      ...EMPTY_FORM,
      commission_type: tab === 'partners' ? 'percent' : 'month2',
      email: tab === 'salesman' ? '' : '',
    })
    setFormErr('')
    setShowForm(true)
  }

  const openEdit = (rep) => {
    const p = rep.payout || {}
    setEditId(rep.id)
    setForm({
      name: rep.name || '',
      email: rep.email || '',
      password: '',
      mobile: rep.mobile || '',
      promo_code: rep.promo_code || '',
      company_name: rep.company_name || '',
      commission_type: rep.commission_type || 'month2',
      commission_pct: String(rep.commission_pct ?? 15),
      commission_fixed_gbp: rep.commission_fixed_minor != null ? String(Number(rep.commission_fixed_minor) / 100) : '',
      payout_method: p.payout_method || 'bank',
      bank_holder_name: p.bank_holder_name || '',
      bank_name: p.bank_name || '',
      bank_sort_code: p.bank_sort_code || '',
      bank_account_number: p.bank_account_number || '',
      bank_address: p.bank_address || '',
      paypal_email: p.paypal_email || '',
    })
    setFormErr('')
    setShowForm(true)
  }

  const saveForm = async () => {
    setBusy(true)
    setFormErr('')
    setMsg('')
    const fixedMinor = form.commission_type === 'fixed'
      ? Math.round(parseFloat(form.commission_fixed_gbp || '0') * 100)
      : 0
    const payload = {
      name: form.name,
      email: form.email,
      password: form.password,
      mobile: form.mobile,
      promo_code: form.promo_code,
      company_name: form.company_name,
      kind,
      commission_type: form.commission_type,
      commission_pct: form.commission_pct,
      commission_fixed_minor: fixedMinor,
      payout: {
        payout_method: form.payout_method,
        bank_holder_name: form.bank_holder_name,
        bank_name: form.bank_name,
        bank_sort_code: form.bank_sort_code,
        bank_account_number: form.bank_account_number,
        bank_address: form.bank_address,
        paypal_email: form.paypal_email,
      },
    }
    try {
      if (editId) {
        const patch = { ...payload }
        delete patch.email
        delete patch.password
        delete patch.kind
        await apiFetch(`/admin/sales-reps/${editId}`, { method: 'PATCH', body: JSON.stringify(patch) })
        setMsg('Saved')
      } else {
        await apiFetch('/admin/sales-reps', { method: 'POST', body: JSON.stringify(payload) })
        setMsg('Created')
      }
      setShowForm(false)
      await load()
      if (profileRep && editId === profileRep.id) await openProfile(profileRep)
    } catch (e) {
      setFormErr(e?.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const resetPassword = async () => {
    if (!pwRep) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/${pwRep.id}/reset-password`, {
        method: 'POST',
        body: JSON.stringify({ password: pwValue }),
      })
      setMsg('Password reset')
      setPwRep(null)
      setPwValue('')
    } catch (e) {
      setErr(e?.message || 'Reset failed')
    } finally {
      setBusy(false)
    }
  }

  const toggleFreeze = async (rep) => {
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !rep.is_active }),
      })
      await load()
      if (profileRep?.id === rep.id) await openProfile({ ...rep, is_active: !rep.is_active })
    } catch (e) {
      setErr(e?.message || 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  const deleteRep = async (rep) => {
    if (!window.confirm(`Delete ${rep.name}?`)) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/${rep.id}`, { method: 'DELETE' })
      setMsg('Deleted')
      if (profileRep?.id === rep.id) {
        setProfileRep(null)
        setProfile(null)
      }
      await load()
    } catch (e) {
      setErr(e?.message || 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const openProfile = async (rep) => {
    setProfileRep(rep)
    setInvoiceDetail(null)
    setErr('')
    try {
      const res = await apiFetch(`/admin/sales-reps/${rep.id}/dashboard`)
      setProfile(res)
      if (res?.rep) setProfileRep(res.rep)
    } catch (e) {
      setErr(e?.message || 'Failed to load profile')
    }
  }

  const openInvoice = async (invoiceId) => {
    try {
      const res = await apiFetch(`/admin/sales-reps/payout-invoices/${invoiceId}`)
      setInvoiceDetail(res?.invoice || null)
    } catch (e) {
      setErr(e?.message || 'Failed to open invoice')
    }
  }

  const approvePay = async (invoiceId) => {
    if (!window.confirm('Approve and mark this payout invoice as paid?')) return
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/payout-invoices/${invoiceId}/approve-pay`, { method: 'POST', body: '{}' })
      setMsg('Invoice approved and paid')
      if (profileRep) await openProfile(profileRep)
    } catch (e) {
      setErr(e?.message || 'Approve failed')
    } finally {
      setBusy(false)
    }
  }

  const rejectInvoice = async (invoiceId) => {
    const reason = window.prompt('Reject reason (optional)') || ''
    setBusy(true)
    try {
      await apiFetch(`/admin/sales-reps/payout-invoices/${invoiceId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      })
      setMsg('Invoice rejected')
      if (profileRep) await openProfile(profileRep)
    } catch (e) {
      setErr(e?.message || 'Reject failed')
    } finally {
      setBusy(false)
    }
  }

  if (profileRep && profile) {
    const stats = profile.stats || {}
    const wallet = stats.wallet || {}
    const payout = stats.payout || profileRep.payout || {}
    const invoices = stats.payout_invoices || []
    const commissions = stats.commissions || []
    return (
      <div className='occ-page st-wrap wide'>
        <button type='button' className='st-back' onClick={() => { setProfileRep(null); setProfile(null); setInvoiceDetail(null) }}>
          ← Back to list
        </button>
        {err ? <div className='occ-alert error'>{err}</div> : null}
        {msg ? <div className='occ-alert success'>{msg}</div> : null}

        <div className='st-profile-top'>
          <div>
            <h2 style={{ margin: '0 0 4px' }}>{profileRep.name}</h2>
            <div className='muted' style={{ fontSize: 13 }}>
              <span>{profileRep.email}</span>
              {profileRep.mobile ? <span style={{ marginLeft: 12 }}>{profileRep.mobile}</span> : null}
              <span style={{ marginLeft: 12 }} className='st-promo'>{profileRep.promo_code}</span>
            </div>
          </div>
          <div className='st-actions'>
            {statusBadge(profileRep.is_active ? 'active' : 'frozen')}
            <button type='button' className='occ-btn' onClick={() => openEdit(profileRep)}>Edit</button>
            <button type='button' className='occ-btn ghost' onClick={() => toggleFreeze(profileRep)}>
              {profileRep.is_active ? 'Freeze' : 'Unfreeze'}
            </button>
          </div>
        </div>

        <div className='st-stat-grid'>
          <div className='st-stat'><div className='label'>Total commission</div><div className='value'>{money(wallet.commission_minor)}</div></div>
          <div className='st-stat'><div className='label'>Paid</div><div className='value' style={{ color: '#4c7a4a' }}>{money(wallet.commission_paid_minor)}</div></div>
          <div className='st-stat'><div className='label'>Awaiting approval</div><div className='value' style={{ color: '#a9822c' }}>{money(wallet.commission_requested_minor)}</div></div>
          <div className='st-stat'><div className='label'>Available</div><div className='value'>{money(wallet.commission_available_minor)}</div></div>
        </div>

        <div className='st-profile-grid'>
          <div>
            <div className='st-card' style={{ marginBottom: 14 }}>
              <h3>Payout details</h3>
              {payout.payout_method === 'paypal' ? (
                <>
                  <div className='st-row'><span className='k'>Method</span><span className='v'>PayPal</span></div>
                  <div className='st-row'><span className='k'>PayPal</span><span className='v'>{payout.paypal_email || '—'}</span></div>
                </>
              ) : (
                <>
                  <div className='st-row'><span className='k'>Method</span><span className='v'>Bank</span></div>
                  <div className='st-row'><span className='k'>Holder / company</span><span className='v'>{payout.bank_holder_name || '—'}</span></div>
                  <div className='st-row'><span className='k'>Bank</span><span className='v'>{payout.bank_name || '—'}</span></div>
                  <div className='st-row'><span className='k'>Sort code</span><span className='v'>{payout.bank_sort_code || '—'}</span></div>
                  <div className='st-row'><span className='k'>Account</span><span className='v'>{payout.bank_account_number || '—'}</span></div>
                  <div className='st-row'><span className='k'>Address</span><span className='v'>{payout.bank_address || '—'}</span></div>
                </>
              )}
            </div>
            <div className='st-card'>
              <h3>Commission setup</h3>
              <div className='st-row'><span className='k'>Type</span><span className='v'>{commissionBadge(profileRep)}</span></div>
              <div className='st-row'><span className='k'>Promo</span><span className='v st-promo'>{profileRep.promo_code}</span></div>
              {profileRep.company_name ? <div className='st-row'><span className='k'>Company</span><span className='v'>{profileRep.company_name}</span></div> : null}
            </div>
          </div>

          <div className='st-card'>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Payout invoices</h3>
            </div>
            <div className='st-table-card' style={{ border: 'none', boxShadow: 'none' }}>
              <table>
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.length === 0 ? (
                    <tr><td colSpan={4} className='st-empty'>No payout invoices yet.</td></tr>
                  ) : invoices.map((inv) => (
                    <tr key={inv.id}>
                      <td>
                        <strong>{inv.invoice_number}</strong>
                        <div className='muted' style={{ fontSize: 11 }}>{(inv.submitted_at || '').slice(0, 10)}</div>
                      </td>
                      <td>{inv.amount_display || money(inv.amount_minor)}</td>
                      <td>{statusBadge(inv.status)}</td>
                      <td>
                        <div className='st-actions'>
                          <button type='button' className='st-mark' onClick={() => openInvoice(inv.id)}>Open</button>
                          {inv.status === 'submitted' ? (
                            <>
                              <button type='button' className='st-mark pay' disabled={busy} onClick={() => approvePay(inv.id)}>Approve &amp; pay</button>
                              <button type='button' className='st-mark reject' disabled={busy} onClick={() => rejectInvoice(inv.id)}>Reject</button>
                            </>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {invoiceDetail ? (
              <div className='st-invoice-detail'>
                <strong>{invoiceDetail.invoice_number}</strong> — {invoiceDetail.amount_display || money(invoiceDetail.amount_minor)}
                <div className='muted' style={{ marginTop: 6 }}>{invoiceDetail.payout_method_summary}</div>
                {invoiceDetail.notes ? <div style={{ marginTop: 8 }}>Notes: {invoiceDetail.notes}</div> : null}
                {invoiceDetail.payout_snapshot ? (
                  <pre style={{ marginTop: 10, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                    {JSON.stringify(invoiceDetail.payout_snapshot, null, 2)}
                  </pre>
                ) : null}
              </div>
            ) : null}

            <h3 style={{ margin: '20px 0 10px', fontSize: 12, textTransform: 'uppercase', color: '#6f6a5e' }}>Commission ledger</h3>
            <div className='st-table-card' style={{ border: 'none' }}>
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Customer / org</th>
                    <th>Amount</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {commissions.length === 0 ? (
                    <tr><td colSpan={4} className='st-empty'>No commission records yet.</td></tr>
                  ) : commissions.map((c) => (
                    <tr key={c.id}>
                      <td>{(c.created_at || '').slice(0, 10)}</td>
                      <td>{c.org_name || c.org_id}</td>
                      <td>{money(c.amount_minor, c.currency)}</td>
                      <td>{statusBadge(c.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className='occ-page st-wrap'>
      <div className='occ-head'>
        <div>
          <h1>Sales Team</h1>
          <p className='muted'>Manage salesmen and sales partners, commission setup, and payout invoices.</p>
        </div>
      </div>

      <div className='st-tabs'>
        <button type='button' className={`st-tab ${tab === 'salesman' ? 'active' : ''}`} onClick={() => switchTab('salesman')}>Sales Man</button>
        <button type='button' className={`st-tab ${tab === 'partners' ? 'active' : ''}`} onClick={() => switchTab('partners')}>Sales Partners</button>
      </div>

      {err ? <div className='occ-alert error'>{err}</div> : null}
      {msg ? <div className='occ-alert success'>{msg}</div> : null}

      <div className='st-toolbar'>
        <div className='st-search'>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={tab === 'partners' ? 'Search partners...' : 'Search salesman...'} />
        </div>
        <button type='button' className='occ-btn primary' onClick={openCreate}>
          {tab === 'partners' ? 'Add Sales Partner' : 'Add Sales Man'}
        </button>
      </div>

      <div className='st-table-card'>
        {loading ? (
          <div className='st-empty'>Loading…</div>
        ) : filtered.length === 0 ? (
          <div className='st-empty'>No records yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Mobile</th>
                <th>Commission</th>
                <th>Promo Code</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((rep) => (
                <tr key={rep.id} style={{ opacity: rep.is_active ? 1 : 0.55 }}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{rep.name}</div>
                    <div className='muted' style={{ fontSize: 12 }}>{rep.email}</div>
                  </td>
                  <td>{rep.mobile || '—'}</td>
                  <td>{commissionBadge(rep)}</td>
                  <td><span className='st-promo'>{rep.promo_code}</span></td>
                  <td>{rep.is_active ? <span className='st-badge active'>Active</span> : <span className='st-badge frozen'>Frozen</span>}</td>
                  <td>
                    <div className='st-actions'>
                      <button type='button' className='st-icon-btn' title='Profile' onClick={() => openProfile(rep)}>P</button>
                      <button type='button' className='st-icon-btn' title='Edit' onClick={() => openEdit(rep)}>E</button>
                      <button type='button' className='st-icon-btn' title='Reset password' onClick={() => { setPwRep(rep); setPwValue('') }}>R</button>
                      <button type='button' className='st-icon-btn' title={rep.is_active ? 'Freeze' : 'Unfreeze'} onClick={() => toggleFreeze(rep)}>F</button>
                      <button type='button' className='st-icon-btn' title='Delete' onClick={() => deleteRep(rep)}>D</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showForm ? (
        <Modal title={editId ? 'Edit member' : tab === 'partners' ? 'Add Sales Partner' : 'Add Sales Man'} onClose={() => setShowForm(false)} wide>
          <div className='occ-modal-body'>
            {formErr ? <div className='occ-alert error'>{formErr}</div> : null}
            <label className='occ-field'>Full name<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            {!editId ? (
              <>
                <label className='occ-field'>Email<input type='email' value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
                <label className='occ-field'>Temporary password<input value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
              </>
            ) : null}
            <label className='occ-field'>Mobile<input value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} /></label>
            <label className='occ-field'>Company name<input value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} /></label>
            <label className='occ-field'>Promo code<input value={form.promo_code} onChange={(e) => setForm({ ...form, promo_code: e.target.value.toUpperCase() })} style={{ textTransform: 'uppercase' }} /></label>

            <div className='occ-field'>
              <span>Commission type</span>
              <div className='st-comm-options' style={{ marginTop: 8 }}>
                {[
                  { id: 'month2', title: 'Paid on 2nd Month (%)', desc: 'Held until the 2nd month payment, as a % of the sale.' },
                  { id: 'fixed', title: 'Paid When Customer Pays — Fixed', desc: 'Flat GBP amount when the customer pays.' },
                  { id: 'percent', title: 'Paid When Customer Pays — Percentage', desc: 'Percentage of the sale when the customer pays.' },
                ].map((opt) => (
                  <label key={opt.id} className={`st-comm-option ${form.commission_type === opt.id ? 'selected' : ''}`}>
                    <input
                      type='radio'
                      name='commission_type'
                      checked={form.commission_type === opt.id}
                      onChange={() => setForm({ ...form, commission_type: opt.id })}
                    />
                    <div>
                      <div className='co-title'>{opt.title}</div>
                      <div className='co-desc'>{opt.desc}</div>
                      {form.commission_type === opt.id && opt.id !== 'fixed' ? (
                        <input
                          style={{ marginTop: 8, width: 120 }}
                          type='number'
                          min='0'
                          max='100'
                          step='0.1'
                          value={form.commission_pct}
                          onChange={(e) => setForm({ ...form, commission_pct: e.target.value })}
                          placeholder='%'
                        />
                      ) : null}
                      {form.commission_type === opt.id && opt.id === 'fixed' ? (
                        <input
                          style={{ marginTop: 8, width: 140 }}
                          type='number'
                          min='0'
                          step='0.01'
                          value={form.commission_fixed_gbp}
                          onChange={(e) => setForm({ ...form, commission_fixed_gbp: e.target.value })}
                          placeholder='GBP'
                        />
                      ) : null}
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className='occ-field'>
              <span>Payout method</span>
              <div className='st-comm-options' style={{ marginTop: 8 }}>
                <label className={`st-comm-option ${form.payout_method === 'bank' ? 'selected' : ''}`}>
                  <input type='radio' checked={form.payout_method === 'bank'} onChange={() => setForm({ ...form, payout_method: 'bank' })} />
                  <div style={{ flex: 1 }}>
                    <div className='co-title'>Bank account (UK)</div>
                    {form.payout_method === 'bank' ? (
                      <div style={{ marginTop: 8, display: 'grid', gap: 8 }}>
                        <input placeholder='Account holder / company name' value={form.bank_holder_name} onChange={(e) => setForm({ ...form, bank_holder_name: e.target.value })} />
                        <input placeholder='Bank name' value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} />
                        <input placeholder='Sort code' value={form.bank_sort_code} onChange={(e) => setForm({ ...form, bank_sort_code: e.target.value })} />
                        <input placeholder='Account number' value={form.bank_account_number} onChange={(e) => setForm({ ...form, bank_account_number: e.target.value })} />
                        <input placeholder='Address' value={form.bank_address} onChange={(e) => setForm({ ...form, bank_address: e.target.value })} />
                      </div>
                    ) : null}
                  </div>
                </label>
                <label className={`st-comm-option ${form.payout_method === 'paypal' ? 'selected' : ''}`}>
                  <input type='radio' checked={form.payout_method === 'paypal'} onChange={() => setForm({ ...form, payout_method: 'paypal' })} />
                  <div style={{ flex: 1 }}>
                    <div className='co-title'>PayPal</div>
                    {form.payout_method === 'paypal' ? (
                      <input style={{ marginTop: 8, width: '100%' }} type='email' placeholder='name@paypal.com' value={form.paypal_email} onChange={(e) => setForm({ ...form, paypal_email: e.target.value })} />
                    ) : null}
                  </div>
                </label>
              </div>
            </div>
          </div>
          <div className='occ-modal-foot'>
            <button type='button' className='occ-btn ghost' onClick={() => setShowForm(false)}>Cancel</button>
            <button type='button' className='occ-btn primary' disabled={busy} onClick={saveForm}>Save</button>
          </div>
        </Modal>
      ) : null}

      {pwRep ? (
        <Modal title='Reset password' onClose={() => setPwRep(null)}>
          <div className='occ-modal-body'>
            <p className='muted'>New temporary password for <strong>{pwRep.name}</strong>.</p>
            <label className='occ-field'>Password<input value={pwValue} onChange={(e) => setPwValue(e.target.value)} /></label>
          </div>
          <div className='occ-modal-foot'>
            <button type='button' className='occ-btn ghost' onClick={() => setPwRep(null)}>Cancel</button>
            <button type='button' className='occ-btn primary' disabled={busy || pwValue.length < 6} onClick={resetPassword}>Reset</button>
          </div>
        </Modal>
      ) : null}
    </div>
  )
}
