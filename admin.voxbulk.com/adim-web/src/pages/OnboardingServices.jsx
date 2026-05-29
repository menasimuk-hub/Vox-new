import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

const SERVICE_ROWS = [
  { key: 'interview', label: 'Interviews', desc: 'AI phone screening campaigns' },
  { key: 'survey', label: 'Surveys', desc: 'AI phone & WhatsApp questionnaires' },
  { key: 'recovery', label: 'Recovery', desc: 'Missed-appointment & recall outreach' },
  { key: 'follow_up', label: 'Follow up', desc: 'WhatsApp appointment reminders' },
]

export default function OnboardingServices() {
  const [orgs, setOrgs] = useState(null)
  const [orgId, setOrgId] = useState('')
  const [services, setServices] = useState({ interview: true, survey: true, recovery: false, follow_up: false })
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const selectedOrg = useMemo(() => (orgs || []).find((o) => o.id === orgId) || null, [orgs, orgId])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch('/admin/organisations?limit=500')
        if (cancelled) return
        const list = Array.isArray(data) ? data : []
        setOrgs(list)
        const stored = localStorage.getItem('retover_admin_selected_org_id') || ''
        if (stored && list.some((o) => o.id === stored)) setOrgId(stored)
        else if (list.length) setOrgId(list[0].id)
      } catch (e) {
        if (!cancelled) {
          setOrgs([])
          setError(e?.message || 'Could not load organisations')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!orgId) return
    let cancelled = false
    setLoading(true)
    setError('')
    ;(async () => {
      try {
        const data = await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/enabled-services`)
        if (cancelled) return
        setServices({
          interview: data?.enabled_services?.interview !== false,
          survey: data?.enabled_services?.survey !== false,
          recovery: Boolean(data?.enabled_services?.recovery),
          follow_up: Boolean(data?.enabled_services?.follow_up),
        })
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load service toggles')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [orgId])

  const onToggle = (key, value) => {
    setServices((prev) => ({ ...prev, [key]: value }))
  }

  const onSave = async () => {
    if (!orgId) return
    setSaving(true)
    setError('')
    try {
      await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/enabled-services`, {
        method: 'PATCH',
        body: JSON.stringify(services),
      })
      window.alert('Dashboard services updated for this organisation.')
    } catch (e) {
      setError(e?.message || 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Customer services</h1>
          <p>
            Control which product modules appear in each customer&apos;s dashboard sidebar and home page.
            When a service is off, it is hidden from that organisation&apos;s dashboard.
          </p>
        </div>
        <div className='actions'>
          <button className='btn primary' onClick={() => void onSave()} disabled={!orgId || saving || loading}>
            {saving ? 'Saving…' : 'Save toggles'}
          </button>
        </div>
      </div>

      {error ? (
        <div className='card' style={{ marginBottom: 16, borderColor: '#fecaca' }}>
          <div className='cardBody' style={{ color: '#b91c1c', fontSize: 14 }}>{error}</div>
        </div>
      ) : null}

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardBody'>
          <label className='muted' style={{ display: 'block', marginBottom: 8, fontSize: 13 }}>Organisation</label>
          <select
            className='input'
            value={orgId}
            onChange={(e) => {
              setOrgId(e.target.value)
              localStorage.setItem('retover_admin_selected_org_id', e.target.value)
            }}
          >
            {(orgs || []).map((o) => (
              <option key={o.id} value={o.id}>{o.name}</option>
            ))}
          </select>
          {selectedOrg ? (
            <p className='muted' style={{ marginTop: 8, fontSize: 13 }}>
              Plan: {selectedOrg.plan_name || selectedOrg.plan_code || '—'} · Users: {selectedOrg.user_count ?? '—'}
            </p>
          ) : null}
        </div>
      </div>

      <div className='card'>
        <div className='cardHead'>
          <h3>Dashboard modules</h3>
          {loading ? <span className='pill'>Loading…</span> : null}
        </div>
        <div className='cardBody'>
          <div style={{ display: 'grid', gap: 12 }}>
            {SERVICE_ROWS.map((row) => (
              <div
                key={row.key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 16,
                  padding: '12px 14px',
                  border: '1px solid var(--border, #e5e7eb)',
                  borderRadius: 10,
                }}
              >
                <div>
                  <strong>{row.label}</strong>
                  <div className='muted' style={{ fontSize: 13 }}>{row.desc}</div>
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <span className='muted' style={{ fontSize: 12 }}>{services[row.key] ? 'On' : 'Off'}</span>
                  <input
                    type='checkbox'
                    checked={Boolean(services[row.key])}
                    onChange={(e) => onToggle(row.key, e.target.checked)}
                  />
                </label>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
