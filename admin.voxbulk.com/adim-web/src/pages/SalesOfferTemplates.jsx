import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { SALES_OFFER_TYPES } from '../lib/salesOfferTypes'

const EMPTY = {
  name: '',
  offer_type: 'dental_trial',
  plan_code: 'dental_1',
  trial_days: 15,
  survey_contacts_included: 3,
  interview_contacts_included: 3,
  free_call_credits: 0,
  expires_in_days: 30,
  is_active: true,
  sort_order: 100,
}

function summaryLine(row) {
  if (row.offer_type === 'survey_credits') return `${row.survey_contacts_included} survey contacts · ${row.expires_in_days}d expiry`
  if (row.offer_type === 'interview_credits') return `${row.interview_contacts_included} interviews · ${row.expires_in_days}d expiry`
  return `${row.plan_code || 'plan'} · ${row.trial_days} day trial · ${row.expires_in_days}d expiry`
}

export default function SalesOfferTemplates() {
  const [templates, setTemplates] = useState([])
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState('')
  const [creating, setCreating] = useState(false)
  const [editId, setEditId] = useState('')
  const [draft, setDraft] = useState(EMPTY)
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const [tplData, planRows] = await Promise.all([
      apiFetch('/admin/frontpage/lead-sales/offer-templates'),
      apiFetch('/admin/products/plans/active').catch(() => []),
    ])
    setTemplates(Array.isArray(tplData?.templates) ? tplData.templates : [])
    setPlans(Array.isArray(planRows) ? planRows : [])
  }, [])

  useEffect(() => {
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        setMsg(e?.message || 'Could not load templates')
      } finally {
        setLoading(false)
      }
    })()
  }, [load])

  const activeCount = useMemo(() => templates.filter((t) => t.is_active).length, [templates])

  const startCreate = () => {
    setEditId('new')
    setDraft({ ...EMPTY, name: 'New sales offer' })
    setMsg('')
  }

  const startEdit = (row) => {
    setEditId(row.id)
    setDraft({ ...row })
    setMsg('')
  }

  const saveDraft = async () => {
    setSavingId(editId)
    setMsg('')
    try {
      if (editId === 'new') {
        await apiFetch('/admin/frontpage/lead-sales/offer-templates', {
          method: 'POST',
          body: JSON.stringify(draft),
        })
      } else {
        await apiFetch(`/admin/frontpage/lead-sales/offer-templates/${encodeURIComponent(editId)}`, {
          method: 'PUT',
          body: JSON.stringify(draft),
        })
      }
      await load()
      setEditId('')
      setDraft(EMPTY)
      setMsg('Template saved.')
    } catch (e) {
      setMsg(e?.message || 'Save failed')
    } finally {
      setSavingId('')
    }
  }

  const toggleActive = async (row) => {
    setSavingId(row.id)
    try {
      await apiFetch(`/admin/frontpage/lead-sales/offer-templates/${encodeURIComponent(row.id)}`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: !row.is_active }),
      })
      await load()
    } catch (e) {
      setMsg(e?.message || 'Update failed')
    } finally {
      setSavingId('')
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <Link to='/marketing/lead-sales/settings' className='muted' style={{ fontSize: 13 }}>
            ← Lead sales setup
          </Link>
          <h1 style={{ marginTop: 8 }}>Sales offer templates</h1>
          <p className='muted'>
            Set once — after each call, AI picks subscription / survey / interview and auto-sends the matching template.
          </p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={load} disabled={loading}>
            Refresh
          </button>
          <button type='button' className='btn primary' onClick={startCreate}>
            New template
          </button>
        </div>
      </div>

      {msg ? <div className='note' style={{ marginBottom: 12 }}>{msg}</div> : null}

      <div className='salesTplStats'>
        <div className='salesTplStat'>
          <label>Active templates</label>
          <strong>{activeCount}</strong>
        </div>
        <div className='salesTplStat'>
          <label>AI routing</label>
          <strong>Call outcome</strong>
          <span className='muted'>Map each type in Lead sales setup</span>
        </div>
      </div>

      {loading ? <p className='muted'>Loading…</p> : null}

      <div className='salesTplList'>
        {templates.map((row) => (
          <section key={row.id} className={`card salesTplRow${editId === row.id ? ' isEditing' : ''}`}>
            <div className='salesTplRowHead'>
              <div>
                <strong>{row.name}</strong>
                <span className='muted salesTplRowMeta'>{summaryLine(row)}</span>
              </div>
              <div className='actions'>
                <span className={`pill ${row.is_active ? 'p-green' : 'p-amber'}`}>{row.is_active ? 'Active' : 'Off'}</span>
                <button type='button' className='btn soft' onClick={() => startEdit(row)}>
                  Edit
                </button>
                <button type='button' className='btn soft' disabled={savingId === row.id} onClick={() => toggleActive(row)}>
                  {row.is_active ? 'Disable' : 'Enable'}
                </button>
              </div>
            </div>
            {editId === row.id ? (
              <TemplateEditor draft={draft} setDraft={setDraft} plans={plans} onSave={saveDraft} saving={savingId === row.id} onCancel={() => setEditId('')} />
            ) : null}
          </section>
        ))}
      </div>

      {editId === 'new' ? (
        <section className='card salesTplRow isEditing' style={{ marginTop: 14 }}>
          <div className='cardHead'><h3>New template</h3></div>
          <div className='cardBody'>
            <TemplateEditor draft={draft} setDraft={setDraft} plans={plans} onSave={saveDraft} saving={creating} onCancel={() => setEditId('')} />
          </div>
        </section>
      ) : null}
    </>
  )
}

