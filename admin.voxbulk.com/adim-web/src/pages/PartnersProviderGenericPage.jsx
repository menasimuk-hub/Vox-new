import React, { useCallback, useEffect, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { connectionBadge, getPartnerProvider, modeBadge } from '../lib/partnersCatalog'
import './partners.css'

function copyText(text) {
  if (!text || !navigator?.clipboard) return
  navigator.clipboard.writeText(text).catch(() => {})
}

export default function PartnersProviderGenericPage() {
  const { providerKey } = useParams()
  const provider = getPartnerProvider(providerKey)

  const [enabled, setEnabled] = useState(false)
  const [mode, setMode] = useState('sandbox')
  const [connection, setConnection] = useState('none')
  const [mappedOrg, setMappedOrg] = useState('')
  const [orgOptions, setOrgOptions] = useState([])
  const [resultWebhook, setResultWebhook] = useState('')
  const [webhookSecret, setWebhookSecret] = useState('')
  const [keys, setKeys] = useState([])
  const [recentJobs, setRecentJobs] = useState([])
  const [revealedKey, setRevealedKey] = useState(null)
  const [flash, setFlash] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  const notify = useCallback((msg) => {
    setFlash(msg)
    window.setTimeout(() => setFlash(''), 3500)
  }, [])

  const apply = useCallback((data) => {
    const p = data?.provider || {}
    setEnabled(!!p.enabled)
    setMode(p.mode || 'sandbox')
    setMappedOrg(p.mapped_org_id || '')
    setResultWebhook(p.result_webhook_url || '')
    setKeys(data?.keys || [])
    setRecentJobs(data?.recent_jobs || [])
    const hasActive = (data?.keys || []).some((k) => k.is_active)
    if (p.last_health_ok === false) setConnection('error')
    else if (p.enabled && hasActive && p.mapped_org_id) setConnection(p.mode === 'live' ? 'connected' : 'sandbox')
    else setConnection('none')
  }, [])

  const load = useCallback(async () => {
    if (!provider) return
    setLoading(true)
    try {
      const [data, orgs] = await Promise.all([
        apiFetch(`/admin/partners/${provider.key}`),
        apiFetch('/admin/partners/org-options').catch(() => ({ items: [] })),
      ])
      apply(data)
      setOrgOptions(orgs?.items || [])
    } catch (e) {
      notify(e?.message || 'Load failed')
    } finally {
      setLoading(false)
    }
  }, [provider, apply, notify])

  useEffect(() => {
    load()
  }, [provider?.key]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!provider) return <Navigate to='/partners/dashboard' replace />

  const conn = connectionBadge(connection)
  const modeB = modeBadge(mode)
  const inboundUrl = 'https://api.voxbulk.com/partner/v1/screenings'

  const keyLabel = (environment) => {
    const active = keys.find((k) => k.environment === environment && k.is_active)
    if (!active) return 'Not generated'
    if (revealedKey?.environment === environment) return revealedKey.api_key
    return `${active.key_prefix}…`
  }

  const onSave = async () => {
    setBusy(true)
    try {
      const body = {
        enabled,
        mode,
        mapped_org_id: mappedOrg || null,
        result_webhook_url: resultWebhook || '',
      }
      if (webhookSecret) body.webhook_secret = webhookSecret
      const data = await apiFetch(`/admin/partners/${provider.key}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      })
      apply(data)
      setWebhookSecret('')
      notify('Saved')
    } catch (e) {
      notify(e?.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const onGenerateKey = async (environment) => {
    setBusy(true)
    try {
      const res = await apiFetch(`/admin/partners/${provider.key}/keys?environment=${environment}`, {
        method: 'POST',
      })
      setRevealedKey({ environment, api_key: res.api_key })
      notify(`${environment} key generated`)
      await load()
    } catch (e) {
      notify(e?.message || 'Key failed')
    } finally {
      setBusy(false)
    }
  }

  const onPing = async () => {
    setBusy(true)
    try {
      const res = await apiFetch(`/admin/partners/${provider.key}/health`, { method: 'POST' })
      notify(res.message || (res.ok ? 'OK' : 'Failed'))
      await load()
    } catch (e) {
      notify(e?.message || 'Health failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='partners-page'>
      <Link className='partners-back' to='/partners/dashboard'>
        <i className='ti ti-arrow-left' /> Provider Dashboard
      </Link>
      <div className='partners-header'>
        <div>
          <h1>{provider.label}</h1>
          <div className='partners-sub'>Partner API keys, mapped org, webhook</div>
        </div>
      </div>
      <div className='partners-status-row'>
        <span className={`partners-badge ${conn.cls}`}>{conn.text}</span>
        <span className={`partners-badge ${modeB.cls}`}>{modeB.text}</span>
        {flash ? <span className='partners-helper'>{flash}</span> : null}
        {loading ? <span className='partners-helper'>Loading…</span> : null}
      </div>

      <section className='partners-section'>
        <h3>Connection</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Enabled</span>
          <button
            type='button'
            className={`partners-toggle ${enabled ? 'on' : ''}`}
            onClick={() => setEnabled((v) => !v)}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Mode</span>
          <select className='partners-control' style={{ maxWidth: 180 }} value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value='sandbox'>Sandbox</option>
            <option value='live'>Live</option>
          </select>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Mapped org</span>
          <select
            className='partners-control'
            style={{ maxWidth: 320 }}
            value={mappedOrg}
            onChange={(e) => setMappedOrg(e.target.value)}
          >
            <option value=''>Select…</option>
            {orgOptions.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-primary' disabled={busy} onClick={onSave}>
            Save
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={busy} onClick={onPing}>
            Test health
          </button>
        </div>
      </section>

      <section className='partners-section'>
        <h3>API keys</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Partner name</span>
          <span className='partners-readonly'>{provider.partnerNameHeader}</span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Sandbox</span>
          <span className='partners-readonly'>
            {keyLabel('sandbox')}
            {revealedKey?.environment === 'sandbox' ? (
              <button type='button' className='partners-copy-btn' onClick={() => copyText(revealedKey.api_key)}>
                <i className='ti ti-copy' />
              </button>
            ) : null}
          </span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Live</span>
          <span className='partners-readonly'>
            {keyLabel('live')}
            {revealedKey?.environment === 'live' ? (
              <button type='button' className='partners-copy-btn' onClick={() => copyText(revealedKey.api_key)}>
                <i className='ti ti-copy' />
              </button>
            ) : null}
          </span>
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={busy} onClick={() => onGenerateKey('sandbox')}>
            Generate sandbox
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={busy} onClick={() => onGenerateKey('live')}>
            Generate live
          </button>
        </div>
        <div className='partners-helper'>Inbound: {inboundUrl}</div>
      </section>

      <section className='partners-section'>
        <h3>Webhook</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Result URL</span>
          <input
            className='partners-control'
            style={{ maxWidth: 400 }}
            value={resultWebhook}
            onChange={(e) => setResultWebhook(e.target.value)}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Secret</span>
          <input
            className='partners-control'
            type='password'
            style={{ maxWidth: 260 }}
            value={webhookSecret}
            onChange={(e) => setWebhookSecret(e.target.value)}
            placeholder='Leave blank to keep'
          />
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-primary' disabled={busy} onClick={onSave}>
            Save
          </button>
        </div>
      </section>

      <section className='partners-section'>
        <h3>Recent jobs</h3>
        {recentJobs.length === 0 ? (
          <div className='partners-footer-note' style={{ marginTop: 0 }}>
            No jobs yet.
          </div>
        ) : (
          <div className='partners-table-wrap'>
            <table className='partners-table'>
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Candidate</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.map((j) => (
                  <tr key={j.id}>
                    <td>{j.partner_reference_id}</td>
                    <td>{j.candidate_name}</td>
                    <td>{j.result_status || j.status}</td>
                    <td>{j.created_at || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
