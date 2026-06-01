import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'

export default function PendingSignups() {
  const navigate = useNavigate()
  const [rows, setRows] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [autoApprovePromo, setAutoApprovePromo] = useState(true)
  const [settingsLoading, setSettingsLoading] = useState(true)
  const [settingsSaving, setSettingsSaving] = useState(false)

  async function loadSettings() {
    setSettingsLoading(true)
    try {
      const data = await apiFetch('/admin/onboarding/settings')
      setAutoApprovePromo(Boolean(data?.settings?.auto_approve_promo_signups ?? true))
    } catch {
      setAutoApprovePromo(true)
    } finally {
      setSettingsLoading(false)
    }
  }

  async function load() {
    try {
      const data = await apiFetch('/admin/onboarding/requests?status_filter=pending')
      setRows(Array.isArray(data) ? data : [])
    } catch {
      setRows([])
    }
  }

  useEffect(() => {
    loadSettings()
    load()
  }, [])

  const saveAutoApprove = async (next) => {
    setSettingsSaving(true)
    try {
      const data = await apiFetch('/admin/onboarding/settings', {
        method: 'PUT',
        body: JSON.stringify({ auto_approve_promo_signups: next }),
      })
      setAutoApprovePromo(Boolean(data?.settings?.auto_approve_promo_signups ?? next))
    } catch (e) {
      window.alert(e?.message || 'Could not save setting')
    } finally {
      setSettingsSaving(false)
    }
  }

  const decide = async (id, action) => {
    setBusyId(id)
    try {
      await apiFetch(`/admin/onboarding/requests/${id}/${action}`, { method: 'POST', body: JSON.stringify({}) })
      await load()
    } catch (e) {
      window.alert(e?.message || 'Action failed')
    } finally {
      setBusyId(null)
    }
  }

  const openOrgUsers = (organisationId) => {
    localStorage.setItem('voxbulk_admin_selected_org_id', organisationId)
    navigate('/organisations/profile?tab=users')
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Pending signups</h1>
          <p>
            Self-serve onboarding requests awaiting approval. <strong>Approve</strong> activates the user so they can log in.
            <span className='muted'> Rejected users cannot log in.</span>
          </p>
        </div>
        <div className='actions'>
          <button className='btn soft' onClick={load}>Refresh</button>
        </div>
      </div>

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardBody'>
          <h2 style={{ margin: '0 0 8px', fontSize: 16 }}>Promo signup approval</h2>
          <p className='muted' style={{ margin: '0 0 12px', fontSize: 14 }}>
            When enabled, customers who sign up with a sales promo link are activated immediately — no manual approval needed.
            Signups without a promo code always require manual approval.
          </p>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: settingsLoading || settingsSaving ? 'wait' : 'pointer' }}>
            <input
              type='checkbox'
              checked={autoApprovePromo}
              disabled={settingsLoading || settingsSaving}
              onChange={(e) => {
                const next = e.target.checked
                setAutoApprovePromo(next)
                saveAutoApprove(next)
              }}
            />
            <span>
              <strong>Auto-approve promo signups</strong>
              {settingsLoading ? ' (loading…)' : settingsSaving ? ' (saving…)' : autoApprovePromo ? ' — on (default)' : ' — off (manual approval)'}
            </span>
          </label>
        </div>
      </div>

      <div className='card'>
        <div className='cardBody'>
          <div className='tableWrap'>
            <table className='table'>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Organisation</th>
                  <th>User</th>
                  <th>Plan</th>
                  <th>Promo</th>
                  <th>Payment</th>
                  <th>Created</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {!rows && <tr><td colSpan={8}>Loading…</td></tr>}
                {rows && rows.length === 0 && <tr><td colSpan={8}>No pending requests.</td></tr>}
                {(rows || []).map((r) => (
                  <tr key={r.id}>
                    <td>{r.id}</td>
                    <td>{r.org_name || r.org_id}</td>
                    <td>{r.user_email || r.user_id}</td>
                    <td>{r.plan_code}</td>
                    <td>{r.promo_code || '—'}</td>
                    <td>{r.payment_method}</td>
                    <td>{r.created_at ? new Date(r.created_at).toLocaleString() : '—'}</td>
                    <td style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button type='button' className='btn soft' onClick={() => openOrgUsers(r.org_id)}>Org users</button>
                      <button type='button' className='btn soft' disabled={busyId === r.id} onClick={() => decide(r.id, 'approve')}>Approve</button>
                      <button type='button' className='btn' disabled={busyId === r.id} onClick={() => decide(r.id, 'reject')}>Reject</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  )
}