function TemplateEditor({ draft, setDraft, plans, onSave, saving, onCancel }) {
  const set = (field, value) => setDraft((d) => ({ ...d, [field]: value }))

  return (
    <div className='salesTplEditor'>
      <div className='salesTplFieldGrid'>
        <label className='salesTplField'>
          <span>Name</span>
          <input className='input inputCompact' value={draft.name || ''} onChange={(e) => set('name', e.target.value)} />
        </label>
        <label className='salesTplField'>
          <span>Offer type</span>
          <select className='input inputCompact' value={draft.offer_type || 'dental_trial'} onChange={(e) => set('offer_type', e.target.value)}>
            {SALES_OFFER_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </label>
        <label className='salesTplField'>
          <span>Expires (days)</span>
          <input className='input inputCompact' type='number' min={1} max={365} value={draft.expires_in_days ?? 30} onChange={(e) => set('expires_in_days', e.target.value)} />
        </label>
        <label className='salesTplField'>
          <span>Sort order</span>
          <input className='input inputCompact' type='number' value={draft.sort_order ?? 100} onChange={(e) => set('sort_order', e.target.value)} />
        </label>
        <label className='salesTplField salesTplCheck'>
          <span>Active</span>
          <input type='checkbox' checked={draft.is_active !== false} onChange={(e) => set('is_active', e.target.checked)} />
        </label>
      </div>

      {draft.offer_type === 'dental_trial' ? (
        <div className='salesTplFieldGrid'>
          <label className='salesTplField'>
            <span>Plan</span>
            <select className='input inputCompact' value={draft.plan_code || ''} onChange={(e) => set('plan_code', e.target.value)}>
              {plans.length ? plans.map((p) => <option key={p.code} value={p.code}>{p.name}</option>) : <option value='dental_1'>dental_1</option>}
            </select>
          </label>
          <label className='salesTplField'>
            <span>Trial days</span>
            <input className='input inputCompact' type='number' min={0} max={90} value={draft.trial_days ?? 15} onChange={(e) => set('trial_days', e.target.value)} />
          </label>
          <label className='salesTplField'>
            <span>Free call credits</span>
            <input className='input inputCompact' type='number' min={0} value={draft.free_call_credits ?? 0} onChange={(e) => set('free_call_credits', e.target.value)} />
          </label>
        </div>
      ) : null}

      {draft.offer_type === 'survey_credits' ? (
        <div className='salesTplFieldGrid'>
          <label className='salesTplField'>
            <span>Survey contacts</span>
            <input className='input inputCompact' type='number' min={1} value={draft.survey_contacts_included ?? 3} onChange={(e) => set('survey_contacts_included', e.target.value)} />
          </label>
        </div>
      ) : null}

      {draft.offer_type === 'interview_credits' ? (
        <div className='salesTplFieldGrid'>
          <label className='salesTplField'>
            <span>Interviews</span>
            <input className='input inputCompact' type='number' min={1} value={draft.interview_contacts_included ?? 3} onChange={(e) => set('interview_contacts_included', e.target.value)} />
          </label>
        </div>
      ) : null}

      <div className='actions' style={{ marginTop: 10 }}>
        <button type='button' className='btn primary' onClick={onSave} disabled={saving}>{saving ? 'Saving…' : 'Save template'}</button>
        <button type='button' className='btn soft' onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}
