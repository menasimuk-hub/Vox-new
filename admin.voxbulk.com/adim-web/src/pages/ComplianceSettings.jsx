import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const LAWFUL_BASES = ['consent', 'contract', 'legitimate_interests', 'legal_obligation']
const ARTICLE9 = [
  'explicit_consent',
  'employment_safeguard',
  'vital_interests',
  'legal_claims',
  'substantial_public_interest',
  'health_social_care',
  'public_health',
  'archiving_research',
]

export default function ComplianceSettings() {
  const [orgs, setOrgs] = useState([])
  const [orgId, setOrgId] = useState('')
  const [defaults, setDefaults] = useState(null)
  const [audit, setAudit] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  const loadOrgs = useCallback(async () => {
    const data = await apiFetch('/admin/organisations?limit=200')
    const list = Array.isArray(data?.items) ? data.items : []
    setOrgs(list)
    setOrgId((prev) => prev || String(list[0]?.id || ''))
  }, [])

  const loadOrg = useCallback(async (id) => {
    if (!id) return
    const data = await apiFetch(`/admin/compliance/organisations/${encodeURIComponent(id)}`)
    setDefaults(data?.defaults || {})
  }, [])

  const loadAudit = useCallback(async () => {
    const data = await apiFetch('/admin/compliance/audit?limit=50')
    setAudit(Array.isArray(data?.events) ? data.events : [])
  }, [])

  useEffect(() => {
    setLoading(true)
    setError('')
    Promise.all([loadOrgs(), loadAudit()])
      .catch((e) => setError(e?.message || 'Could not load compliance data'))
      .finally(() => setLoading(false))
  }, [loadOrgs, loadAudit])

  useEffect(() => {
    if (!orgId) return
    loadOrg(orgId).catch((e) => setError(e?.message || 'Could not load org defaults'))
  }, [orgId, loadOrg])

  const updateField = (key, value) => {
    setDefaults((prev) => ({ ...(prev || {}), [key]: value }))
  }

  const save = async (e) => {
    e.preventDefault()
    if (!orgId) return
    setSaving(true)
    setError('')
    setMsg('')
    try {
      await apiFetch(`/admin/compliance/organisations/${encodeURIComponent(orgId)}`, {
        method: 'PUT',
        body: JSON.stringify(defaults || {}),
      })
      setMsg('Organisation compliance defaults saved.')
      await loadAudit()
    } catch (err) {
      setError(err?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const runRetention = async () => {
    setError('')
    setMsg('')
    try {
      const data = await apiFetch('/admin/compliance/retention/run?dry_run=true', { method: 'POST' })
      setMsg(`Retention dry-run: ${JSON.stringify(data?.stats || {})}`)
    } catch (err) {
      setError(err?.message || 'Retention run failed')
    }
  }

  const selectedOrg = orgs.find((o) => o.id === orgId)

  return (
    <>
      <div className="pageTop">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            Compliance / UK baseline
          </div>
          <h1>UK compliance settings</h1>
          <p className="pageLead">
            PECR, UK GDPR, and DPA 2018 baseline. Configure org defaults; service orders inherit these unless overridden in order config.
            Survey WA and interview WA remain separate workflows — both use org suppression and STOP handling.
          </p>
        </div>
        <div className="pageTopActions">
          <Link className="btn" to="/compliance/audit">Audit log</Link>
          <button type="button" className="btn" onClick={runRetention}>Retention dry-run</button>
        </div>
      </div>

      {error ? <div className="alert error"><strong>{error}</strong></div> : null}
      {msg ? <div className="alert ok"><strong>{msg}</strong></div> : null}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardHead"><h2>Organisation defaults</h2></div>
        <div className="cardBody">
          {loading ? (
            <p className="muted">Loading…</p>
          ) : (
            <form onSubmit={save} className="grid2">
              <label className="field">
                <span>Organisation</span>
                <select className="input" value={orgId} onChange={(e) => setOrgId(e.target.value)}>
                  {orgs.map((o) => (
                    <option key={o.id} value={o.id}>{o.name || o.id}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Default lawful basis</span>
                <select
                  className="input"
                  value={defaults?.lawful_basis_default || ''}
                  onChange={(e) => updateField('lawful_basis_default', e.target.value)}
                >
                  <option value="">—</option>
                  {LAWFUL_BASES.map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </label>
              <label className="field">
                <span>Privacy notice URL</span>
                <input
                  className="input"
                  value={defaults?.privacy_notice_url || ''}
                  onChange={(e) => updateField('privacy_notice_url', e.target.value)}
                  placeholder="https://…"
                />
              </label>
              <label className="field">
                <span>Contact email</span>
                <input
                  className="input"
                  value={defaults?.contact_email || ''}
                  onChange={(e) => updateField('contact_email', e.target.value)}
                />
              </label>
              <label className="field">
                <span>DPO / data protection email</span>
                <input
                  className="input"
                  value={defaults?.dpo_email || ''}
                  onChange={(e) => updateField('dpo_email', e.target.value)}
                />
              </label>
              <label className="field checkRow">
                <input
                  type="checkbox"
                  checked={Boolean(defaults?.opt_out_enabled ?? true)}
                  onChange={(e) => updateField('opt_out_enabled', e.target.checked)}
                />
                <span>Opt-out enabled (PECR)</span>
              </label>
              <label className="field checkRow">
                <input
                  type="checkbox"
                  checked={Boolean(defaults?.special_category_data_present_default)}
                  onChange={(e) => updateField('special_category_data_present_default', e.target.checked)}
                />
                <span>Special category data (default)</span>
              </label>
              <label className="field">
                <span>Article 9 condition (if special category)</span>
                <select
                  className="input"
                  value={defaults?.article9_condition_default || ''}
                  onChange={(e) => updateField('article9_condition_default', e.target.value || null)}
                >
                  <option value="">—</option>
                  {ARTICLE9.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </label>
              <label className="field" style={{ gridColumn: '1 / -1' }}>
                <span>Just-in-time privacy intro (default)</span>
                <input
                  className="input"
                  value={defaults?.privacy_intro_text_default || ''}
                  onChange={(e) => updateField('privacy_intro_text_default', e.target.value)}
                />
              </label>
              <label className="field">
                <span>Retention: messages (days)</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={defaults?.retention_days_messages ?? 365}
                  onChange={(e) => updateField('retention_days_messages', Number(e.target.value))}
                />
              </label>
              <label className="field">
                <span>Retention: responses (days)</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={defaults?.retention_days_responses ?? 730}
                  onChange={(e) => updateField('retention_days_responses', Number(e.target.value))}
                />
              </label>
              <label className="field">
                <span>Retention: recordings (days)</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={defaults?.retention_days_recordings ?? 90}
                  onChange={(e) => updateField('retention_days_recordings', Number(e.target.value))}
                />
              </label>
              <label className="field">
                <span>Retention: transcripts (days)</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={defaults?.retention_days_transcripts ?? 365}
                  onChange={(e) => updateField('retention_days_transcripts', Number(e.target.value))}
                />
              </label>
              {selectedOrg ? (
                <p className="muted" style={{ gridColumn: '1 / -1' }}>
                  Orders for {selectedOrg.name} must pass compliance checks before launch/send.
                  Override per order via API <code>PUT /admin/compliance/orders/:id</code> with a <code>compliance</code> object.
                </p>
              ) : null}
              <div className="formActions" style={{ gridColumn: '1 / -1' }}>
                <button type="submit" className="btn primary" disabled={saving}>
                  {saving ? 'Saving…' : 'Save org defaults'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>

      <div className="card">
        <div className="cardHead"><h2>Recent compliance audit</h2></div>
        <div className="cardBody tableWrap">
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Event</th>
                <th>Org</th>
                <th>Order</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((ev) => (
                <tr key={ev.id}>
                  <td>{ev.created_at ? new Date(ev.created_at).toLocaleString() : '—'}</td>
                  <td><code>{ev.event_type}</code></td>
                  <td className="muted">{ev.org_id ? ev.org_id.slice(0, 8) : '—'}</td>
                  <td className="muted">{ev.order_id ? ev.order_id.slice(0, 8) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
